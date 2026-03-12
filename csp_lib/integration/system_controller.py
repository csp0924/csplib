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
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, StrategyContext, SystemBase
from csp_lib.controller.executor import StrategyExecutor
from csp_lib.controller.services import PVDataService
from csp_lib.controller.strategies import StopStrategy
from csp_lib.controller.system import ModeManager, ModePriority, ProtectionGuard, ProtectionResult, ProtectionRule
from csp_lib.controller.system.cascading import CapacityConfig, CascadingStrategy
from csp_lib.controller.system.event_override import AlarmStopOverride, EventDrivenOverride
from csp_lib.controller.system.mode import SwitchSource
from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.core.health import HealthReport, HealthStatus

from .command_router import CommandRouter
from .context_builder import ContextBuilder
from .data_feed import DeviceDataFeed
from .distributor import DeviceSnapshot, PowerDistributor
from .heartbeat import HeartbeatService
from .orchestrator import SystemCommandOrchestrator
from .registry import DeviceRegistry
from .schema import (
    CapabilityCommandMapping,
    CapabilityContextMapping,
    CommandMapping,
    ContextMapping,
    DataFeedMapping,
    HeartbeatMapping,
    HeartbeatMode,
)

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger("csp_lib.integration.system_controller")

_AUTO_STOP_MODE = "__auto_stop__"
_SCHEDULE_MODE = "__schedule__"


@dataclass
class SystemControllerConfig:
    """
    SystemController 配置

    Attributes:
        context_mappings: 設備點位 → StrategyContext 的映射列表
        command_mappings: Command 欄位 → 設備寫入的映射列表
        capability_context_mappings: capability-driven context 映射列表
        capability_command_mappings: capability-driven command 映射列表
        system_base: 系統基準值（可選）
        data_feed_mapping: PV 資料餵入映射（可選）
        pv_max_history: PVDataService 最大歷史記錄數
        protection_rules: 保護規則列表
        auto_stop_on_alarm: 系統告警時自動推入 stop override
        system_alarm_key: system_alarm 在 context.extra 中的 key
        capacity_kva: 級聯策略最大視在功率 (kVA)（可選，多 base mode 時啟用）
        alarm_mode: 告警模式 - "system_wide" 全系統停機 / "per_device" 僅告警設備關機
        on_device_alarm: 設備告警時的回呼（per_device 模式）
        on_device_alarm_clear: 設備告警解除時的回呼（per_device 模式）
        heartbeat_mappings: 心跳寫入映射列表（設定時自動建立 HeartbeatService）
        heartbeat_interval: 心跳寫入間隔（秒），預設 1.0
        use_heartbeat_capability: 是否啟用 HEARTBEAT 能力發現模式
        heartbeat_capability_mode: 能力發現模式的心跳值模式
        heartbeat_capability_constant_value: CONSTANT 模式的固定寫入值
        heartbeat_capability_increment_max: INCREMENT 模式的最大計數值
        power_distributor: 功率分配器（可選），設定後 capability command mappings 使用 per-device 分配
    """

    context_mappings: list[ContextMapping] = field(default_factory=list)
    command_mappings: list[CommandMapping] = field(default_factory=list)
    capability_context_mappings: list[CapabilityContextMapping] = field(default_factory=list)
    capability_command_mappings: list[CapabilityCommandMapping] = field(default_factory=list)
    system_base: SystemBase | None = None
    data_feed_mapping: DataFeedMapping | None = None
    pv_max_history: int = 300
    protection_rules: list[ProtectionRule] = field(default_factory=list)
    auto_stop_on_alarm: bool = True
    system_alarm_key: str = "system_alarm"
    capacity_kva: float | None = None
    alarm_mode: str = "system_wide"
    on_device_alarm: Callable[[AsyncModbusDevice], Awaitable[None]] | None = None
    on_device_alarm_clear: Callable[[AsyncModbusDevice], Awaitable[None]] | None = None
    heartbeat_mappings: list[HeartbeatMapping] = field(default_factory=list)
    heartbeat_interval: float = 1.0
    use_heartbeat_capability: bool = False
    heartbeat_capability_mode: HeartbeatMode = HeartbeatMode.TOGGLE
    heartbeat_capability_constant_value: int = 1
    heartbeat_capability_increment_max: int = 65535
    power_distributor: PowerDistributor | None = None


