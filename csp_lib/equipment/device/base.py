# =============== Equipment Device - Base ===============
#
# 非同步 Modbus 設備
#
# 整合讀寫、告警、事件的完整設備抽象

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable, Sequence

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
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    EVENT_READ_ERROR,
    EVENT_VALUE_CHANGE,
    AsyncHandler,
    ConnectedPayload,
    DeviceEventEmitter,
    DisconnectPayload,
    ReadCompletePayload,
    ReadErrorPayload,
    ValueChangePayload,
)
from .mixins import AlarmMixin, WriteMixin

if TYPE_CHECKING:
    from csp_lib.equipment.core import ReadPoint, WritePoint
    from csp_lib.modbus.clients.base import AsyncModbusClientBase


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

        # 告警管理
        self._alarm_manager = AlarmStateManager()
        self._alarm_evaluators = list(alarm_evaluators)
        for evaluator in self._alarm_evaluators:
            self._alarm_manager.register_alarms(evaluator.get_alarms())

        # 設備層級聚合處理
        self._aggregator_pipeline = aggregator_pipeline

        # 能力綁定
        self._capability_bindings: dict[str, CapabilityBinding] = {
            b.capability.name: b for b in capability_bindings
        }

        # 事件
        self._emitter = DeviceEventEmitter()

        # 設備狀態
        self._latest_values: dict[str, Any] = {}
        self._client_connected = False  # Socket 層級：client.connect() 是否成功
        self._device_responsive = False  # 通訊層級：設備是否有回應
        self._consecutive_failures = 0  # 連續讀取失敗次數
        self._last_failure_time: float | None = None  # 最後一次讀取失敗的時間（monotonic）
        self._stop_event = asyncio.Event()
        self._read_task: asyncio.Task[None] | None = None

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

    def remove_capability(self, capability: Capability | str) -> None:
        """動態移除能力綁定（執行期）"""
        name = capability.name if isinstance(capability, Capability) else capability
        self._capability_bindings.pop(name, None)

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
        await self.stop()
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
                self._client_connected = True
                # 注意：_device_responsive 保持 False，等讀取成功後才設為 True 並發送 EVENT_CONNECTED
                self._consecutive_failures = 0
            except DeviceConnectionError:
                self._last_failure_time = time.monotonic()
                raise
            except Exception as e:
                self._last_failure_time = time.monotonic()
                raise DeviceConnectionError(self._config.device_id, f"重連失敗: {e}") from e

        start_time = time.monotonic()

        try:
            values = await self._read_all()
            self._consecutive_failures = 0
            self._last_failure_time = None

            # 設備恢復回應
            if not self._device_responsive:
                self._device_responsive = True
                await self._emitter.emit_await(
                    EVENT_CONNECTED,
                    ConnectedPayload(device_id=self._config.device_id),
                )

            # 更新值並發送變更事件
            await self._process_values(values)

            # 執行告警評估
            await self._evaluate_alarm(values)

            duration_ms = (time.monotonic() - start_time) * 1000
            self._emitter.emit(
                EVENT_READ_COMPLETE,
                ReadCompletePayload(
                    device_id=self._config.device_id,
                    values=values,
                    duration_ms=duration_ms,
                ),
            )

            return values

        except CommunicationError as e:
            # 已有正確 device_id 的 CommunicationError 直接傳播
            if e.device_id != "unknown":
                self._handle_read_failure(str(e))
                await self._check_disconnect_threshold(str(e))
                raise
            # transport 層的 "unknown" device_id → 替換為正確 device_id
            err = CommunicationError(self._config.device_id, str(e))
            err.__cause__ = e.__cause__
            self._handle_read_failure(str(err))
            await self._check_disconnect_threshold(str(err))
            raise err from e.__cause__
        except Exception as e:
            err = CommunicationError(self._config.device_id, f"讀取失敗: {e}")
            self._handle_read_failure(str(err))
            await self._check_disconnect_threshold(str(err))
            raise err from e

    # =============== Events ================

    def on(self, event: str, handler: AsyncHandler) -> Callable[[], None]:
        """註冊事件處理器"""
        return self._emitter.on(event, handler)

    def emit(self, event: str, payload: Any) -> None:
        """發送事件（非阻塞）"""
        self._emitter.emit(event, payload)

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
        """讀取循環（含自動重連）"""
        interval = self._config.read_interval
        reconnect_interval = self._config.reconnect_interval

        while not self._stop_event.is_set():
            start_time = time.monotonic()

            # 未連線時嘗試重連
            if not self._client_connected:
                try:
                    await self._client.connect()
                    self._client_connected = True
                    self._device_responsive = True
                    self._consecutive_failures = 0
                    await self._emitter.emit_await(EVENT_CONNECTED, ConnectedPayload(device_id=self._config.device_id))
                except DeviceConnectionError:
                    # 重連失敗，等待後重試
                    await asyncio.sleep(reconnect_interval)
                    continue
                except Exception:
                    # 重連失敗，等待後重試
                    await asyncio.sleep(reconnect_interval)
                    continue

            try:
                await self.read_once()
            except Exception:
                pass  # read_once 已處理錯誤事件

            elapsed = time.monotonic() - start_time
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

    def _handle_read_failure(self, error_msg: str) -> None:
        """處理讀取失敗：累加計數 + 記錄失敗時間 + 發送錯誤事件"""
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()
        self._emitter.emit(
            EVENT_READ_ERROR,
            ReadErrorPayload(
                device_id=self._config.device_id,
                error=error_msg,
                consecutive_failures=self._consecutive_failures,
            ),
        )

    async def _check_disconnect_threshold(self, error_msg: str) -> None:
        """達到斷線閾值時標記設備無回應"""
        if self._consecutive_failures >= self._config.disconnect_threshold and self._device_responsive:
            self._device_responsive = False
            await self._emitter.emit_await(
                EVENT_DISCONNECTED,
                DisconnectPayload(
                    device_id=self._config.device_id,
                    reason=error_msg,
                    consecutive_failures=self._consecutive_failures,
                ),
            )

    async def _process_values(self, values: dict[str, Any]) -> None:
        """處理讀取到的值，發送變更事件"""
        for name, new_value in values.items():
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
        self._latest_values.update(values)

    # =============== Magic Methods =========

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} id={self.device_id} connected={self.is_connected} responsive={self.is_responsive}>"

    def __repr__(self) -> str:
        return self.__str__()
