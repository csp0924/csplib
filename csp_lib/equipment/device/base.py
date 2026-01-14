# =============== Equipment Device - Base ===============
#
# 非同步 Modbus 設備
#
# 整合讀寫、告警、事件的完整設備抽象

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable, Sequence

from csp_lib.equipment.alarm import AlarmEvaluator, AlarmEventType, AlarmState, AlarmStateManager
from csp_lib.equipment.transport import (
    GroupReader,
    PointGrouper,
    ReadScheduler,
    ValidatedWriter,
    WriteResult,
    WriteStatus,
)

from .config import DeviceConfig
from .events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    EVENT_READ_ERROR,
    EVENT_VALUE_CHANGE,
    EVENT_WRITE_COMPLETE,
    EVENT_WRITE_ERROR,
    AsyncHandler,
    ConnectedPayload,
    DeviceAlarmPayload,
    DeviceEventEmitter,
    DisconnectPayload,
    ReadCompletePayload,
    ReadErrorPayload,
    ValueChangePayload,
    WriteCompletePayload,
    WriteErrorPayload,
)

if TYPE_CHECKING:
    from csp_lib.equipment.core import ReadPoint, WritePoint
    from csp_lib.modbus.clients.base import AsyncModbusClientBase


class AsyncModbusDevice:
    """
    非同步 Modbus 設備

    整合讀寫、告警、事件的完整設備抽象。

    特點：
        - 定期讀取循環
        - 告警狀態管理（含遲滯）
        - 事件驅動通知
        - 動態點位排程
        - 設備寫入管理
    """

    def __init__(
        self,
        config: DeviceConfig,
        client: AsyncModbusClientBase,
        always_points: Sequence[ReadPoint] = (),
        rotating_points: Sequence[Sequence[ReadPoint]] = (),
        write_points: Sequence[WritePoint] = (),
        alarm_evaluators: Sequence[AlarmEvaluator] = (),
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
            address_offset=config.address_offset,
        )
        self._writer = ValidatedWriter(client=client, address_offset=config.address_offset)

        # 寫入點位查詢表
        self._write_points = {write_point.name: write_point for write_point in write_points}

        # 告警管理
        self._alarm_manager = AlarmStateManager()
        self._alarm_evaluators = list(alarm_evaluators)
        for evaluator in self._alarm_evaluators:
            self._alarm_manager.register_alarms(evaluator.get_alarms())

        # 事件
        self._emitter = DeviceEventEmitter()

        # 設備狀態
        self._latest_values: dict[str, Any] = {}
        self._client_connected = False  # Socket 層級：client.connect() 是否成功
        self._device_responsive = False  # 通訊層級：設備是否有回應
        self._consecutive_failures = 0  # 連續讀取失敗次數
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
    def is_protected(self) -> bool:
        """設備是否已保護"""
        return self._alarm_manager.has_protection_alarm()

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
    def active_alarms(self) -> list[AlarmState]:
        """啟用中的告警"""
        return self._alarm_manager.get_active_alarms()

    @property
    def is_running(self) -> bool:
        """讀取循環是否運行中"""
        return self._read_task is not None and not self._read_task.done()

    # =============== Lifecycle ===============

    async def connect(self) -> None:
        """
        連線設備

        Raises:
            ConnectionError: 連線失敗
        """
        await self._client.connect()
        await self._emitter.start()  # 啟動事件處理 worker
        self._client_connected = True
        self._device_responsive = True  # 假設連線成功即可回應，讀取失敗會更新
        self._consecutive_failures = 0
        await self._emitter.emit_await(EVENT_CONNECTED, ConnectedPayload(device_id=self._config.device_id))

    async def disconnect(self) -> None:
        """
        斷線設備

        Raises:
            ConnectionError: 斷線失敗
        """
        await self.stop()
        if self._client_connected:
            await self._client.disconnect()
            self._client_connected = False
            self._device_responsive = False
            self._consecutive_failures = 0
            await self._emitter.emit_await(
                EVENT_DISCONNECTED,
                DisconnectPayload(device_id=self._config.device_id, reason="normal", consecutive_failures=0),
            )
            await self._emitter.stop()  # 停止事件處理 worker

    async def start(self) -> None:
        """
        啟動定期讀取循環

        Raises:
            ConnectionError: 設備未連線
        """
        if not self._client_connected:
            raise ConnectionError("設備未連線（Client 尚未連線）")

        if self._read_task is not None and not self._read_task.done():
            return

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

        包含：讀取點位、更新狀態、處理值變更事件、評估告警。
        適合不需要定期讀取的場景（如：手動觸發讀取）。

        Returns:
            讀取到的點位值字典

        Raises:
            Exception: 讀取失敗時拋出例外（會發送 EVENT_READ_ERROR）
        """
        start_time = time.monotonic()

        try:
            values = await self._read_all()
            self._consecutive_failures = 0

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

        except Exception as e:
            self._consecutive_failures += 1
            self._emitter.emit(
                EVENT_READ_ERROR,
                ReadErrorPayload(
                    device_id=self._config.device_id,
                    error=str(e),
                    consecutive_failures=self._consecutive_failures,
                ),
            )

            # 達到斷線閾值，標記設備無回應
            if self._consecutive_failures >= self._config.disconnect_threshold and self._device_responsive:
                self._device_responsive = False
                await self._emitter.emit_await(
                    EVENT_DISCONNECTED,
                    DisconnectPayload(
                        device_id=self._config.device_id,
                        reason=str(e),
                        consecutive_failures=self._consecutive_failures,
                    ),
                )

            raise

    async def write(self, name: str, value: Any, verify: bool = False) -> WriteResult:
        """寫入點位值"""
        point = self._write_points.get(name)
        if point is None:
            return WriteResult(
                status=WriteStatus.VALIDATION_FAILED,
                point_name=name,
                value=value,
                error_message=f"寫入點位 {name} 失敗，點位不存在",
            )

        result = await self._writer.write(point=point, value=value, verify=verify)

        if result.status == WriteStatus.SUCCESS:
            self._emitter.emit(
                EVENT_WRITE_COMPLETE,
                WriteCompletePayload(device_id=self._config.device_id, point_name=name, value=value),
            )
        else:
            self._emitter.emit(
                EVENT_WRITE_ERROR,
                WriteErrorPayload(
                    device_id=self._config.device_id, point_name=name, value=value, error=result.error_message
                ),
            )

        return result

    # =============== Events ================

    def on(self, event: str, handler: AsyncHandler) -> Callable[[], None]:
        """註冊事件處理器"""
        return self._emitter.on(event, handler)

    def emit(self, event: str, payload: Any) -> None:
        """發送事件（非阻塞）"""
        self._emitter.emit(event, payload)

    # =============== Alarm =================

    async def clear_alarm(self, code: str) -> None:
        """手動清除告警"""
        event = self._alarm_manager.clear_alarm(code)
        if event:
            payload = DeviceAlarmPayload(device_id=self._config.device_id, alarm_event=event)
            await self._emitter.emit_await(EVENT_ALARM_CLEARED, payload)  # 告警事件需同步處理

    # =============== Private ===============

    async def _read_all(self) -> dict[str, Any]:
        """讀取所有點位（使用排程器預計算分組）"""
        groups = self._scheduler.get_next_groups()
        if not groups:
            return {}
        return await self._reader.read_many(groups)

    async def _read_loop(self) -> None:
        """讀取循環"""
        interval = self._config.read_interval

        while not self._stop_event.is_set():
            start_time = time.monotonic()

            try:
                await self.read_once()
            except Exception:
                pass  # read_once 已處理錯誤事件

            elapsed = time.monotonic() - start_time
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

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

    async def _evaluate_alarm(self, values: dict[str, Any]) -> None:
        """評估告警"""
        for evaluator in self._alarm_evaluators:
            point_value = values.get(evaluator.point_name)
            if point_value is None:
                continue

            evaluations = evaluator.evaluate(point_value)
            events = self._alarm_manager.update(evaluations)

            for event in events:
                payload = DeviceAlarmPayload(device_id=self._config.device_id, alarm_event=event)
                if event.event_type == AlarmEventType.TRIGGERED:
                    await self._emitter.emit_await(EVENT_ALARM_TRIGGERED, payload)
                else:
                    await self._emitter.emit_await(EVENT_ALARM_CLEARED, payload)

    # =============== Magic Methods =========

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} id={self.device_id} connected={self.is_connected} responsive={self.is_responsive}>"

    def __repr__(self) -> str:
        return self.__str__()
