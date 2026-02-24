# =============== Cluster - State Sync ===============
#
# Leader ↔ Follower 狀態同步
#
# Leader 定期發佈叢集狀態到 Redis；Follower 輪詢讀取。
#   - ClusterSnapshot: 叢集狀態快照
#   - ClusterStatePublisher: Leader 端發佈器
#   - ClusterStateSubscriber: Follower 端訂閱器

from __future__ import annotations

import asyncio
import json
import socket
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .config import ClusterConfig

if TYPE_CHECKING:
    from csp_lib.controller.system import ModeManager, ProtectionGuard
    from csp_lib.redis import RedisClient

logger = get_logger("csp_lib.cluster.sync")


# ================ Snapshot ================


@dataclass
class ClusterSnapshot:
    """
    叢集狀態快照

    由 ClusterStateSubscriber 從 Redis 反序列化產生。

    Attributes:
        leader_id: 目前 leader instance_id
        elected_at: leader 上任時間
        base_modes: 基礎模式名稱列表
        override_names: 活躍的 override 名稱列表
        effective_mode: 目前生效的模式名稱
        triggered_rules: 觸發的保護規則名稱列表
        protection_was_modified: 保護是否修改了命令
        p_target: 最後一次命令的 P 目標
        q_target: 最後一次命令的 Q 目標
        command_timestamp: 最後一次命令的時間戳
        auto_stop_active: 自動停機是否啟動
    """

    leader_id: str | None = None
    elected_at: float | None = None
    base_modes: list[str] = field(default_factory=list)
    override_names: list[str] = field(default_factory=list)
    effective_mode: str | None = None
    triggered_rules: list[str] = field(default_factory=list)
    protection_was_modified: bool = False
    p_target: float = 0.0
    q_target: float = 0.0
    command_timestamp: float | None = None
    auto_stop_active: bool = False


# ================ Publisher (Leader) ================


class ClusterStatePublisher(AsyncLifecycleMixin):
    """
    叢集狀態發佈器（Leader 端）

    定期將 ModeManager、ProtectionGuard、last_command 等狀態
    寫入 Redis Hash，並透過 Pub/Sub 發送變更通知。
    """

    def __init__(
        self,
        config: ClusterConfig,
        redis_client: RedisClient,
        mode_manager: ModeManager,
        protection_guard: ProtectionGuard,
        get_last_command: Callable[[], tuple[float, float]],
        get_auto_stop: Callable[[], bool],
    ) -> None:
        """
        初始化發佈器

        Args:
            config: 叢集配置
            redis_client: Redis 客戶端
            mode_manager: 模式管理器
            protection_guard: 保護鏈
            get_last_command: 取得最後一次命令 (p_target, q_target) 的 callable
            get_auto_stop: 取得 auto_stop 狀態的 callable
        """
        self._config = config
        self._redis = redis_client
        self._mode_manager = mode_manager
        self._protection_guard = protection_guard
        self._get_last_command = get_last_command
        self._get_auto_stop = get_auto_stop
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._elected_at = time.time()

    async def _on_start(self) -> None:
        """啟動發佈迴圈"""
        self._stop_event.clear()
        self._elected_at = time.time()

        # 立即發佈 leader 身份
        await self._publish_leader_identity()
        await self._redis.publish(
            self._config.redis_channel("leader_change"),
            json.dumps({"instance_id": self._config.instance_id, "action": "elected"}),
        )

        self._task = asyncio.create_task(self._publish_loop())
        logger.info("ClusterStatePublisher started.")

    async def _on_stop(self) -> None:
        """停止發佈並清除 leader 身份"""
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # 清除 leader key
        try:
            await self._redis.delete(self._config.redis_key("leader"))
        except Exception:
            logger.exception("Failed to clear leader key on stop")

        logger.info("ClusterStatePublisher stopped.")

    async def _publish_loop(self) -> None:
        """定期發佈狀態"""
        interval = self._config.state_publish_interval
        while not self._stop_event.is_set():
            try:
                await self._publish_all()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Failed to publish cluster state")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                pass

    async def _publish_all(self) -> None:
        """發佈所有狀態到 Redis"""
        await self._publish_leader_identity()
        await self._publish_mode_state()
        await self._publish_protection_state()
        await self._publish_last_command()
        await self._publish_auto_stop()

    async def _publish_leader_identity(self) -> None:
        """發佈 leader 身份"""
        key = self._config.redis_key("leader")
        data = {
            "instance_id": self._config.instance_id,
            "elected_at": self._elected_at,
            "hostname": socket.gethostname(),
        }
        await self._redis.set(key, json.dumps(data), ex=self._config.state_ttl)

    async def _publish_mode_state(self) -> None:
        """發佈模式狀態"""
        mm = self._mode_manager
        key = self._config.redis_key("mode_state")
        data = {
            "base_modes": json.dumps(mm.base_mode_names),
            "overrides": json.dumps(mm.active_override_names),
            "effective_mode": mm.effective_mode.name if mm.effective_mode else "",
        }
        await self._redis.hset(key, data)
        await self._redis.expire(key, self._config.state_ttl)

    async def _publish_protection_state(self) -> None:
        """發佈保護狀態"""
        key = self._config.redis_key("protection_state")
        result = self._protection_guard.last_result
        data = {
            "triggered_rules": json.dumps(result.triggered_rules if result else []),
            "was_modified": json.dumps(result.was_modified if result else False),
        }
        await self._redis.hset(key, data)
        await self._redis.expire(key, self._config.state_ttl)

    async def _publish_last_command(self) -> None:
        """發佈最後一次命令"""
        key = self._config.redis_key("last_command")
        p, q = self._get_last_command()
        data = {
            "p_target": json.dumps(p),
            "q_target": json.dumps(q),
            "timestamp": json.dumps(time.time()),
        }
        await self._redis.hset(key, data)
        await self._redis.expire(key, self._config.state_ttl)

    async def _publish_auto_stop(self) -> None:
        """發佈自動停機狀態"""
        key = self._config.redis_key("auto_stop_active")
        value = "1" if self._get_auto_stop() else "0"
        await self._redis.set(key, value, ex=self._config.state_ttl)


