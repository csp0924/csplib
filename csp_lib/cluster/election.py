# =============== Cluster - Election ===============
#
# etcd 基於 lease 的 leader election
#
# 使用 etcetra 實現分散式 leader election：
#   - LeaderElector: campaign / resign / watch 邏輯

from __future__ import annotations

import asyncio
import enum
import socket
from typing import Awaitable, Callable

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .config import ClusterConfig

logger = get_logger(__name__)


class ElectionState(enum.Enum):
    """選舉狀態"""

    CANDIDATE = "candidate"
    LEADER = "leader"
    FOLLOWER = "follower"
    STOPPED = "stopped"


class LeaderElector(AsyncLifecycleMixin):
    """
    etcd lease-based leader election

    演算法：
    1. Grant lease with TTL
    2. Transaction: IF election_key NOT EXISTS → PUT(key, instance_id, lease)
    3. Success → LEADER: keep-alive renewal loop + watch for deletion
    4. Failure → FOLLOWER: watch key for DELETE → re-campaign

    Attributes:
        is_leader: 是否為 leader
        state: 目前選舉狀態
        current_leader_id: 目前 leader 的 instance_id
    """

    def __init__(
        self,
        config: ClusterConfig,
        on_elected: Callable[[], Awaitable[None]] | None = None,
        on_demoted: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._on_elected = on_elected
        self._on_demoted = on_demoted

        self._state = ElectionState.STOPPED
        self._current_leader_id: str | None = None
        self._lease = None
        self._client = None
        self._campaign_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._watch_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        # self-resign 旗標：在主動 resign 期間設為 True，避免 watch 對 self-induced
        # DELETE 事件再走一次 demotion 流程（會誤觸 on_demoted）。
        self._resigning = False
        # watch 重連退避（秒），失敗時遞增直到上限
        self._watch_backoff_initial = 0.1
        self._watch_backoff_max = 5.0

    @property
    def is_leader(self) -> bool:
        return self._state == ElectionState.LEADER

    @property
    def state(self) -> ElectionState:
        return self._state

    @property
    def current_leader_id(self) -> str | None:
        return self._current_leader_id

    async def _on_start(self) -> None:
        """啟動選舉流程"""
        self._stop_event.clear()
        self._resigning = False
        self._state = ElectionState.CANDIDATE

        self._client = self._create_etcd_client()

        logger.info(f"LeaderElector started: instance={self._config.instance_id}, key={self._config.election_key}")
        self._campaign_task = asyncio.create_task(self._campaign_loop())

    def _create_etcd_client(self):
        """建立 etcd 客戶端（可在測試中覆寫）"""
        import etcetra

        endpoint = self._config.etcd.endpoints[0]
        host, _, port_str = endpoint.partition(":")
        port = int(port_str) if port_str else 2379

        return etcetra.EtcdClient(
            host=host,
            port=port,
            username=self._config.etcd.username,
            password=self._config.etcd.password,
        )

    async def _on_stop(self) -> None:
        """停止選舉，resign 如果是 leader"""
        self._stop_event.set()

        if self._state == ElectionState.LEADER:
            await self._resign_internal()

        self._state = ElectionState.STOPPED

        # 取消背景任務
        for task in (self._campaign_task, self._keepalive_task, self._watch_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._campaign_task = None
        self._keepalive_task = None
        self._watch_task = None

        if self._client is not None:
            await self._client.close()
            self._client = None

        logger.info("LeaderElector stopped.")

    async def resign(self) -> None:
        """主動辭去 leader 角色（撤銷 lease）"""
        if self._state != ElectionState.LEADER:
            return
        await self._resign_internal()

    async def _resign_internal(self) -> None:
        """內部 resign 實作

        設置 self._resigning 旗標，讓 watch loop 對接下來收到的 DELETE 事件
        判斷為 self-induced 並略過 demotion 流程。
        """
        self._resigning = True
        if self._lease is not None and self._client is not None:
            try:
                await self._client.lease_revoke(self._lease)
                logger.info("Lease revoked (resigned).")
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"Failed to revoke lease during resign: instance={self._config.instance_id}, "
                    f"state={self._state.value}: {e}"
                )
            self._lease = None

    async def _campaign_loop(self) -> None:
        """持續嘗試競選 leader"""
        while not self._stop_event.is_set():
            try:
                await self._try_campaign()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"Election campaign failed: instance={self._config.instance_id}, "
                    f"state={self._state.value}, retrying in {self._config.campaign_retry_delay}s: {e}"
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.campaign_retry_delay)
                    return  # stopped
                except asyncio.TimeoutError:
                    pass

    async def _try_campaign(self) -> None:
        """嘗試一次競選"""
        if self._client is None:
            return

        # Grant lease
        self._lease = await self._client.lease_grant(self._config.lease_ttl)
        lease_id = self._lease

        # 嘗試以 transaction 取得 election key
        election_key = self._config.election_key
        instance_id = self._config.instance_id
        hostname = socket.gethostname()
        value = f"{instance_id}@{hostname}"

        success = await self._client.txn_put_if_not_exists(election_key, value, lease_id)

        if success:
            # 我們是 leader
            self._state = ElectionState.LEADER
            self._current_leader_id = instance_id
            logger.info(f"Elected as leader: {instance_id}")

            if self._on_elected is not None:
                await self._on_elected()

            # 啟動 keepalive 與 watch
            self._keepalive_task = asyncio.create_task(self._keepalive_loop(lease_id))
            self._watch_task = asyncio.create_task(self._watch_leader_key())

            # 等待直到被 demoted 或 stopped
            await self._stop_event.wait()
        else:
            # 讀取目前 leader
            current_value = await self._client.get(election_key)
            if current_value is not None:
                self._current_leader_id = current_value.split("@")[0] if "@" in current_value else current_value
            self._state = ElectionState.FOLLOWER
            logger.info(f"Following leader: {self._current_leader_id}")

            # 撤銷我們的無用 lease
            try:
                await self._client.lease_revoke(lease_id)
            except Exception as e:
                logger.debug(f"Failed to revoke unused lease after losing election: {e}")
            self._lease = None

            # Watch key 等待 leader 離開
            await self._wait_for_leader_loss()

    async def _keepalive_loop(self, lease_id: int) -> None:
        """持續更新 lease TTL"""
        interval = max(self._config.lease_ttl / 3, 1.0)
        consecutive_failures = 0
        max_failures = self._config.max_keepalive_failures

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                return  # stopped
            except asyncio.TimeoutError:
                pass

            try:
                await self._client.lease_keepalive(lease_id)
                consecutive_failures = 0
            except asyncio.CancelledError:
                return
            except Exception as e:
                consecutive_failures += 1
                logger.warning(
                    f"Lease keepalive failed (attempt {consecutive_failures}/{max_failures}): "
                    f"instance={self._config.instance_id}, state={self._state.value}: {e}"
                )
                if consecutive_failures >= max_failures:
                    logger.error("Lease keepalive failed too many times, self-fencing")
                    await self._handle_demotion()
                    return

    async def _watch_leader_key(self) -> None:
        """Leader 模式下監視自己的 key 是否被外部刪除。

        若收到 DELETE 事件且非自身 resign 觸發（self._resigning == False），
        立即呼叫 _handle_demotion，避免等到 keepalive 連續失敗才偵測到失主權
        （該路徑延遲約 max_keepalive_failures × (lease_ttl/3) 秒）。

        實作細節：
          - 使用 client.watch(key) 取得 async iterator
          - 事件型別判斷以 ev.event_type / ev.event 為主（兼容 etcetra.WatchEvent
            的 .event: WatchEventType 與測試 mock 的 .event_type: str）
          - watch 連線失敗時以指數退避重連，直到 stop 或 demoted
          - 由 stop()/demotion 透過 task.cancel() 終止
        """
        if self._client is None:
            return

        election_key = self._config.election_key
        backoff = self._watch_backoff_initial

        while not self._stop_event.is_set() and self._state == ElectionState.LEADER:
            try:
                watcher = self._client.watch(election_key)
                async for event in watcher:
                    if self._stop_event.is_set() or self._state != ElectionState.LEADER:
                        return
                    if not _is_delete_event(event):
                        continue
                    if self._resigning:
                        # 自身 resign 觸發的 DELETE — 不再走 demotion 流程
                        logger.debug("Ignoring self-induced DELETE event during resign")
                        return
                    logger.warning(
                        f"Election key externally deleted, demoting: "
                        f"instance={self._config.instance_id}, key={election_key}"
                    )
                    await self._handle_demotion()
                    return
                # watch iterator 結束（連線斷）— 重試
                backoff = self._watch_backoff_initial
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"Watch loop error, retrying in {backoff:.1f}s: "
                    f"instance={self._config.instance_id}, key={election_key}: {e}"
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                    return  # stopped
                except asyncio.TimeoutError:
                    backoff = min(backoff * 2, self._watch_backoff_max)

    async def _wait_for_leader_loss(self) -> None:
        """Follower 模式下等待 leader key 消失"""
        if self._client is None:
            return

        election_key = self._config.election_key
        poll_interval = max(self._config.lease_ttl / 2, 1.0)

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=poll_interval)
                return  # stopped
            except asyncio.TimeoutError:
                pass

            try:
                value = await self._client.get(election_key)
                if value is None:
                    # Leader 消失，重新競選
                    logger.info("Leader key disappeared, re-campaigning")
                    self._state = ElectionState.CANDIDATE
                    return
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"Error polling leader key: instance={self._config.instance_id}, "
                    f"state={self._state.value}, key={self._config.election_key}: {e}"
                )

    async def _handle_demotion(self) -> None:
        """處理從 leader 降級"""
        if self._state != ElectionState.LEADER:
            return

        self._state = ElectionState.FOLLOWER
        self._current_leader_id = None
        logger.warning("Demoted from leader")

        if self._on_demoted is not None:
            await self._on_demoted()


def _is_delete_event(event: object) -> bool:
    """判斷 watch 事件是否為 DELETE。

    兼容 etcetra.types.WatchEvent（.event: WatchEventType enum，name == "DELETE"）
    與測試 mock（.event_type: str == "DELETE"）兩種形態。
    """
    # 測試 mock 路徑：直接帶 event_type 字串
    et = getattr(event, "event_type", None)
    if isinstance(et, str):
        return et.upper() == "DELETE"
    # etcetra 路徑：ev.event 為 WatchEventType enum
    ev_field = getattr(event, "event", None)
    if ev_field is not None:
        name = getattr(ev_field, "name", None)
        if isinstance(name, str):
            return name.upper() == "DELETE"
        # fallback：直接比字串化
        return str(ev_field).upper().endswith("DELETE")
    return False


__all__ = [
    "ElectionState",
    "LeaderElector",
]
