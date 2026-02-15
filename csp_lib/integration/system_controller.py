# =============== Integration - System Controller ===============
#
# 頂層系統控制器
#
# 結合 ModeManager、ProtectionGuard 與既有整合元件，提供：
#   - 模式管理：註冊多種模式並以優先權切換
#   - 保護機制：SOC 限制、逆送保護、系統告警保護
#   - 自動告警處理：設備告警時自動推入 stop override
#
# 架構：
#   ContextBuilder.build() → StrategyContext (注入 system_alarm)
#        ↓
#   StrategyExecutor (策略由 ModeManager 決定)
#        ↓
#   Command (原始) → ProtectionGuard.apply() → Command (保護後)
#        ↓
#   CommandRouter.route() → 設備寫入

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from csp_lib.controller.core import Command, StrategyContext, SystemBase
from csp_lib.controller.executor import StrategyExecutor
from csp_lib.controller.services import PVDataService
from csp_lib.controller.strategies import StopStrategy
from csp_lib.controller.system import ModeManager, ModePriority, ProtectionGuard, ProtectionResult, ProtectionRule
from csp_lib.core import AsyncLifecycleMixin, get_logger

from .command_router import CommandRouter
from .context_builder import ContextBuilder
from .data_feed import DeviceDataFeed
from .registry import DeviceRegistry
from .schema import CommandMapping, ContextMapping, DataFeedMapping

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy

logger = get_logger("csp_lib.integration.system_controller")

_AUTO_STOP_MODE = "__auto_stop__"


@dataclass
class SystemControllerConfig:
    """
    SystemController 配置

    Attributes:
        context_mappings: 設備點位 → StrategyContext 的映射列表
        command_mappings: Command 欄位 → 設備寫入的映射列表
        system_base: 系統基準值（可選）
        data_feed_mapping: PV 資料餵入映射（可選）
        pv_max_history: PVDataService 最大歷史記錄數
        protection_rules: 保護規則列表
        auto_stop_on_alarm: 系統告警時自動推入 stop override
        system_alarm_key: system_alarm 在 context.extra 中的 key
    """

    context_mappings: list[ContextMapping] = field(default_factory=list)
    command_mappings: list[CommandMapping] = field(default_factory=list)
    system_base: SystemBase | None = None
    data_feed_mapping: DataFeedMapping | None = None
    pv_max_history: int = 300
    protection_rules: list[ProtectionRule] = field(default_factory=list)
    auto_stop_on_alarm: bool = True
    system_alarm_key: str = "system_alarm"