# ================ Subscriber (Follower) ================


class ClusterStateSubscriber(AsyncLifecycleMixin):
    """
    叢集狀態訂閱器（Follower 端）

    定期輪詢 Redis 讀取 leader 發佈的叢集狀態與設備值。
    """

    def __init__(
        self,
        config: ClusterConfig,
        redis_client: RedisClient,
    ) -> None:
        self._config = config
        self._redis = redis_client
        self._snapshot = ClusterSnapshot()
        self._device_states: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def snapshot(self) -> ClusterSnapshot:
        """目前叢集狀態快照"""
        return self._snapshot

    @property
    def device_states(self) -> dict[str, dict[str, Any]]:
        """設備狀態快取（device_id → latest_values dict）"""
        return self._device_states

    async def _on_start(self) -> None:
        """啟動輪詢迴圈"""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("ClusterStateSubscriber started.")

    async def _on_stop(self) -> None:
        """停止輪詢"""
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ClusterStateSubscriber stopped.")

    async def _poll_loop(self) -> None:
        """輪詢主迴圈"""
        interval = self._config.state_publish_interval
        while not self._stop_event.is_set():
            try:
                await self._poll_all()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Failed to poll cluster state")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                pass

    async def _poll_all(self) -> None:
        """讀取所有叢集狀態"""
        snap = ClusterSnapshot()

        # Leader identity
        leader_raw = await self._redis.get(self._config.redis_key("leader"))
        if leader_raw is not None:
            try:
                leader_data = json.loads(leader_raw)
                snap.leader_id = leader_data.get("instance_id")
                snap.elected_at = leader_data.get("elected_at")
            except (json.JSONDecodeError, TypeError):
                pass

        # Mode state
        mode_data = await self._redis.hgetall(self._config.redis_key("mode_state"))
        if mode_data:
            raw_base = mode_data.get("base_modes")
            if isinstance(raw_base, str):
                try:
                    snap.base_modes = json.loads(raw_base)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(raw_base, list):
                snap.base_modes = raw_base

            raw_overrides = mode_data.get("overrides")
            if isinstance(raw_overrides, str):
                try:
                    snap.override_names = json.loads(raw_overrides)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(raw_overrides, list):
                snap.override_names = raw_overrides

            effective = mode_data.get("effective_mode", "")
            snap.effective_mode = effective if effective else None

        # Protection state
        prot_data = await self._redis.hgetall(self._config.redis_key("protection_state"))
        if prot_data:
            raw_rules = prot_data.get("triggered_rules")
            if isinstance(raw_rules, str):
                try:
                    snap.triggered_rules = json.loads(raw_rules)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(raw_rules, list):
                snap.triggered_rules = raw_rules

            raw_modified = prot_data.get("was_modified")
            if isinstance(raw_modified, bool):
                snap.protection_was_modified = raw_modified
            elif isinstance(raw_modified, str):
                try:
                    snap.protection_was_modified = json.loads(raw_modified)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Last command
        cmd_data = await self._redis.hgetall(self._config.redis_key("last_command"))
        if cmd_data:
            try:
                snap.p_target = float(cmd_data.get("p_target", 0.0))
            except (ValueError, TypeError):
                pass
            try:
                snap.q_target = float(cmd_data.get("q_target", 0.0))
            except (ValueError, TypeError):
                pass
            try:
                snap.command_timestamp = float(cmd_data.get("timestamp", 0.0))
            except (ValueError, TypeError):
                pass

        # Auto stop
        auto_stop_raw = await self._redis.get(self._config.redis_key("auto_stop_active"))
        snap.auto_stop_active = auto_stop_raw == "1"

        self._snapshot = snap

        # Device states（利用既有 StateSyncManager 發佈的 key）
        for device_id in self._config.device_ids:
            try:
                state = await self._redis.hgetall(f"device:{device_id}:state")
                if state:
                    self._device_states[device_id] = state
            except Exception:
                logger.debug(f"Failed to read device state for {device_id}")


__all__ = [
    "ClusterSnapshot",
    "ClusterStatePublisher",
    "ClusterStateSubscriber",
]
