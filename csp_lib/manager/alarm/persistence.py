"""告警持久化管理器"""

from datetime import datetime
from typing import Callable

from csp_lib.core import get_logger
from csp_lib.equipment.alarm import AlarmLevel
from csp_lib.equipment.device import AsyncModbusDevice
from csp_lib.equipment.device.events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    ConnectedPayload,
    DeviceAlarmPayload,
    DisconnectPayload,
)

from .repository import AlarmRepository
from .schema import AlarmRecord, AlarmType

logger = get_logger(__name__)


class AlarmPersistenceManager:
    """
    告警持久化管理器
    職責：
    1. 訂閱多個 AsyncModbusDevice 事件
    2. 斷線/告警觸發 → 寫入 DB
    3. 恢復/告警解除 → 更新 resolved_at
    """

    DISCONNECT_CODE = "DISCONNECT"
    DISCONNECT_NAME = "設備斷線"

    def __init__(
        self,
        repository: AlarmRepository,
    ) -> None:
        self._repository = repository
        self._unsubscribes: dict[str, list[Callable[[], None]]] = {}

    def subscribe(self, device: AsyncModbusDevice) -> None:
        """訂閱設備事件"""
        device_id = device.device_id
        if device_id in self._unsubscribes:
            return
        self._unsubscribes[device_id] = [
            device.on(EVENT_DISCONNECTED, self._on_disconnected),
            device.on(EVENT_CONNECTED, self._on_connected),
            device.on(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered),
            device.on(EVENT_ALARM_CLEARED, self._on_alarm_cleared),
        ]
        logger.info(f"告警持久化管理器已訂閱設備: {device_id}")

    def unsubscribe(self, device: AsyncModbusDevice) -> None:
        """取消訂閱設備事件"""
        device_id = device.device_id
        if device_id not in self._unsubscribes:
            return
        for unsubscribe in self._unsubscribes.pop(device_id):
            unsubscribe()
        logger.info(f"告警持久化管理器已取消訂閱設備: {device_id}")

    # ================ Event Handler ================

    async def _on_disconnected(self, payload: DisconnectPayload) -> None:
        record = AlarmRecord(
            alarm_key=AlarmRecord.make_key(payload.device_id, AlarmType.DISCONNECT, self.DISCONNECT_CODE),
            device_id=payload.device_id,
            alarm_type=AlarmType.DISCONNECT,
            name=self.DISCONNECT_NAME,
            level=AlarmLevel.WARNING.value,
            description=payload.reason,
            occurred_at=payload.timestamp,
        )
        await self._create_alarm(record)

    async def _on_connected(self, payload: ConnectedPayload) -> None:
        key = AlarmRecord.make_key(payload.device_id, AlarmType.DISCONNECT, self.DISCONNECT_CODE)
        await self._resolve_alarm(key, payload.timestamp)

    async def _on_alarm_triggered(self, payload: DeviceAlarmPayload) -> None:
        alarm = payload.alarm_event.alarm
        record = AlarmRecord(
            alarm_key=AlarmRecord.make_key(payload.device_id, AlarmType.DEVICE_ALARM, alarm.code),
            device_id=payload.device_id,
            alarm_type=AlarmType.DEVICE_ALARM,
            name=alarm.name,
            level=alarm.level.value,
            description=alarm.description,
            occurred_at=payload.timestamp,
        )
        await self._create_alarm(record)

    async def _on_alarm_cleared(self, payload: DeviceAlarmPayload) -> None:
        alarm = payload.alarm_event.alarm
        key = AlarmRecord.make_key(payload.device_id, AlarmType.DEVICE_ALARM, alarm.code)
        await self._resolve_alarm(key, payload.timestamp)

    # =========== Private =============

    async def _create_alarm(self, record: AlarmRecord) -> None:
        _, is_new = await self._repository.upsert(record)
        if is_new:
            logger.info(f"告警持久化管理器已新增告警: {record.alarm_key}")
            # TODO: 發送告警通知

    async def _resolve_alarm(self, alarm_key: str, resolved_at: datetime) -> None:
        success = await self._repository.resolve(alarm_key, resolved_at)
        if success:
            logger.info(f"告警持久化管理器已解除告警: {alarm_key}")
        # TODO: 發送告警通知
