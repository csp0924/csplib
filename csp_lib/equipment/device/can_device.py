# =============== Equipment Device - AsyncCANDevice ===============
#
# 非同步 CAN 設備
#
# 整合 Frame Buffer (TX) + 接收解析 (RX) + 定期發送 + 事件系統

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from csp_lib.can.clients.base import AsyncCANClientBase
from csp_lib.can.config import CANFrame
from csp_lib.core import get_logger
from csp_lib.core._time_anchor import next_tick_delay
from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.equipment.alarm import AlarmEvaluator, AlarmStateManager
from csp_lib.equipment.processing import AggregatorPipeline
from csp_lib.equipment.processing.can_encoder import (
    CANFrameBuffer,
    CANSignalDefinition,
    FrameBufferConfig,
)
from csp_lib.equipment.processing.can_parser import CANFrameParser
from csp_lib.equipment.transport.periodic_sender import PeriodicFrameConfig, PeriodicSendScheduler
from csp_lib.equipment.transport.writer import WriteResult, WriteStatus

from .capability import Capability, CapabilityBinding
from .config import DeviceConfig
from .events import (
    EVENT_CAPABILITY_ADDED,
    EVENT_CAPABILITY_REMOVED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    EVENT_VALUE_CHANGE,
    EVENT_WRITE_COMPLETE,
    EVENT_WRITE_ERROR,
    AsyncHandler,
    CapabilityChangedPayload,
    ConnectedPayload,
    DeviceEventEmitter,
    DisconnectPayload,
    ReadCompletePayload,
    ValueChangePayload,
    WriteCompletePayload,
    WriteErrorPayload,
)
from .mixins import AlarmMixin

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CANRxFrameDefinition:
    """
    CAN 接收訊框定義

    Attributes:
        can_id: 要監聽的 CAN ID
        parser: 訊框解析器
        is_periodic: 是否為定期回報訊框（True=被動監聽，False=請求-回應）
        request_data: 請求資料（僅用於 is_periodic=False）
    """

    can_id: int
    parser: CANFrameParser
    is_periodic: bool = True
    request_data: bytes = b""


