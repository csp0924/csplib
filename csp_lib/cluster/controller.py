# =============== Cluster - Controller ===============
#
# 叢集控制器
#
# 中央編排器：包裝 SystemController + UnifiedDeviceManager，
# 根據 leader/follower 角色切換行為。

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .config import ClusterConfig
from .context import VirtualContextBuilder
from .election import LeaderElector
from .sync import ClusterStatePublisher, ClusterStateSubscriber

if TYPE_CHECKING:
    from csp_lib.integration import SystemController
    from csp_lib.manager import UnifiedDeviceManager
    from csp_lib.redis import RedisClient

logger = get_logger("csp_lib.cluster.controller")


class ClusterController(AsyncLifecycleMixin):
    """
    叢集控制器

    包裝 SystemController 與 UnifiedDeviceManager，根據 etcd leader election
    的結果在 leader/follower 角色間切換。

    - Leader: 完整管線 — 連接設備、保護評估、命令路由、MongoDB/Redis 寫入
    - Follower: 虛擬 context（從 Redis 讀取），策略 dry-run，不連接設備

    Usage::

        cluster = ClusterController(
            config=cluster_config,
            system_controller=sys_ctrl,
            unified_manager=unified_mgr,
            redis_client=redis,
        )
        async with cluster:
            await asyncio.Event().wait()
    """

    def __init__(
        self,
        config: ClusterConfig,
        system_controller: SystemController,
        unified_manager: UnifiedDeviceManager,
        redis_client: RedisClient,
        on_promoted: Callable[[], Awaitable[None]] | None = None,
        on_demoted: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._system_controller = system_controller
        self._unified_manager = unified_manager
        self._redis = redis_client
        self._on_promoted_hook = on_promoted
        self._on_demoted_hook = on_demoted

        # 內部元件（啟動後建立）
        self._subscriber: ClusterStateSubscriber | None = None
        self._publisher: ClusterStatePublisher | None = None
        self._virtual_builder: VirtualContextBuilder | None = None
        self._elector: LeaderElector | None = None

        # 儲存原始 context_provider 與 on_command（leader 模式用）
        self._live_context_provider = self._system_controller._build_context
        self._live_on_command = self._system_controller._on_command

    # ---- 屬性 ----

    @property
    def role(self) -> str:
        """目前角色"""
        if self._elector is None:
            return "stopped"
        return self._elector.state.value

    @property
    def is_leader(self) -> bool:
        """是否為 leader"""
        return self._elector is not None and self._elector.is_leader

    @property
    def elector(self) -> LeaderElector | None:
        """Leader election 元件"""
        return self._elector

    # ---- 生命週期 ----

    async def _on_start(self) -> None:
        """啟動叢集控制器（以 follower 模式啟動）"""
        # 1. 建立並啟動 subscriber
        self._subscriber = ClusterStateSubscriber(self._config, self._redis)
        await self._subscriber.start()

        # 2. 建立 VirtualContextBuilder
        sc = self._system_controller
        trait_device_map = self._build_trait_device_map()
        self._virtual_builder = VirtualContextBuilder(
            subscriber=self._subscriber,
            mappings=sc.config.context_mappings,
            system_base=sc.config.system_base,
            trait_device_map=trait_device_map,
        )

        # 3. 進入 follower 模式（swap executor）
        self._enter_follower_mode()

        # 4. 啟動 SystemController（executor 以 follower context + no-op command 運行）
        await self._system_controller.start()

        # 5. 啟動 LeaderElector
        self._elector = LeaderElector(
            config=self._config,
            on_elected=self._handle_elected,
            on_demoted=self._handle_demoted,
        )
        await self._elector.start()

        logger.info(f"ClusterController started: instance={self._config.instance_id}")

    async def _on_stop(self) -> None:
        """停止叢集控制器"""
        # 停止 elector
        if self._elector is not None:
            await self._elector.stop()
            self._elector = None

        # 停止 publisher
        if self._publisher is not None:
            await self._publisher.stop()
            self._publisher = None

        # 停止 system controller
        await self._system_controller.stop()

        # 如果是 leader，停止 unified manager
        if self._unified_manager.is_running:
            await self._unified_manager.stop()

        # 停止 subscriber
        if self._subscriber is not None:
            await self._subscriber.stop()
            self._subscriber = None

        logger.info("ClusterController stopped.")

    # ---- Promotion / Demotion ----

    async def _handle_elected(self) -> None:
        """升格為 leader 的回呼"""
        logger.info("Promoting to leader...")

        # 1. 啟動 UnifiedDeviceManager（連接 Modbus、啟動讀取、啟動 MongoDB/Redis sync）
        await self._unified_manager.start()

        # 2. 等待 failover_grace_period（讓設備產生新資料）
        await asyncio.sleep(self._config.failover_grace_period)

        # 3. 切換 executor 到 live 模式
        self._enter_leader_mode()

        # 4. 啟動 ClusterStatePublisher
        executor = self._system_controller.executor
        self._publisher = ClusterStatePublisher(
            config=self._config,
            redis_client=self._redis,
            mode_manager=self._system_controller.mode_manager,
            protection_guard=self._system_controller.protection_guard,
            get_last_command=lambda: (executor.last_command.p_target, executor.last_command.q_target),
            get_auto_stop=lambda: self._system_controller.auto_stop_active,
        )
        await self._publisher.start()

        # 5. 同步 follower 快取的模式狀態到 live ModeManager
        if self._subscriber is not None:
            await self._sync_mode_state_from_snapshot()

        # 6. 呼叫使用者的 promoted hook
        if self._on_promoted_hook is not None:
            await self._on_promoted_hook()

        logger.info("Promoted to leader successfully.")

    async def _handle_demoted(self) -> None:
        """降級為 follower 的回呼"""
        logger.info("Demoting to follower...")

        # 1. 停止 publisher
        if self._publisher is not None:
            await self._publisher.stop()
            self._publisher = None

        # 2. 切換 executor 到 follower 模式（先於停止設備）
        self._enter_follower_mode()

        # 3. 停止 UnifiedDeviceManager
        await self._unified_manager.stop()

        # 4. 呼叫使用者的 demoted hook
        if self._on_demoted_hook is not None:
            await self._on_demoted_hook()

        logger.info("Demoted to follower.")

    # ---- Mode Switching ----

    def _enter_follower_mode(self) -> None:
        """切換 executor 到 follower 模式"""
        executor = self._system_controller.executor
        if self._virtual_builder is not None:
            executor.set_context_provider(self._virtual_builder.build)
        executor.set_on_command(self._noop_command_handler)
        logger.debug("Executor switched to follower mode (virtual context, no-op command).")

    def _enter_leader_mode(self) -> None:
        """切換 executor 到 leader 模式"""
        executor = self._system_controller.executor
        executor.set_context_provider(self._live_context_provider)
        executor.set_on_command(self._live_on_command)
        logger.debug("Executor switched to leader mode (live context, real command).")

    @staticmethod
    async def _noop_command_handler(command) -> None:
        """Follower 的 no-op 命令處理器"""
        pass

    # ---- Helpers ----

    def _build_trait_device_map(self) -> dict[str, list[str]]:
        """從 context_mappings 中的 trait 與 registry 建構 trait → device_id 映射"""
        trait_map: dict[str, list[str]] = {}
        sc = self._system_controller
        for mapping in sc.config.context_mappings:
            if mapping.trait is not None and mapping.trait not in trait_map:
                devices = sc.registry.get_devices_by_trait(mapping.trait)
                trait_map[mapping.trait] = [d.device_id for d in devices]
        return trait_map

    async def _sync_mode_state_from_snapshot(self) -> None:
        """將 subscriber 快取的模式狀態同步到 live ModeManager"""
        if self._subscriber is None:
            return

        snap = self._subscriber.snapshot
        mm = self._system_controller.mode_manager

        # 同步 base modes
        if snap.base_modes:
            for mode_name in snap.base_modes:
                if mode_name in mm.registered_modes and mode_name not in mm.base_mode_names:
                    try:
                        await mm.add_base_mode(mode_name)
                    except (KeyError, ValueError):
                        pass

    def health(self) -> dict:
        """取得叢集健康狀態"""
        return {
            "role": self.role,
            "instance_id": self._config.instance_id,
            "is_leader": self.is_leader,
            "leader_id": self._elector.current_leader_id if self._elector else None,
            "unified_manager_running": self._unified_manager.is_running,
            "system_controller_running": self._system_controller.is_running,
        }


__all__ = [
    "ClusterController",
]
