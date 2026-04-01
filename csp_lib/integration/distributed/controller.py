# =============== Integration Distributed - Controller ===============
#
# 分散式控制器
#
# Controller 端的主編排器（Computer_3）：
#   - DistributedController: 結合遠端設備資料與本地策略執行

from __future__ import annotations

from typing import TYPE_CHECKING

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.core import AsyncLifecycleMixin, get_logger

from .command_router import RemoteCommandRouter
from .subscriber import DeviceStateSubscriber

if TYPE_CHECKING:
    from csp_lib.cluster.context import VirtualContextBuilder
    from csp_lib.controller.core import Strategy
    from csp_lib.integration import SystemController
    from csp_lib.redis import RedisClient

    from .config import DistributedConfig

logger = get_logger(__name__)


class DistributedController(AsyncLifecycleMixin):
    """
    分散式控制器

    Controller 端（Computer_3）的主編排器，不直接連接任何設備，
    改為透過 Redis 讀取遠端設備資料並將指令透過 Redis 發送回去。

    內部組件：
    1. DeviceStateSubscriber - 從 Redis 輪詢設備資料
    2. VirtualContextBuilder - 將快取資料轉換為 StrategyContext
    3. SystemController - ModeManager + ProtectionGuard + StrategyExecutor
    4. RemoteCommandRouter - 透過 Redis 發送指令到遠端站台

    Usage::

        ctrl = DistributedController(
            config=distributed_config,
            system_controller=sys_ctrl,
            redis_client=redis,
        )
        ctrl.register_mode("pq", pq_strategy, ModePriority.SCHEDULE)
        await ctrl.set_base_mode("pq")
        async with ctrl:
            await asyncio.Event().wait()
    """

    def __init__(
        self,
        config: DistributedConfig,
        system_controller: SystemController,
        redis_client: RedisClient,
    ) -> None:
        self._config = config
        self._system_controller = system_controller
        self._redis = redis_client

        # 內部元件（啟動後建立）
        self._subscriber: DeviceStateSubscriber | None = None
        self._virtual_builder: VirtualContextBuilder | None = None
        self._remote_router: RemoteCommandRouter | None = None

    # ---- 模式管理（委派 SystemController）----

    def register_mode(self, name: str, strategy: Strategy, priority: int, description: str = "") -> None:
        """註冊模式"""
        self._system_controller.register_mode(name, strategy, priority, description)

    async def set_base_mode(self, name: str | None) -> None:
        """設定基礎模式"""
        await self._system_controller.set_base_mode(name)

    async def add_base_mode(self, name: str) -> None:
        """新增基礎模式"""
        await self._system_controller.add_base_mode(name)

    async def remove_base_mode(self, name: str) -> None:
        """移除基礎模式"""
        await self._system_controller.remove_base_mode(name)

    async def push_override(self, name: str) -> None:
        """推入 override 模式"""
        await self._system_controller.push_override(name)

    async def pop_override(self, name: str) -> None:
        """移除 override 模式"""
        await self._system_controller.pop_override(name)

    def trigger(self) -> None:
        """手動觸發策略執行"""
        self._system_controller.trigger()

    # ---- 生命週期 ----

    async def _on_start(self) -> None:
        """啟動分散式控制器"""
        sc = self._system_controller

        # 1. 建立並啟動 DeviceStateSubscriber
        self._subscriber = DeviceStateSubscriber(self._config, self._redis)
        await self._subscriber.start()

        # 2. 建立 VirtualContextBuilder（延遲匯入以避免循環引用）
        from csp_lib.cluster.context import VirtualContextBuilder

        self._virtual_builder = VirtualContextBuilder(
            subscriber=self._subscriber,
            mappings=sc.config.context_mappings,
            system_base=sc.config.system_base,
            trait_device_map=self._config.trait_device_map,
        )

        # 3. 建立 RemoteCommandRouter
        self._remote_router = RemoteCommandRouter(
            config=self._config,
            redis_client=self._redis,
            subscriber=self._subscriber,
            mappings=sc.config.command_mappings,
        )

        # 4. Swap executor providers
        executor = sc.executor
        executor.set_context_provider(self._build_context)
        executor.set_on_command(self._on_command)

        # 5. 啟動 SystemController（executor 迴圈開始）
        await sc.start()

        logger.info("DistributedController started.")

    async def _on_stop(self) -> None:
        """停止分散式控制器"""
        # 停止 SystemController
        await self._system_controller.stop()

        # 停止 subscriber
        if self._subscriber is not None:
            await self._subscriber.stop()
            self._subscriber = None

        self._virtual_builder = None
        self._remote_router = None

        logger.info("DistributedController stopped.")

    # ---- 內部流程 ----

    def _build_context(self) -> StrategyContext:
        """建構策略上下文，注入 system_alarm 旗標"""
        if self._virtual_builder is None:
            return StrategyContext()

        ctx = self._virtual_builder.build()

        # 檢查設備離線狀態 → 觸發 system_alarm
        if self._config.system_alarm_on_device_offline and self._subscriber is not None:
            has_offline = any(not self._subscriber.device_online.get(did, False) for did in self._config.all_device_ids)
            alarm_key = self._system_controller.config.system_alarm_key
            ctx.extra[alarm_key] = has_offline

        return ctx

    async def _on_command(self, command: Command) -> None:
        """命令回呼：套用保護鏈 → 路由到遠端設備"""
        sc = self._system_controller
        context = self._build_context()

        # 套用保護鏈
        result = sc.protection_guard.apply(command, context)
        protected_command = result.protected_command

        # 處理自動停機
        if sc.config.auto_stop_on_alarm:
            await sc._handle_auto_stop(context)

        # 路由到遠端設備
        if self._remote_router is not None:
            await self._remote_router.route(protected_command)

    # ---- 唯讀屬性 ----

    @property
    def system_controller(self) -> SystemController:
        """內部 SystemController"""
        return self._system_controller

    @property
    def subscriber(self) -> DeviceStateSubscriber | None:
        """設備狀態訂閱器"""
        return self._subscriber

    @property
    def remote_router(self) -> RemoteCommandRouter | None:
        """遠端指令路由器"""
        return self._remote_router

    @property
    def is_running(self) -> bool:
        """是否正在執行"""
        return self._system_controller.is_running


__all__ = [
    "DistributedController",
]
