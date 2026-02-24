# =============== Notification - Dispatcher ===============
#
# 通知分發器
#
# 將通知扇出到多個通道，個別失敗不影響其他通道：
#   - NotificationDispatcher: 多通道通知分發器

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Sequence

from csp_lib.core import get_logger

from .base import Notification, NotificationChannel, NotificationEvent
from .config import NotificationConfig
from .event import NotificationItem

if TYPE_CHECKING:
    from csp_lib.manager.alarm.schema import AlarmRecord

logger = get_logger(__name__)


class NotificationDispatcher:
    """
    通知分發器

    將通知扇出到多個通道，個別通道發送失敗不影響其他通道，
    僅記錄警告日誌。

    Attributes:
        channels: 已註冊的通知通道列表

    Example:
        ```python
        dispatcher = NotificationDispatcher([line_channel, email_channel])
        await dispatcher.dispatch(notification)
        ```
    """

    def __init__(self, channels: Sequence[NotificationChannel]) -> None:
        """
        初始化通知分發器

        Args:
            channels: 通知通道列表
        """
        self._channels = list(channels)

    async def dispatch(self, notification: Notification) -> None:
        """
        將通知分發到所有通道

        個別通道失敗不影響其他通道，僅記錄警告日誌。

        Args:
            notification: 通知資料
        """
        for channel in self._channels:
            try:
                await channel.send(notification)
            except Exception:
                logger.warning(f"通知通道 '{channel.name}' 發送失敗", exc_info=True)

    @staticmethod
    def from_alarm_record(
        record: AlarmRecord,
        event: NotificationEvent,
        config: NotificationConfig | None = None,
    ) -> Notification:
        """
        從 AlarmRecord 建構 Notification

        工廠方法，根據告警記錄和事件類型建立通知物件。

        Args:
            record: 告警記錄
            event: 通知事件類型（TRIGGERED / RESOLVED）
            config: 通知配置（可選，預設使用 NotificationConfig()）

        Returns:
            Notification: 通知物件
        """
        if config is None:
            config = NotificationConfig()
        event_label = config.triggered_label if event == NotificationEvent.TRIGGERED else config.resolved_label
        title = config.title_template.format(
            level=record.level.name,
            device_id=record.device_id,
            name=record.name,
            event_label=event_label,
        )
        body = record.description or record.name
        occurred_at = record.occurred_at or datetime.now()

        return Notification(
            title=title,
            body=body,
            level=record.level,
            device_id=record.device_id,
            alarm_key=record.alarm_key,
            event=event,
            occurred_at=occurred_at,
        )

    async def dispatch_batch(self, notifications: Sequence[NotificationItem]) -> None:
        """
        批次分發通知到所有通道

        將通知列表透過 send_batch() 發送到所有通道。
        個別通道失敗不影響其他通道，僅記錄警告日誌。

        Args:
            notifications: 通知項目列表
        """
        for channel in self._channels:
            try:
                await channel.send_batch(list(notifications))
            except Exception:
                logger.warning(f"通知通道 '{channel.name}' 批次發送失敗", exc_info=True)

    @property
    def channels(self) -> list[NotificationChannel]:
        """已註冊的通知通道列表"""
        return list(self._channels)


__all__ = [
    "NotificationDispatcher",
]
