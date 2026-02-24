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
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Callable

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
from csp_lib.manager.base import DeviceEventSubscriber

from .config import AlarmPersistenceConfig
from .repository import AlarmRepository
from .schema import AlarmRecord, AlarmType

if TYPE_CHECKING:
    from csp_lib.notification import NotificationSender

logger = get_logger(__name__)


class _NotifyEvent(str, Enum):
    """內部通知事件類型（避免頂層 import 循環）"""

    TRIGGERED = "triggered"
    RESOLVED = "resolved"


class AlarmPersistenceManager(DeviceEventSubscriber):
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

    def __init__(
        self,
        repository: AlarmRepository,
        dispatcher: NotificationSender | None = None,
        config: AlarmPersistenceConfig | None = None,
    ) -> None:
        """
        初始化告警持久化管理器

        Args:
            repository: 告警資料存取層（遵循 AlarmRepository Protocol）
            dispatcher: 通知分發器（可選），用於告警觸發/解除時發送通知
            config: 告警持久化配置（可選，預設使用 AlarmPersistenceConfig()）
        """
        super().__init__()
        self._repository = repository
        self._dispatcher = dispatcher
        self._config = config or AlarmPersistenceConfig()

    # ================ 訂閱管理 ================

    def _register_events(self, device: AsyncModbusDevice) -> list[Callable[[], None]]:
        """註冊設備的連線/斷線與告警觸發/解除事件"""
        logger.info(f"告警持久化管理器已訂閱設備: {device.device_id}")
        return [
            device.on(EVENT_DISCONNECTED, self._on_disconnected),
            device.on(EVENT_CONNECTED, self._on_connected),
            device.on(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered),
            device.on(EVENT_ALARM_CLEARED, self._on_alarm_cleared),
        ]

    def _on_unsubscribe(self, device_id: str) -> None:
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
            alarm_key=AlarmRecord.make_key(payload.device_id, AlarmType.DISCONNECT, self._config.disconnect_code),
            device_id=payload.device_id,
            alarm_type=AlarmType.DISCONNECT,
            name=self._config.disconnect_name,
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
        key = AlarmRecord.make_key(payload.device_id, AlarmType.DISCONNECT, self._config.disconnect_code)
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

        透過 repository 寫入告警記錄。若為新告警則記錄 log 並發送通知。

        Args:
            record: 告警記錄
        """
        _, is_new = await self._repository.upsert(record)
        if is_new:
            logger.info(f"告警持久化管理器已新增告警: {record.alarm_key}")
            await self._notify(record, _NotifyEvent.TRIGGERED)

    async def _resolve_alarm(self, alarm_key: str, resolved_at: datetime) -> None:
        """
        解除告警記錄

        透過 repository 更新告警狀態為已解除。若成功則記錄 log 並發送通知。

        Args:
            alarm_key: 告警唯一鍵
            resolved_at: 解除時間
        """
        success = await self._repository.resolve(alarm_key, resolved_at)
        if success:
            logger.info(f"告警持久化管理器已解除告警: {alarm_key}")
            await self._notify_resolved(alarm_key, resolved_at)

    async def _notify(self, record: AlarmRecord, event: _NotifyEvent) -> None:
        """發送告警通知（非阻塞，失敗僅記 log）"""
        if self._dispatcher is None:
            return
        try:
            from csp_lib.notification import NotificationDispatcher, NotificationEvent

            notification = NotificationDispatcher.from_alarm_record(record, NotificationEvent(event.value))
            await self._dispatcher.dispatch(notification)
        except Exception:
            logger.warning(f"告警通知發送失敗: {record.alarm_key}", exc_info=True)

    async def _notify_resolved(self, alarm_key: str, resolved_at: datetime) -> None:
        """發送解除通知（從 alarm_key 拆解 device_id，不查 DB）"""
        if self._dispatcher is None:
            return
        try:
            from csp_lib.notification import Notification, NotificationEvent

            # alarm_key 格式: "<device_id>:<alarm_type>:<alarm_code>"
            parts = alarm_key.split(":")
            device_id = parts[0] if parts else alarm_key

            notification = Notification(
                title=f"[RESOLVED] {device_id} 告警解除",
                body=f"告警 {alarm_key} 已解除",
                level=AlarmLevel.INFO,
                device_id=device_id,
                alarm_key=alarm_key,
                event=NotificationEvent.RESOLVED,
                occurred_at=resolved_at,
            )
            await self._dispatcher.dispatch(notification)
        except Exception:
            logger.warning(f"告警解除通知發送失敗: {alarm_key}", exc_info=True)