class AsyncCANDevice(AlarmMixin):
    """
    非同步 CAN 設備

    整合 Frame Buffer (TX) + 接收解析 (RX) + 定期發送 + 事件系統。

    三種操作模式：
        - 被動監聯：rx_frame_definitions 中 is_periodic=True 的訊框
        - 主動控制：tx_signals + tx_periodic_configs
        - 請求-回應：rx_frame_definitions 中 is_periodic=False 的訊框

    使用範例::

        async with AsyncCANDevice(
            config=DeviceConfig(device_id="pcs_001"),
            client=client,
            tx_signals=[...],
            tx_buffer_configs=[FrameBufferConfig(can_id=0x200)],
            tx_periodic_configs=[PeriodicFrameConfig(can_id=0x200, interval=0.1)],
            rx_frame_definitions=[CANRxFrameDefinition(can_id=0x100, parser=bms_parser)],
        ) as device:
            await device.write("power_target", 5000)
            print(device.latest_values)
    """

    ACTIONS: dict[str, str] = {}

    def __init__(
        self,
        config: DeviceConfig,
        client: AsyncCANClientBase,
        # TX 配置
        tx_signals: Sequence[CANSignalDefinition] = (),
        tx_buffer_configs: Sequence[FrameBufferConfig] = (),
        tx_periodic_configs: Sequence[PeriodicFrameConfig] = (),
        # RX 配置
        rx_frame_definitions: Sequence[CANRxFrameDefinition] = (),
        # 通用
        alarm_evaluators: Sequence[AlarmEvaluator] = (),
        aggregator_pipeline: AggregatorPipeline | None = None,
        capability_bindings: Sequence[CapabilityBinding] = (),
        rx_timeout: float = 10.0,
    ) -> None:
        self._config = config
        self._client = client

        # TX: Frame Buffer
        self._frame_buffer: CANFrameBuffer | None = None
        self._periodic_scheduler: PeriodicSendScheduler | None = None
        self._tx_signal_names: set[str] = set()

        if tx_signals:
            self._frame_buffer = CANFrameBuffer(
                configs=list(tx_buffer_configs),
                signals=list(tx_signals),
            )
            self._tx_signal_names = {sig.field.name for sig in tx_signals}

            if tx_periodic_configs:
                self._periodic_scheduler = PeriodicSendScheduler(
                    frame_buffer=self._frame_buffer,
                    send_callback=client.send,
                    configs=list(tx_periodic_configs),
                )

        # RX: 訊框定義
        self._rx_definitions: dict[int, CANRxFrameDefinition] = {
            rx_def.can_id: rx_def for rx_def in rx_frame_definitions
        }
        self._rx_unsubscribes: list[Callable[[], None]] = []

        # 告警管理
        self._alarm_manager = AlarmStateManager()
        self._alarm_evaluators = list(alarm_evaluators)
        for evaluator in self._alarm_evaluators:
            self._alarm_manager.register_alarms(evaluator.get_alarms())

        # 聚合處理
        self._aggregator_pipeline = aggregator_pipeline

        # 能力綁定
        self._capability_bindings: dict[str, CapabilityBinding] = {b.capability.name: b for b in capability_bindings}

        # 事件
        self._emitter = DeviceEventEmitter()

        # 設備狀態
        self._latest_values: dict[str, Any] = {}
        self._client_connected = False
        self._device_responsive = False

        # Snapshot loop & RX timeout
        self._snapshot_task: asyncio.Task[None] | None = None
        self._rx_timeout = rx_timeout
        self._last_rx_time: float = 0.0

    # =============== Properties ===============

    @property
    def device_id(self) -> str:
        return self._config.device_id

    @property
    def is_connected(self) -> bool:
        return self._client_connected

    @property
    def is_responsive(self) -> bool:
        return self._device_responsive

    @property
    def latest_values(self) -> dict[str, Any]:
        return self._latest_values.copy()

    @property
    def is_running(self) -> bool:
        return self._client_connected

    # =============== Capabilities ===============

    @property
    def capabilities(self) -> dict[str, CapabilityBinding]:
        return dict(self._capability_bindings)

    def has_capability(self, capability: Capability | str) -> bool:
        name = capability.name if isinstance(capability, Capability) else capability
        return name in self._capability_bindings

    def get_binding(self, capability: Capability | str) -> CapabilityBinding | None:
        name = capability.name if isinstance(capability, Capability) else capability
        return self._capability_bindings.get(name)

    def resolve_point(self, capability: Capability | str, slot: str) -> str:
        from csp_lib.core.errors import ConfigurationError

        binding = self.get_binding(capability)
        if binding is None:
            name = capability.name if isinstance(capability, Capability) else capability
            raise ConfigurationError(f"Device '{self.device_id}' has no capability '{name}'")
        return binding.resolve(slot)

    def add_capability(self, binding: CapabilityBinding) -> None:
        self._capability_bindings[binding.capability.name] = binding
        self._emitter.emit(
            EVENT_CAPABILITY_ADDED,
            CapabilityChangedPayload(device_id=self._config.device_id, capability_name=binding.capability.name),
        )

    def remove_capability(self, capability: Capability | str) -> None:
        name = capability.name if isinstance(capability, Capability) else capability
        if name in self._capability_bindings:
            self._capability_bindings.pop(name, None)
            self._emitter.emit(
                EVENT_CAPABILITY_REMOVED,
                CapabilityChangedPayload(device_id=self._config.device_id, capability_name=name),
            )

    # =============== Health ===============

    def health(self) -> HealthReport:
        if self.is_connected and self.is_responsive and not self.is_protected:
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
                "protocol": "can",
            },
        )

    # =============== Lifecycle ===============

    async def connect(self) -> None:
        """連線 CAN Bus 並啟動接收"""
        await self._client.connect()
        await self._emitter.start()
        self._client_connected = True
        self._device_responsive = True
        self._last_rx_time = time.monotonic()

        # 訂閱 RX 訊框
        for can_id, rx_def in self._rx_definitions.items():
            if rx_def.is_periodic:
                cancel = self._client.subscribe(can_id, self._make_rx_handler(rx_def))
                self._rx_unsubscribes.append(cancel)

        # 啟動 listener
        await self._client.start_listener()

        await self._emitter.emit_await(EVENT_CONNECTED, ConnectedPayload(device_id=self._config.device_id))

    async def start(self) -> None:
        """啟動定期發送與 snapshot loop"""
        if self._periodic_scheduler:
            await self._periodic_scheduler.start()
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())

    async def stop(self) -> None:
        """停止定期發送與 snapshot loop"""
        if self._snapshot_task is not None:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass
            self._snapshot_task = None
        if self._periodic_scheduler:
            await self._periodic_scheduler.stop()

    async def disconnect(self) -> None:
        """停止並斷開連線"""
        await self.stop()

        # 取消 RX 訂閱
        for unsub in self._rx_unsubscribes:
            unsub()
        self._rx_unsubscribes.clear()

        if self._client_connected:
            await self._client.stop_listener()
            await self._client.disconnect()
            self._client_connected = False
            self._device_responsive = False
            await self._emitter.emit_await(
                EVENT_DISCONNECTED,
                DisconnectPayload(device_id=self._config.device_id, reason="normal", consecutive_failures=0),
            )
            await self._emitter.stop()

    async def __aenter__(self) -> AsyncCANDevice:
        try:
            await self.connect()
            await self.start()
            return self
        except Exception:
            await self.disconnect()
            raise

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            await self.stop()
        finally:
            await self.disconnect()

    # =============== Transport ===============

    async def write(self, name: str, value: Any, *, immediate: bool = False, **kwargs: Any) -> WriteResult:
        """
        寫入 CAN 信號

        更新 frame buffer 中的信號值。

        Args:
            name: 信號名稱
            value: 物理值
            immediate: 是否立即發送（不等待定期排程）

        Returns:
            WriteResult
        """
        if self._frame_buffer is None or name not in self._tx_signal_names:
            return WriteResult(
                status=WriteStatus.VALIDATION_FAILED,
                point_name=name,
                value=value,
                error_message=f"TX 信號 '{name}' 不存在",
            )

        try:
            self._frame_buffer.set_signal(name, value)

            if immediate:
                signal = self._frame_buffer.get_signal(name)
                data = self._frame_buffer.get_frame(signal.can_id)
                await self._client.send(signal.can_id, data)

            self._emitter.emit(
                EVENT_WRITE_COMPLETE,
                WriteCompletePayload(device_id=self._config.device_id, point_name=name, value=value),
            )
            return WriteResult(status=WriteStatus.SUCCESS, point_name=name, value=value)

        except Exception as e:
            self._emitter.emit(
                EVENT_WRITE_ERROR,
                WriteErrorPayload(device_id=self._config.device_id, point_name=name, value=value, error=str(e)),
            )
            return WriteResult(
                status=WriteStatus.WRITE_FAILED,
                point_name=name,
                value=value,
                error_message=str(e),
            )

    async def read_once(self) -> dict[str, Any]:
        """
        執行一次讀取

        - 被動監聽的訊框：直接返回 latest_values（背景已持續更新）
        - 請求-回應的訊框：發送請求，等回應後解碼合併
        - READ_COMPLETE 由 snapshot loop 統一發射
        """
        # 處理請求-回應類型的訊框
        for can_id, rx_def in self._rx_definitions.items():
            if not rx_def.is_periodic and rx_def.request_data:
                frame = await self._client.request(
                    can_id=can_id,
                    data=rx_def.request_data,
                    response_id=can_id,
                )
                self._process_rx_frame(rx_def, frame)

        return self._latest_values.copy()

    # =============== Events ===============

    def on(self, event: str, handler: AsyncHandler) -> Callable[[], None]:
        return self._emitter.on(event, handler)

    def emit(self, event: str, payload: Any) -> None:
        self._emitter.emit(event, payload)

    # =============== Private ===============

    def _make_rx_handler(self, rx_def: CANRxFrameDefinition) -> Callable[[CANFrame], None]:
        """為 RX 訊框建立回調 handler"""

        def handler(frame: CANFrame) -> None:
            self._process_rx_frame(rx_def, frame)

        return handler

    def _process_rx_frame(self, rx_def: CANRxFrameDefinition, frame: CANFrame) -> None:
        """處理接收到的 CAN 訊框"""
        self._last_rx_time = time.monotonic()

        # RX timeout 恢復：若先前判定為無回應，收到訊框後恢復
        if not self._device_responsive and self._client_connected:
            self._device_responsive = True
            self._emitter.emit(EVENT_CONNECTED, ConnectedPayload(device_id=self._config.device_id))

        # 將 8 bytes 轉為 UInt64（parser 期望的格式）
        raw_int = int.from_bytes(frame.data.ljust(8, b"\x00"), byteorder=rx_def.parser.byte_order)

        values = rx_def.parser.process({rx_def.parser.source_name: raw_int})

        # 聚合處理
        if self._aggregator_pipeline:
            values = self._aggregator_pipeline.process(values)

        # 發送值變更事件（僅 VALUE_CHANGE，READ_COMPLETE 由 snapshot loop 負責）
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

    # =============== Snapshot Loop ===============

    async def _snapshot_loop(self) -> None:
        """週期性發射 READ_COMPLETE + 告警評估 + RX timeout 檢查。

        採用絕對時間錨定（absolute time anchoring）避免時序漂移：
        以 ``next_tick_delay`` helper 統一計算 sleep delay；work-first 語義，
        sleep 自動補償 work 耗時，落後一個 interval 重設 anchor 避免 burst。
        """
        interval = self._config.read_interval
        anchor = time.monotonic()
        n = 0
        while True:
            values = self._latest_values.copy()

            self._emitter.emit(
                EVENT_READ_COMPLETE,
                ReadCompletePayload(
                    device_id=self._config.device_id,
                    values=values,
                    duration_ms=0.0,
                ),
            )

            await self._evaluate_alarm(values)
            self._check_rx_timeout()

            delay, anchor, n = next_tick_delay(anchor, n, interval)
            await asyncio.sleep(delay)

    def _check_rx_timeout(self) -> None:
        """檢查 RX 是否超時，若超時則標記為無回應"""
        if self._last_rx_time == 0.0:
            return
        elapsed = time.monotonic() - self._last_rx_time
        if elapsed > self._rx_timeout and self._device_responsive:
            self._device_responsive = False
            self._emitter.emit(
                EVENT_DISCONNECTED,
                DisconnectPayload(device_id=self._config.device_id, reason="rx_timeout", consecutive_failures=0),
            )

    # =============== Magic Methods =========

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} id={self.device_id} connected={self.is_connected} responsive={self.is_responsive}>"

    def __repr__(self) -> str:
        return self.__str__()


__all__ = [
    "CANRxFrameDefinition",
    "AsyncCANDevice",
]
