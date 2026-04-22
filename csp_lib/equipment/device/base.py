# =============== Equipment Device - Base ===============
#
# 非同步 Modbus 設備
#
# 整合讀寫、告警、事件的完整設備抽象

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Sequence

from csp_lib.core import get_logger
from csp_lib.core._numeric import is_non_finite_float
from csp_lib.core._time_anchor import next_tick_delay
from csp_lib.core.errors import CommunicationError, ConfigurationError, DeviceConnectionError
from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.equipment.alarm import AlarmEvaluator, AlarmStateManager
from csp_lib.equipment.processing import AggregatorPipeline
from csp_lib.equipment.transport import (
    GroupReader,
    PointGrouper,
    ReadScheduler,
    ValidatedWriter,
)

from .capability import Capability, CapabilityBinding
from .config import DeviceConfig
from .events import (
    EVENT_CAPABILITY_ADDED,
    EVENT_CAPABILITY_REMOVED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_POINT_TOGGLED,
    EVENT_READ_COMPLETE,
    EVENT_READ_ERROR,
    EVENT_RECONFIGURED,
    EVENT_RESTARTED,
    EVENT_VALUE_CHANGE,
    AsyncHandler,
    CapabilityChangedPayload,
    ConnectedPayload,
    DeviceEventEmitter,
    DisconnectPayload,
    PointToggledPayload,
    ReadCompletePayload,
    ReadErrorPayload,
    ReconfiguredPayload,
    RestartedPayload,
    ValueChangePayload,
)
from .mixins import AlarmMixin, WriteMixin

if TYPE_CHECKING:
    from csp_lib.equipment.core import PointMetadata, ReadPoint, WritePoint
    from csp_lib.modbus.clients.base import AsyncModbusClientBase
    from csp_lib.modbus.types import ModbusDataType

    from .action import DOActionConfig

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PointInfo:
    """點位詳細資訊"""

    name: str
    address: int
    data_type: ModbusDataType
    direction: str  # "read" | "write" | "read_write"
    enabled: bool
    read_group: str
    metadata: PointMetadata | None


@dataclass(frozen=True, slots=True)
class ReconfigureSpec:
    """重新配置規格"""

    always_points: Sequence[ReadPoint] | None = None
    rotating_points: Sequence[Sequence[ReadPoint]] | None = None
    write_points: Sequence[WritePoint] | None = None
    alarm_evaluators: Sequence[AlarmEvaluator] | None = None
    capability_bindings: Sequence[CapabilityBinding] | None = None