class _OverrideState:
    """EventDrivenOverride 的內部狀態追蹤"""

    __slots__ = ("active", "deactivate_at")

    def __init__(self) -> None:
        self.active: bool = False
        self.deactivate_at: float | None = None


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
        self._context_builder = ContextBuilder(
            registry,
            config.context_mappings,
            system_base=config.system_base,
            capability_mappings=config.capability_context_mappings or None,
        )

        # Command 路由器
        self._command_router = CommandRouter(
            registry,
            config.command_mappings,
            capability_mappings=config.capability_command_mappings or None,
        )

        # 系統指令編排器
        self._orchestrator = SystemCommandOrchestrator(registry)

        # 心跳服務（可選）
        self._heartbeat: HeartbeatService | None = None
        if config.heartbeat_mappings or config.use_heartbeat_capability:
            self._heartbeat = HeartbeatService(
                registry,
                mappings=config.heartbeat_mappings or None,
                interval=config.heartbeat_interval,
                use_capability=config.use_heartbeat_capability,
                mode=config.heartbeat_capability_mode,
                constant_value=config.heartbeat_capability_constant_value,
                increment_max=config.heartbeat_capability_increment_max,
            )

        # 策略執行器：context_provider 與 on_command 由本控制器管理
        self._executor = StrategyExecutor(
            context_provider=self._build_context,
            on_command=self._on_command,
        )

        # 自動停機狀態（向後相容）
        self._auto_stop_active = False
        self._cached_context: StrategyContext | None = None

        # 事件驅動 Override
        self._event_overrides: list[EventDrivenOverride] = []
        self._event_override_states: dict[str, _OverrideState] = {}

        # 設備級告警追蹤（per_device 模式）
        self._alarmed_devices: set[str] = set()

        # 背景任務
        self._run_task: asyncio.Task[None] | None = None

        # 註冊自動停機模式（通過 EventDrivenOverride 機制）
        if config.auto_stop_on_alarm:
            self._mode_manager.register(
                _AUTO_STOP_MODE,
                StopStrategy(),
                ModePriority.PROTECTION + 1,
                "Auto stop on system alarm",
            )
            self.register_event_override(AlarmStopOverride(name=_AUTO_STOP_MODE, alarm_key=config.system_alarm_key))

    # ---- 模式管理（委派 ModeManager）----

    def register_mode(self, name: str, strategy: Strategy, priority: int, description: str = "") -> None:
        """註冊模式，並驗證策略所需的 capabilities"""
        required = strategy.required_capabilities
        if required:
            for cap in required:
                devices = self._registry.get_devices_with_capability(cap)
                if not devices:
                    logger.warning(
                        f"Strategy '{strategy}' requires capability '{cap.name}' but no registered device has it."
                    )
        self._mode_manager.register(name, strategy, priority, description)

    async def set_base_mode(self, name: str | None) -> None:
        """設定基礎模式"""
        await self._mode_manager.set_base_mode(name)

    async def add_base_mode(self, name: str) -> None:
        """新增基礎模式（多 base mode 共存）"""
        await self._mode_manager.add_base_mode(name)

    async def remove_base_mode(self, name: str) -> None:
        """移除基礎模式"""
        await self._mode_manager.remove_base_mode(name)

    async def push_override(self, name: str) -> None:
        """推入 override 模式"""
        await self._mode_manager.push_override(name)

    async def pop_override(self, name: str) -> None:
        """移除 override 模式"""
        await self._mode_manager.pop_override(name)

    def register_event_override(self, override: EventDrivenOverride) -> None:
        """
        註冊事件驅動的 override

        Args:
            override: 實作 EventDrivenOverride 的實例，name 必須對應已註冊的模式
        """
        self._event_overrides.append(override)
        self._event_override_states[override.name] = _OverrideState()
        logger.debug(f"Event override registered: {override.name}")

    # ---- 排程模式控制（ScheduleModeController 實作）----

    async def activate_schedule_mode(self, strategy: Strategy, *, description: str = "") -> None:
        """
        啟用排程模式（ScheduleModeController 實作）

        首次呼叫時註冊 ``__schedule__`` 模式並設為 base mode；
        後續呼叫更新策略，觸發 on_strategy_change。
        """
        mm = self._mode_manager
        if _SCHEDULE_MODE not in mm.registered_modes:
            mm.register(_SCHEDULE_MODE, strategy, ModePriority.SCHEDULE, description)
            await mm.add_base_mode(_SCHEDULE_MODE, source=SwitchSource.SCHEDULE)
        else:
            await mm.update_mode_strategy(
                _SCHEDULE_MODE,
                strategy,
                source=SwitchSource.SCHEDULE,
                description=description,
            )
            if _SCHEDULE_MODE not in mm.base_mode_names:
                await mm.add_base_mode(_SCHEDULE_MODE, source=SwitchSource.SCHEDULE)

    async def deactivate_schedule_mode(self) -> None:
        """
        停用排程模式（ScheduleModeController 實作）

        從 base mode 移除 ``__schedule__``。
        """
        mm = self._mode_manager
        if _SCHEDULE_MODE in mm.base_mode_names:
            await mm.remove_base_mode(_SCHEDULE_MODE)

    def trigger(self) -> None:
        """手動觸發策略執行"""
        self._executor.trigger()

    # ---- 生命週期 ----

    async def _on_start(self) -> None:
        """啟動系統控制器"""
        if self._data_feed is not None:
            self._data_feed.attach()
        if self._heartbeat is not None:
            await self._heartbeat.start()
        self._run_task = asyncio.create_task(self._executor.run())
        logger.info("SystemController started.")

    async def _on_stop(self) -> None:
        """停止系統控制器"""
        try:
            self._executor.stop()
            if self._run_task is not None:
                await self._run_task
                self._run_task = None
        finally:
            try:
                if self._heartbeat is not None:
                    await self._heartbeat.stop()
            finally:
                if self._data_feed is not None:
                    self._data_feed.detach()
        logger.info("SystemController stopped.")

    # ---- 內部流程 ----

    def _build_context(self) -> StrategyContext:
        """建構策略上下文，注入 system_alarm 旗標"""
        context = self._context_builder.build()

        # 檢查所有設備的告警狀態
        has_alarm = any(dev.is_protected for dev in self._registry.all_devices)

        # per_device 模式不觸發系統級告警（由 _handle_device_alarms 逐設備處理）
        if self._config.alarm_mode == "per_device":
            context.extra[self._config.system_alarm_key] = False
        else:
            context.extra[self._config.system_alarm_key] = has_alarm

        self._cached_context = context
        return context

    async def _on_command(self, command: Command) -> None:
        """命令回呼：套用保護鏈 → 處理告警 → 路由到設備"""
        # 取得最近的 context（由 executor 在 _execute_strategy 中呼叫 _build_context 後產生）
        context = self._cached_context
        if context is None:
            context = self._build_context()

        # 套用保護鏈
        result = self._protection_guard.apply(command, context)
        protected_command = result.protected_command

        # 評估事件驅動 overrides（包含自動停機）
        if self._event_overrides:
            await self._evaluate_event_overrides(context)

        # 路由到設備（is_protected 設備由 CommandRouter 防禦性跳過）
        if self._config.power_distributor is not None and self._config.capability_command_mappings:
            snapshots = self._build_device_snapshots()
            per_device = self._config.power_distributor.distribute(protected_command, snapshots)
            await self._command_router.route_per_device(protected_command, per_device)
        else:
            await self._command_router.route(protected_command)

        # 處理設備級告警（per_device 模式）
        if self._config.alarm_mode == "per_device":
            await self._handle_device_alarms()

    async def _evaluate_event_overrides(self, context: StrategyContext) -> None:
        """統一評估所有 EventDrivenOverride"""
        now = time.monotonic()

        for override in self._event_overrides:
            state = self._event_override_states.get(override.name)
            if state is None:
                continue

            should = override.should_activate(context)

            if should and not state.active:
                state.active = True
                state.deactivate_at = None
                try:
                    await self._mode_manager.push_override(override.name, source=SwitchSource.EVENT)
                    logger.warning(f"Event override activated: {override.name}")
                except (KeyError, ValueError):
                    pass

                # 向後相容：更新 _auto_stop_active
                if override.name == _AUTO_STOP_MODE:
                    self._auto_stop_active = True

            elif not should and state.active:
                if state.deactivate_at is None:
                    state.deactivate_at = now + override.cooldown_seconds

                if now >= state.deactivate_at:
                    state.active = False
                    state.deactivate_at = None
                    try:
                        await self._mode_manager.pop_override(override.name, source=SwitchSource.EVENT)
                        logger.info(f"Event override deactivated: {override.name}")
                    except KeyError:
                        pass

                    # 向後相容：更新 _auto_stop_active
                    if override.name == _AUTO_STOP_MODE:
                        self._auto_stop_active = False

    async def _handle_auto_stop(self, context: StrategyContext) -> None:
        """處理自動停機 override（已棄用，由 _evaluate_event_overrides 取代）"""
        await self._evaluate_event_overrides(context)

    async def _handle_device_alarms(self) -> None:
        """處理設備級告警：逐設備檢查，送關機指令或呼叫回呼"""
        for device in self._registry.all_devices:
            device_id = device.device_id
            if device.is_protected and device_id not in self._alarmed_devices:
                # 新增告警設備
                self._alarmed_devices.add(device_id)
                if self._config.on_device_alarm is not None:
                    await self._config.on_device_alarm(device)
                elif "stop" in getattr(device, "ACTIONS", {}):
                    await device.execute_action("stop")
                logger.warning(f"Device alarm activated: {device_id}")
            elif not device.is_protected and device_id in self._alarmed_devices:
                # 告警解除
                self._alarmed_devices.discard(device_id)
                if self._config.on_device_alarm_clear is not None:
                    await self._config.on_device_alarm_clear(device)
                logger.info(f"Device alarm cleared: {device_id}")

    def _build_device_snapshots(self) -> list[DeviceSnapshot]:
        """建構所有可用設備的狀態快照（供 PowerDistributor 使用）"""
        snapshots: list[DeviceSnapshot] = []
        for device in self._registry.all_devices:
            if not device.is_responsive or device.is_protected:
                continue
            metadata = self._registry.get_metadata(device.device_id)
            values = device.latest_values

            # 建構 capability slot → value 映射
            cap_values: dict[str, dict[str, Any]] = {}
            bindings = getattr(device, "capabilities", {})
            for cap_name, binding in bindings.items():
                slot_values: dict[str, Any] = {}
                for slot in binding.capability.read_slots:
                    point = binding.resolve(slot)
                    slot_values[slot] = values.get(point)
                cap_values[cap_name] = slot_values

            snapshots.append(
                DeviceSnapshot(
                    device_id=device.device_id,
                    metadata=metadata,
                    latest_values=values,
                    capabilities=cap_values,
                )
            )
        return snapshots

    def _resolve_strategy(self) -> Strategy | None:
        """根據 ModeManager 狀態解析當前應使用的策略"""
        mm = self._mode_manager
        if mm.active_override_names:
            return mm.effective_strategy  # 互斥 override
        base = mm.base_strategies
        if not base:
            return None
        if len(base) == 1:
            return base[0]
        if self._config.capacity_kva is not None:
            return CascadingStrategy(  # type: ignore[return-value]  # CascadingStrategy is structurally compatible
                base,
                CapacityConfig(self._config.capacity_kva),
                ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1),
            )
        return base[0]  # 無容量設定時 fallback 到最高優先權

    async def _on_strategy_change(self, old: Strategy | None, new: Strategy | None) -> None:
        """ModeManager 通知策略變更，統一走 _resolve_strategy"""
        resolved = self._resolve_strategy()
        logger.info(f"Strategy change: {old} -> {resolved}")
        await self._executor.set_strategy(resolved)

        # 依據策略的 suppress_heartbeat 控制心跳服務
        if self._heartbeat is not None and resolved is not None:
            if resolved.suppress_heartbeat:
                self._heartbeat.pause()
            else:
                self._heartbeat.resume()

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
    def alarmed_device_ids(self) -> set[str]:
        """當前處於告警狀態的設備 ID 集合"""
        return set(self._alarmed_devices)

    def health(self) -> HealthReport:
        """取得系統健康報告（聚合所有設備）"""
        children = [dev.health() for dev in self._registry.all_devices]
        if all(c.status == HealthStatus.HEALTHY for c in children):
            status = HealthStatus.HEALTHY
        elif any(c.status == HealthStatus.UNHEALTHY for c in children):
            status = HealthStatus.UNHEALTHY
        else:
            status = HealthStatus.DEGRADED
        return HealthReport(
            status=status,
            component="system_controller",
            details={"mode": self.effective_mode_name, "alarmed": list(self._alarmed_devices)},
            children=children,
        )

    @property
    def context_builder(self) -> ContextBuilder:
        """Context 建構器"""
        return self._context_builder

    @property
    def command_router(self) -> CommandRouter:
        """Command 路由器"""
        return self._command_router

    @property
    def orchestrator(self) -> SystemCommandOrchestrator:
        """系統指令編排器"""
        return self._orchestrator

    @property
    def heartbeat(self) -> HeartbeatService | None:
        """心跳服務"""
        return self._heartbeat

    @property
    def event_overrides(self) -> list[EventDrivenOverride]:
        """已註冊的事件驅動 override 列表"""
        return list(self._event_overrides)

    @property
    def auto_stop_active(self) -> bool:
        """自動停機是否啟動"""
        return self._auto_stop_active

    @property
    def config(self) -> SystemControllerConfig:
        """系統控制器配置"""
        return self._config

    @property
    def is_running(self) -> bool:
        """是否正在執行"""
        return self._run_task is not None and not self._run_task.done()