class SystemController(AsyncLifecycleMixin):
    """
    頂層系統控制器

    結合 ModeManager（模式管理）、ProtectionGuard（保護鏈）與既有整合元件，
    在不修改現有 GridControlLoop 的前提下，提供更高階的控制能力。

    內部流程：
    1. _build_context(): ContextBuilder.build() + 注入 system_alarm 旗標
    2. _on_command(command): ProtectionGuard.apply() → CommandRouter.route()
    3. _handle_auto_stop(): 告警啟用 → push stop override；告警解除 → pop

    使用範例::

        controller = SystemController(registry, config)
        controller.register_mode("pq", pq_strategy, ModePriority.SCHEDULE)
        await controller.set_base_mode("pq")
        async with controller:
            await asyncio.Event().wait()
    """

    def __init__(self, registry: DeviceRegistry, config: SystemControllerConfig) -> None:
        self._registry = registry
        self._config = config

        # 模式管理
        self._mode_manager = ModeManager(on_strategy_change=self._on_strategy_change)

        # 保護鏈
        self._protection_guard = ProtectionGuard(config.protection_rules)

        # PV 資料服務（可選）
        self._pv_service: PVDataService | None = None
        self._data_feed: DeviceDataFeed | None = None
        if config.data_feed_mapping is not None:
            self._pv_service = PVDataService(max_history=config.pv_max_history)
            self._data_feed = DeviceDataFeed(registry, config.data_feed_mapping, self._pv_service)

        # Context 建構器
        self._context_builder = ContextBuilder(registry, config.context_mappings, system_base=config.system_base)

        # Command 路由器
        self._command_router = CommandRouter(registry, config.command_mappings)

        # 策略執行器：context_provider 與 on_command 由本控制器管理
        self._executor = StrategyExecutor(
            context_provider=self._build_context,
            on_command=self._on_command,
        )

        # 自動停機狀態
        self._auto_stop_active = False
        self._cached_context = None

        # 背景任務
        self._run_task: asyncio.Task[None] | None = None

        # 註冊自動停機模式
        if config.auto_stop_on_alarm:
            self._mode_manager.register(
                _AUTO_STOP_MODE,
                StopStrategy(),
                ModePriority.PROTECTION + 1,
                "Auto stop on system alarm",
            )

    # ---- 模式管理（委派 ModeManager）----

    def register_mode(self, name: str, strategy: Strategy, priority: int, description: str = "") -> None:
        """註冊模式"""
        self._mode_manager.register(name, strategy, priority, description)

    async def set_base_mode(self, name: str | None) -> None:
        """設定基礎模式"""
        await self._mode_manager.set_base_mode(name)

    async def push_override(self, name: str) -> None:
        """推入 override 模式"""
        await self._mode_manager.push_override(name)

    async def pop_override(self, name: str) -> None:
        """移除 override 模式"""
        await self._mode_manager.pop_override(name)

    def trigger(self) -> None:
        """手動觸發策略執行"""
        self._executor.trigger()

    # ---- 生命週期 ----

    async def _on_start(self) -> None:
        """啟動系統控制器"""
        if self._data_feed is not None:
            self._data_feed.attach()
        self._run_task = asyncio.create_task(self._executor.run())
        logger.info("SystemController started.")

    async def _on_stop(self) -> None:
        """停止系統控制器"""
        self._executor.stop()
        if self._run_task is not None:
            await self._run_task
            self._run_task = None
        if self._data_feed is not None:
            self._data_feed.detach()
        logger.info("SystemController stopped.")

    # ---- 內部流程 ----

    def _build_context(self) -> StrategyContext:
        """建構策略上下文，注入 system_alarm 旗標"""
        context = self._context_builder.build()

        # 檢查所有設備的告警狀態
        has_alarm = any(dev.is_protected for dev in self._registry.all_devices)
        context.extra[self._config.system_alarm_key] = has_alarm

        self._cached_context = context
        return context

    async def _on_command(self, command: Command) -> None:
        """命令回呼：套用保護鏈 → 處理自動停機 → 路由到設備"""
        # 取得最近的 context（由 executor 在 _execute_strategy 中呼叫 _build_context 後產生）
        context = self._cached_context
        if context is None:
            context = self._build_context()

        # 套用保護鏈
        result = self._protection_guard.apply(command, context)
        protected_command = result.protected_command

        # 處理自動停機
        if self._config.auto_stop_on_alarm:
            await self._handle_auto_stop(context)

        # 路由到設備
        await self._command_router.route(protected_command)

    async def _handle_auto_stop(self, context: StrategyContext) -> None:
        """處理自動停機 override"""
        has_alarm = context.extra.get(self._config.system_alarm_key, False)

        if has_alarm and not self._auto_stop_active:
            self._auto_stop_active = True
            try:
                await self._mode_manager.push_override(_AUTO_STOP_MODE)
                logger.warning("Auto stop activated due to system alarm")
            except (KeyError, ValueError):
                pass  # 已經在堆疊中或未註冊
        elif not has_alarm and self._auto_stop_active:
            self._auto_stop_active = False
            try:
                await self._mode_manager.pop_override(_AUTO_STOP_MODE)
                logger.info("Auto stop deactivated, alarm cleared")
            except KeyError:
                pass  # 不在堆疊中

    async def _on_strategy_change(self, old: Strategy | None, new: Strategy | None) -> None:
        """ModeManager 通知策略變更"""
        logger.info(f"Strategy change: {old} -> {new}")
        await self._executor.set_strategy(new)

    # ---- 唯讀屬性 ----

    @property
    def registry(self) -> DeviceRegistry:
        """設備查詢索引"""
        return self._registry

    @property
    def executor(self) -> StrategyExecutor:
        """策略執行器"""
        return self._executor

    @property
    def mode_manager(self) -> ModeManager:
        """模式管理器"""
        return self._mode_manager

    @property
    def protection_guard(self) -> ProtectionGuard:
        """保護鏈"""
        return self._protection_guard

    @property
    def effective_mode_name(self) -> str | None:
        """當前生效的模式名稱"""
        mode = self._mode_manager.effective_mode
        return mode.name if mode is not None else None

    @property
    def protection_status(self) -> ProtectionResult | None:
        """最近一次保護結果"""
        return self._protection_guard.last_result

    @property
    def pv_service(self) -> PVDataService | None:
        """PV 資料服務"""
        return self._pv_service

    @property
    def is_running(self) -> bool:
        """是否正在執行"""
        return self._run_task is not None and not self._run_task.done()