class AsyncModbusDevice(AlarmMixin, WriteMixin):
    """
    非同步 Modbus 設備

    整合讀寫、告警、事件的完整設備抽象。

    特點：
        - 定期讀取循環
        - 告警狀態管理（含遲滯）
        - 事件驅動通知
        - 動態點位排程
        - 設備寫入管理
        - 高階 Action 指令支援

    Class Attributes:
        ACTIONS: 動作名稱對應方法名稱的映射，子類別可覆寫。
            例如: {"start": "set_generator_on", "stop": "set_generator_off"}
    """

    # 子類別可覆寫，定義支援的 action -> method 映射
    ACTIONS: dict[str, str] = {}

    def __init__(
        self,
        config: DeviceConfig,
        client: AsyncModbusClientBase,
        always_points: Sequence[ReadPoint] = (),
        rotating_points: Sequence[Sequence[ReadPoint]] = (),
        write_points: Sequence[WritePoint] = (),
        alarm_evaluators: Sequence[AlarmEvaluator] = (),
        aggregator_pipeline: AggregatorPipeline | None = None,
        capability_bindings: Sequence[CapabilityBinding] = (),
    ):
        self._config = config
        self._client = client

        # 儲存原始點位定義
        self._read_points_always: tuple[ReadPoint, ...] = tuple(always_points)
        self._read_points_rotating: tuple[tuple[ReadPoint, ...], ...] = tuple(tuple(pts) for pts in rotating_points)

        # ReadPoint lookup（供 reject_non_finite 等 per-point 策略查詢）
        self._read_point_lookup: dict[str, ReadPoint] = self._build_read_point_lookup()
        self._has_any_reject_non_finite: bool = any(p.reject_non_finite for p in self._read_point_lookup.values())

        # 建立排程器（自動分組）
        self._grouper = PointGrouper()
        self._scheduler = ReadScheduler(
            always_groups=self._grouper.group(list(always_points)),
            rotating_groups=[self._grouper.group(list(points)) for points in rotating_points],
        )

        # 通訊用元件
        self._reader = GroupReader(
            client=client,
            unit_id=config.unit_id,
            address_offset=config.address_offset,
        )
        self._writer = ValidatedWriter(
            client=client,
            unit_id=config.unit_id,
            address_offset=config.address_offset,
        )

        # 寫入點位查詢表
        self._write_points = {write_point.name: write_point for write_point in write_points}

        # 計算此設備實際觸及的 unit_id 集合（sentinel resolve：None → config.unit_id）
        self._used_unit_ids: frozenset[int] = self._compute_used_unit_ids()

        # 告警管理
        self._alarm_manager = AlarmStateManager()
        self._alarm_evaluators = list(alarm_evaluators)
        for evaluator in self._alarm_evaluators:
            self._alarm_manager.register_alarms(evaluator.get_alarms())

        # 設備層級聚合處理
        self._aggregator_pipeline = aggregator_pipeline

        # 能力綁定
        self._capability_bindings: dict[str, CapabilityBinding] = {b.capability.name: b for b in capability_bindings}

        # 點位開關
        self._disabled_points: set[str] = set()

        # 事件
        self._emitter = DeviceEventEmitter()

        # 設備狀態
        self._latest_values: dict[str, Any] = {}
        self._client_connected = False  # Socket 層級：client.connect() 是否成功
        self._device_responsive = False  # 通訊層級：設備是否有回應
        self._consecutive_failures = 0  # 連續讀取失敗次數
        self._last_failure_time: float | None = None  # 最後一次讀取失敗的時間（monotonic）
        self._status_lock = asyncio.Lock()  # 保護狀態欄位的非同步鎖
        self._stop_event = asyncio.Event()
        self._read_task: asyncio.Task[None] | None = None

        # DO 動作（WriteMixin）
        self._do_actions: dict[str, DOActionConfig] = {}
        self._pulse_tasks: list[asyncio.Task[None]] = []

    # =============== Properties ===============

    @property
    def device_id(self) -> str:
        """設備唯一識別碼(DB/通訊用)"""
        return self._config.device_id

    @property
    def is_connected(self) -> bool:
        """Client 是否已連線（Socket 層級）"""
        return self._client_connected

    @property
    def is_responsive(self) -> bool:
        """設備是否有回應（通訊層級）"""
        return self._device_responsive

    @property
    def is_disconnected(self) -> bool:
        """Client 是否已斷線"""
        return not self._client_connected

    @property
    def is_unreachable(self) -> bool:
        """設備是否無回應（連續失敗達閾值）"""
        return self._client_connected and not self._device_responsive

    @property
    def is_healthy(self) -> bool:
        """設備是否健康"""
        return self.is_connected and self.is_responsive and not self.is_protected

    @property
    def latest_values(self) -> dict[str, Any]:
        """最新讀取值"""
        return self._latest_values.copy()

    @property
    def is_running(self) -> bool:
        """讀取循環是否運行中"""
        return self._read_task is not None and not self._read_task.done()

    @property
    def should_attempt_read(self) -> bool:
        """
        是否應嘗試讀取（用於群組讀取排程）

        回應中的設備或尚未失敗的設備永遠回傳 True。
        無回應的設備在超過 reconnect_interval 後才回傳 True，避免 timeout 阻塞群組讀取。
        """
        if self._device_responsive:
            return True
        if self._last_failure_time is None:
            return True
        return (time.monotonic() - self._last_failure_time) >= self._config.reconnect_interval

    # =============== Capabilities ===============

    @property
    def capabilities(self) -> dict[str, CapabilityBinding]:
        """所有已綁定的能力"""
        return dict(self._capability_bindings)

    def has_capability(self, capability: Capability | str) -> bool:
        """檢查設備是否具備指定能力"""
        name = capability.name if isinstance(capability, Capability) else capability
        return name in self._capability_bindings

    def get_binding(self, capability: Capability | str) -> CapabilityBinding | None:
        """取得能力綁定，不存在回傳 None"""
        name = capability.name if isinstance(capability, Capability) else capability
        return self._capability_bindings.get(name)

    def resolve_point(self, capability: Capability | str, slot: str) -> str:
        """
        解析能力的語意插槽到實際點位名稱

        Args:
            capability: 能力定義或名稱
            slot: 語意插槽名稱

        Returns:
            實際點位名稱

        Raises:
            ConfigurationError: 設備不具備該能力
            KeyError: slot 不存在
        """
        binding = self.get_binding(capability)
        if binding is None:
            name = capability.name if isinstance(capability, Capability) else capability
            raise ConfigurationError(f"Device '{self.device_id}' has no capability '{name}'")
        return binding.resolve(slot)

    def add_capability(self, binding: CapabilityBinding) -> None:
        """動態新增能力綁定（執行期）"""
        self._capability_bindings[binding.capability.name] = binding
        self._emitter.emit(
            EVENT_CAPABILITY_ADDED,
            CapabilityChangedPayload(device_id=self._config.device_id, capability_name=binding.capability.name),
        )

    def remove_capability(self, capability: Capability | str) -> None:
        """動態移除能力綁定（執行期）"""
        name = capability.name if isinstance(capability, Capability) else capability
        if name in self._capability_bindings:
            self._capability_bindings.pop(name, None)
            self._emitter.emit(
                EVENT_CAPABILITY_REMOVED,
                CapabilityChangedPayload(device_id=self._config.device_id, capability_name=name),
            )

    # =============== Point Toggle ===============

    def enable_point(self, name: str) -> None:
        """啟用點位"""
        if name not in self.all_point_names:
            raise KeyError(f"點位 '{name}' 不存在")
        self._disabled_points.discard(name)
        self._emitter.emit(
            EVENT_POINT_TOGGLED,
            PointToggledPayload(device_id=self._config.device_id, point_name=name, enabled=True),
        )

    def disable_point(self, name: str) -> None:
        """停用點位（讀取值不更新、告警不評估、寫入被拒）"""
        if name not in self.all_point_names:
            raise KeyError(f"點位 '{name}' 不存在")
        self._disabled_points.add(name)
        self._emitter.emit(
            EVENT_POINT_TOGGLED,
            PointToggledPayload(device_id=self._config.device_id, point_name=name, enabled=False),
        )

    def is_point_enabled(self, name: str) -> bool:
        """檢查點位是否啟用"""
        return name not in self._disabled_points

    # =============== Point Query ===============

    @property
    def read_points(self) -> tuple[ReadPoint, ...]:
        """所有固定讀取點位"""
        return self._read_points_always

    @property
    def rotating_read_points(self) -> tuple[tuple[ReadPoint, ...], ...]:
        """所有輪替讀取點位"""
        return self._read_points_rotating

    @property
    def write_point_names(self) -> list[str]:
        """所有寫入點位名稱"""
        return list(self._write_points.keys())

    @property
    def all_point_names(self) -> set[str]:
        """所有點位名稱（讀+寫）"""
        names = {p.name for p in self._read_points_always}
        for group in self._read_points_rotating:
            names.update(p.name for p in group)
        names.update(self._write_points.keys())
        return names

    @property
    def disabled_points(self) -> frozenset[str]:
        """目前被停用的點位"""
        return frozenset(self._disabled_points)

    @property
    def used_unit_ids(self) -> frozenset[int]:
        """此設備實際觸及的 Modbus unit_id 集合（SMA multi-unit 場景用）。

        包含 ``DeviceConfig.unit_id`` 以及任何 ``ReadPoint`` / ``WritePoint``
        以 ``unit_id`` 欄位覆寫的值。``None`` sentinel 已 resolve 為
        ``config.unit_id``，故集合內皆為具體 int。

        Returns:
            frozenset[int]: 至少包含 ``{config.unit_id}``
        """
        return self._used_unit_ids

    def get_point_info(self) -> list[PointInfo]:
        """取得所有點位的詳細資訊（含啟用狀態）"""
        infos: list[PointInfo] = []
        write_names = set(self._write_points.keys())

        # 讀取點位
        for point in self._read_points_always:
            direction = "read_write" if point.name in write_names else "read"
            infos.append(
                PointInfo(
                    name=point.name,
                    address=point.address,
                    data_type=point.data_type,
                    direction=direction,
                    enabled=point.name not in self._disabled_points,
                    read_group=point.read_group,
                    metadata=point.metadata,
                )
            )

        seen_names = {p.name for p in self._read_points_always}
        for group in self._read_points_rotating:
            for point in group:
                if point.name in seen_names:
                    continue
                seen_names.add(point.name)
                direction = "read_write" if point.name in write_names else "read"
                infos.append(
                    PointInfo(
                        name=point.name,
                        address=point.address,
                        data_type=point.data_type,
                        direction=direction,
                        enabled=point.name not in self._disabled_points,
                        read_group=point.read_group,
                        metadata=point.metadata,
                    )
                )

        # 僅寫入的點位
        for name, wp in self._write_points.items():
            if name not in seen_names:
                infos.append(
                    PointInfo(
                        name=wp.name,
                        address=wp.address,
                        data_type=wp.data_type,
                        direction="write",
                        enabled=wp.name not in self._disabled_points,
                        read_group="",
                        metadata=wp.metadata,
                    )
                )

        return infos

    # =============== Reconfigure ===============

    async def reconfigure(self, spec: ReconfigureSpec) -> None:
        """
        動態重新配置點位

        Args:
            spec: 重新配置規格，None 欄位表示保持不變
        """
        was_running = self.is_running
        if was_running:
            await self.stop()

        changed_sections: list[str] = []

        try:
            if spec.always_points is not None or spec.rotating_points is not None:
                if spec.always_points is not None:
                    self._read_points_always = tuple(spec.always_points)
                    changed_sections.append("always_points")
                if spec.rotating_points is not None:
                    self._read_points_rotating = tuple(tuple(pts) for pts in spec.rotating_points)
                    changed_sections.append("rotating_points")
                self._scheduler.update_groups(
                    always_groups=self._grouper.group(list(self._read_points_always)),
                    rotating_groups=[self._grouper.group(list(pts)) for pts in self._read_points_rotating],
                )
                # 重建 ReadPoint lookup（含 reject_non_finite 策略）
                self._read_point_lookup = self._build_read_point_lookup()
                self._has_any_reject_non_finite = any(p.reject_non_finite for p in self._read_point_lookup.values())

            if spec.write_points is not None:
                self._write_points = {wp.name: wp for wp in spec.write_points}
                changed_sections.append("write_points")

            if spec.alarm_evaluators is not None:
                old_states = self._alarm_manager.export_states()
                self._alarm_manager = AlarmStateManager()
                self._alarm_evaluators = list(spec.alarm_evaluators)
                for evaluator in self._alarm_evaluators:
                    self._alarm_manager.register_alarms(evaluator.get_alarms())
                self._alarm_manager.import_states(old_states)
                changed_sections.append("alarm_evaluators")

            if spec.capability_bindings is not None:
                self._capability_bindings = {b.capability.name: b for b in spec.capability_bindings}
                changed_sections.append("capability_bindings")

            # 清理不再存在的 disabled_points
            valid_names = self.all_point_names
            self._disabled_points = self._disabled_points & valid_names

            # 點位清單若有變動，重算 used_unit_ids
            if any(s in changed_sections for s in ("always_points", "rotating_points", "write_points")):
                self._used_unit_ids = self._compute_used_unit_ids()
        finally:
            if was_running:
                await self.start()

        self._emitter.emit(
            EVENT_RECONFIGURED,
            ReconfiguredPayload(device_id=self._config.device_id, changed_sections=tuple(changed_sections)),
        )

    async def restart(self) -> None:
        """重啟讀取迴圈"""
        await self.stop()
        await self.start()
        self._emitter.emit(
            EVENT_RESTARTED,
            RestartedPayload(device_id=self._config.device_id),
        )

    # =============== Health ===============

    def health(self) -> HealthReport:
        """取得設備健康報告"""
        if self.is_healthy:
            status = HealthStatus.HEALTHY
        elif self.is_connected:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY
        return HealthReport(
            status=status,
            component=f"device:{self.device_id}",
            details={
                "connected": self.is_connected,
                "responsive": self.is_responsive,
                "protected": self.is_protected,
                "active_alarms": len(self.active_alarms),
            },
        )

    # =============== Lifecycle ===============

    async def connect(self) -> None:
        """
        連線設備

        Raises:
            DeviceConnectionError: 連線失敗
        """
        try:
            await self._client.connect()
        except Exception as e:
            raise DeviceConnectionError(self._config.device_id, f"連線失敗: {e}") from e
        await self._emitter.start()  # 啟動事件處理 worker
        async with self._status_lock:
            self._client_connected = True
            self._device_responsive = True  # 假設連線成功即可回應，讀取失敗會更新
            self._consecutive_failures = 0
        await self._emitter.emit_await(EVENT_CONNECTED, ConnectedPayload(device_id=self._config.device_id))

    async def disconnect(self) -> None:
        """
        斷線設備

        Raises:
            DeviceConnectionError: 斷線失敗
        """
        await self.stop()
        if self._client_connected:
            try:
                await self._client.disconnect()
            except Exception as e:
                raise DeviceConnectionError(self._config.device_id, f"斷線失敗: {e}") from e
            async with self._status_lock:
                self._client_connected = False
                self._device_responsive = False
                self._consecutive_failures = 0
                self._last_failure_time = None
            await self._emitter.emit_await(
                EVENT_DISCONNECTED,
                DisconnectPayload(device_id=self._config.device_id, reason="normal", consecutive_failures=0),
            )
            await self._emitter.stop()  # 停止事件處理 worker

    async def start(self) -> None:
        """
        啟動定期讀取循環

        即使未連線也可啟動，read_loop 會自動嘗試連線。
        """
        if self._read_task is not None and not self._read_task.done():
            return

        # 確保 emitter 已啟動
        await self._emitter.start()

        self._stop_event.clear()
        self._read_task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """
        停止定期讀取循環
        """
        await self.cancel_pending_pulses()
        self._stop_event.set()
        if self._read_task is not None and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

    async def __aenter__(self) -> AsyncModbusDevice:
        try:
            await self.connect()
            await self.start()
            return self
        except Exception:
            await self.disconnect()  # 清理
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            await self.stop()
        finally:
            await self.disconnect()

    # =============== Transport ===============

    async def read_once(self) -> dict[str, Any]:
        """
        執行一次完整的讀取流程

        包含：連線檢查（自動重連）、讀取點位、更新狀態、處理值變更事件、評估告警。
        適合不需要定期讀取的場景（如：手動觸發讀取、群組順序讀取）。

        Returns:
            讀取到的點位值字典

        Raises:
            Exception: 讀取失敗時拋出例外（會發送 EVENT_READ_ERROR）
        """
        # 未連線時嘗試重連
        if not self._client_connected:
            try:
                await self._client.connect()
                async with self._status_lock:
                    self._client_connected = True
                    # 注意：_device_responsive 保持 False，等讀取成功後才設為 True 並發送 EVENT_CONNECTED
                    self._consecutive_failures = 0
            except DeviceConnectionError:
                async with self._status_lock:
                    self._last_failure_time = time.monotonic()
                raise
            except Exception as e:
                async with self._status_lock:
                    self._last_failure_time = time.monotonic()
                raise DeviceConnectionError(self._config.device_id, f"重連失敗: {e}") from e

        start_time = time.monotonic()

        try:
            values = await self._read_all()

            # 更新狀態（成功路徑）
            async with self._status_lock:
                self._consecutive_failures = 0
                self._last_failure_time = None
                was_unresponsive = not self._device_responsive
                if was_unresponsive:
                    self._device_responsive = True

            # 設備恢復回應（在鎖外發送事件，避免死鎖）
            if was_unresponsive:
                await self._emitter.emit_await(
                    EVENT_CONNECTED,
                    ConnectedPayload(device_id=self._config.device_id),
                )

            # 更新值並發送變更事件
            await self._process_values(values)

            # 若點位啟用 reject_non_finite 且本輪值非有限，下游（告警評估、
            # READ_COMPLETE payload、回傳值）應看到舊 latest。
            effective_values = self._resolve_effective_values(values)

            # 執行告警評估（使用 effective_values，避免 NaN 讓閾值比較失效）
            await self._evaluate_alarm(effective_values)

            duration_ms = (time.monotonic() - start_time) * 1000
            self._emitter.emit(
                EVENT_READ_COMPLETE,
                ReadCompletePayload(
                    device_id=self._config.device_id,
                    values=effective_values,
                    duration_ms=duration_ms,
                ),
            )

            return effective_values

        except CommunicationError as e:
            # 已有正確 device_id 的 CommunicationError 直接傳播
            if e.device_id != "unknown":
                await self._handle_read_failure(str(e))
                await self._check_disconnect_threshold(str(e))
                raise
            # transport 層的 "unknown" device_id → 替換為正確 device_id
            err = CommunicationError(self._config.device_id, str(e))
            err.__cause__ = e.__cause__
            await self._handle_read_failure(str(err))
            await self._check_disconnect_threshold(str(err))
            raise err from e.__cause__
        except Exception as e:
            err = CommunicationError(self._config.device_id, f"讀取失敗: {e}")
            await self._handle_read_failure(str(err))
            await self._check_disconnect_threshold(str(err))
            raise err from e

    # =============== Events ================

    def on(self, event: str, handler: AsyncHandler) -> Callable[[], None]:
        """註冊事件處理器"""
        return self._emitter.on(event, handler)

    def emit(self, event: str, payload: Any) -> None:
        """發送事件（非阻塞）"""
        self._emitter.emit(event, payload)

    async def ensure_event_loop_started(self) -> None:
        """
        確保內部事件 emitter worker 已啟動（idempotent）。

        Standalone 模式由 ``start()`` 間接啟動；group 模式由 ``DeviceManager``
        在連線後呼叫此方法，取代舊的 ``device._emitter.start()`` 私有存取。
        多次呼叫安全（``DeviceEventEmitter.start()`` 內部已 idempotent）。
        """
        await self._emitter.start()

    async def ensure_event_loop_stopped(self) -> None:
        """
        確保內部事件 emitter worker 已停止（對稱 ``ensure_event_loop_started``）。

        用於 group 模式下 ``DeviceManager`` 在 disconnect 前關閉事件 worker。
        多次呼叫安全（``DeviceEventEmitter.stop()`` 內部已 idempotent）。
        """
        await self._emitter.stop()

    # =============== Private ===============

    async def _read_all(self) -> dict[str, Any]:
        """讀取所有點位（使用排程器預計算分組）"""
        groups = self._scheduler.get_next_groups()
        if not groups:
            return {}
        raw_values = await self._reader.read_many(groups)
        if self._aggregator_pipeline:
            return self._aggregator_pipeline.process(raw_values)
        return raw_values

    async def _read_loop(self) -> None:
        """讀取循環（含自動重連）。

        採用絕對時間錨定（absolute time anchoring）避免時序漂移：
        以 ``next_tick_delay`` helper 統一計算 sleep delay，補償 read 耗時。
        重連成功後重設 anchor 與 completed 計數，避免斷線期間錯過的 tick
        在重連瞬間 burst catch-up 壓垮設備。
        """
        interval = self._config.read_interval
        reconnect_interval = self._config.reconnect_interval

        anchor = time.monotonic()
        n = 0

        while not self._stop_event.is_set():
            # 未連線時嘗試重連
            if not self._client_connected:
                try:
                    await self._client.connect()
                    async with self._status_lock:
                        self._client_connected = True
                        self._device_responsive = True
                        self._consecutive_failures = 0
                    await self._emitter.emit_await(EVENT_CONNECTED, ConnectedPayload(device_id=self._config.device_id))
                    # 重連成功後重設 anchor 與計數，避免 burst catch-up
                    anchor = time.monotonic()
                    n = 0
                except DeviceConnectionError:
                    # 重連失敗，等待後重試
                    await asyncio.sleep(reconnect_interval)
                    continue
                except Exception as e:
                    # 重連失敗，等待後重試
                    logger.warning(f"[{self._config.device_id}] Reconnect failed: {e}")
                    await asyncio.sleep(reconnect_interval)
                    continue

            try:
                await self.read_once()
            except Exception as e:
                logger.warning(f"[{self._config.device_id}] Read loop error: {e}")

            delay, anchor, n = next_tick_delay(anchor, n, interval)
            await asyncio.sleep(delay)

    async def _handle_read_failure(self, error_msg: str) -> None:
        """處理讀取失敗：累加計數 + 記錄失敗時間 + 發送錯誤事件"""
        async with self._status_lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.monotonic()
            failures = self._consecutive_failures
        self._emitter.emit(
            EVENT_READ_ERROR,
            ReadErrorPayload(
                device_id=self._config.device_id,
                error=error_msg,
                consecutive_failures=failures,
            ),
        )

    async def _check_disconnect_threshold(self, error_msg: str) -> None:
        """達到斷線閾值時標記設備無回應"""
        failures = 0
        async with self._status_lock:
            should_disconnect = (
                self._consecutive_failures >= self._config.disconnect_threshold and self._device_responsive
            )
            if should_disconnect:
                self._device_responsive = False
                failures = self._consecutive_failures

        if should_disconnect:
            await self._emitter.emit_await(
                EVENT_DISCONNECTED,
                DisconnectPayload(
                    device_id=self._config.device_id,
                    reason=error_msg,
                    consecutive_failures=failures,
                ),
            )

    async def _process_values(self, values: dict[str, Any]) -> None:
        """處理讀取到的值，發送變更事件（跳過 disabled 點位）。

        若 ReadPoint 設定 ``reject_non_finite=True`` 且新值為非有限 float
        （NaN / +Inf / -Inf），此點位：

          - 保留 ``_latest_values`` 中的舊值（不覆寫）
          - log WARNING
          - 不發送 ``EVENT_VALUE_CHANGE``
        """
        for name, new_value in values.items():
            if name in self._disabled_points:
                continue
            try:
                if self._should_reject_non_finite(name, new_value):
                    logger.warning(
                        f"[{self._config.device_id}] Point '{name}' got non-finite value "
                        f"{new_value!r}, keeping previous latest value (reject_non_finite=True)"
                    )
                    continue
                old_value = self._latest_values.get(name)
                if old_value != new_value:
                    self._emitter.emit(
                        EVENT_VALUE_CHANGE,
                        ValueChangePayload(
                            device_id=self._config.device_id,
                            point_name=name,
                            old_value=old_value,
                            new_value=new_value,
                        ),
                    )
                self._latest_values[name] = new_value
            except Exception as e:
                logger.warning(f"[{self._config.device_id}] Event processing failed for point '{name}': {e}")

    def _compute_used_unit_ids(self) -> frozenset[int]:
        """計算此設備實際觸及的 unit_id 集合。

        Point-level ``unit_id=None`` 視為使用 device 預設（``config.unit_id``），
        故結果一定包含 ``config.unit_id``；非 None 的 override 額外加入集合。
        """
        used: set[int] = {self._config.unit_id}
        for point in self._read_points_always:
            if point.unit_id is not None:
                used.add(point.unit_id)
        for group in self._read_points_rotating:
            for point in group:
                if point.unit_id is not None:
                    used.add(point.unit_id)
        for wp in self._write_points.values():
            if wp.unit_id is not None:
                used.add(wp.unit_id)
        return frozenset(used)

    def _build_read_point_lookup(self) -> dict[str, ReadPoint]:
        """建立 point_name → ReadPoint 的查詢表，供 per-point 策略使用。

        同名點位以 always_points 為優先，rotating 中若有重複名稱不會覆寫。
        """
        lookup: dict[str, ReadPoint] = {p.name: p for p in self._read_points_always}
        for group in self._read_points_rotating:
            for point in group:
                lookup.setdefault(point.name, point)
        return lookup

    def _should_reject_non_finite(self, name: str, value: Any) -> bool:
        """判斷某點位的新值是否應被 reject。

        Args:
            name: 點位名稱
            value: 讀取到的原始值

        Returns:
            True 代表該點位啟用 ``reject_non_finite`` 且 value 為非有限 float，
            呼叫端應跳過該點位的 latest 更新與事件發送。
        """
        if not self._has_any_reject_non_finite:
            return False
        point = self._read_point_lookup.get(name)
        if point is None or not point.reject_non_finite:
            return False
        return is_non_finite_float(value)

    def _resolve_effective_values(self, values: dict[str, Any]) -> dict[str, Any]:
        """將 reject_non_finite 命中的點位替換為 ``_latest_values`` 中的舊值。

        供 ``read_once`` 輸出給下游（告警評估、``EVENT_READ_COMPLETE`` payload、
        回傳值）的統一視圖。未命中 reject 的點位原值傳遞；命中者若有舊 latest
        則取舊值，否則仍保留原始非有限值（首輪無歷史可退回）。

        無任何點位開啟 reject_non_finite 時走快速路徑直接回傳原 dict，
        避免每 read cycle 多做一次 O(N) 複製。
        """
        if not self._has_any_reject_non_finite:
            return values
        effective: dict[str, Any] = {}
        for name, value in values.items():
            if self._should_reject_non_finite(name, value) and name in self._latest_values:
                effective[name] = self._latest_values[name]
            else:
                effective[name] = value
        return effective

    # =============== Magic Methods =========

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} id={self.device_id} connected={self.is_connected} responsive={self.is_responsive}>"

    def __repr__(self) -> str:
        return self.__str__()


__all__ = ["AsyncModbusDevice", "PointInfo", "ReconfigureSpec"]
