# =============== Manager Alarm - Persistence ===============
#
# 告警持久化管理器
#
# 提供告警事件的自動持久化功能：
#   - AlarmPersistenceManager: 訂閱設備事件並自動寫入/更新告警記錄
#
# 設計模式：
#   - 觀察者模式：訂閱 AsyncModbusDevice 的連線/告警事件
#   - 事件驅動：斷線/告警觸發 → 寫入 DB，恢復/解除 → 更新 resolved_at
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

    自動將設備事件持久化至資料庫。採用觀察者模式訂閱 AsyncModbusDevice
    的連線與告警事件，實現事件驅動的告警管理。

    職責：
        1. 訂閱多個 AsyncModbusDevice 的事件
        2. 斷線/告警觸發 → 寫入 DB（新增告警記錄）
        3. 恢復/告警解除 → 更新 resolved_at（解除告警）

    Attributes:
        DISCONNECT_CODE: 斷線告警的固定代碼
        DISCONNECT_NAME: 斷線告警的顯示名稱
    """

    DISCONNECT_CODE = "DISCONNECT"
    DISCONNECT_NAME = "設備斷線"

    def __init__(self, repository: AlarmRepository) -> None:
        """
        初始化告警持久化管理器

        Args:
            repository: 告警資料存取層（遵循 AlarmRepository Protocol）
        """
        self._repository = repository
        self._unsubscribes: dict[str, list[Callable[[], None]]] = {}

    # ================ 訂閱管理 ================

    def subscribe(self, device: AsyncModbusDevice) -> None:
        """
        訂閱設備事件

        訂閱設備的連線/斷線與告警觸發/解除事件。
        若已訂閱則不重複訂閱。

        Args:
            device: 要訂閱的 Modbus 設備
        """
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
        """
        取消訂閱設備事件

        移除對指定設備的事件訂閱。若尚未訂閱則不做任何操作。

        Args:
            device: 要取消訂閱的 Modbus 設備
        """
        device_id = device.device_id
        if device_id not in self._unsubscribes:
            return
        for unsubscribe in self._unsubscribes.pop(device_id):
            unsubscribe()
        logger.info(f"告警持久化管理器已取消訂閱設備: {device_id}")

    # ================ 事件處理器 ================

    async def _on_disconnected(self, payload: DisconnectPayload) -> None:
        """
        處理設備斷線事件

        建立斷線類型的告警記錄並寫入資料庫。

        Args:
            payload: 斷線事件資料（包含 device_id、reason、timestamp）
        """
        record = AlarmRecord(
            alarm_key=AlarmRecord.make_key(payload.device_id, AlarmType.DISCONNECT, self.DISCONNECT_CODE),
            device_id=payload.device_id,
            alarm_type=AlarmType.DISCONNECT,
            name=self.DISCONNECT_NAME,
            level=AlarmLevel.WARNING,
            description=payload.reason,
            occurred_at=payload.timestamp,
        )
        await self._create_alarm(record)

    async def _on_connected(self, payload: ConnectedPayload) -> None:
        """
        處理設備連線事件

        解除對應的斷線告警。

        Args:
            payload: 連線事件資料（包含 device_id、timestamp）
        """
        key = AlarmRecord.make_key(payload.device_id, AlarmType.DISCONNECT, self.DISCONNECT_CODE)
        await self._resolve_alarm(key, payload.timestamp)

    async def _on_alarm_triggered(self, payload: DeviceAlarmPayload) -> None:
        """
        處理設備告警觸發事件

        建立設備內部告警記錄並寫入資料庫。

        Args:
            payload: 告警事件資料（包含 device_id、alarm_event、timestamp）
        """
        alarm = payload.alarm_event.alarm
        record = AlarmRecord(
            alarm_key=AlarmRecord.make_key(payload.device_id, AlarmType.DEVICE_ALARM, alarm.code),
            device_id=payload.device_id,
            alarm_type=AlarmType.DEVICE_ALARM,
            name=alarm.name,
            level=alarm.level,
            description=alarm.description,
            occurred_at=payload.timestamp,
        )
        await self._create_alarm(record)

    async def _on_alarm_cleared(self, payload: DeviceAlarmPayload) -> None:
        """
        處理設備告警解除事件

        解除對應的設備內部告警。

        Args:
            payload: 告警事件資料（包含 device_id、alarm_event、timestamp）
        """
        alarm = payload.alarm_event.alarm
        key = AlarmRecord.make_key(payload.device_id, AlarmType.DEVICE_ALARM, alarm.code)
        await self._resolve_alarm(key, payload.timestamp)

    # ================ 私有方法 ================

    async def _create_alarm(self, record: AlarmRecord) -> None:
        """
        建立告警記錄

        透過 repository 寫入告警記錄。若為新告警則記錄 log。

        Args:
            record: 告警記錄
        """
        _, is_new = await self._repository.upsert(record)
        if is_new:
            logger.info(f"告警持久化管理器已新增告警: {record.alarm_key}")
            # TODO: 發送告警通知

    async def _resolve_alarm(self, alarm_key: str, resolved_at: datetime) -> None:
        """
        解除告警記錄

        透過 repository 更新告警狀態為已解除。若成功則記錄 log。

        Args:
            alarm_key: 告警唯一鍵
            resolved_at: 解除時間
        """
        success = await self._repository.resolve(alarm_key, resolved_at)
        if success:
            logger.info(f"告警持久化管理器已解除告警: {alarm_key}")
        # TODO: 發送告警通知
