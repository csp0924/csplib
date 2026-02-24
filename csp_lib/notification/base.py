# =============== Notification - Base ===============
#
# 通知系統基礎定義
#
# 提供通知框架的核心抽象：
#   - NotificationEvent: 通知事件類型（觸發/解除）
#   - Notification: 通知資料類別
#   - NotificationChannel: 通知通道抽象（ABC）
#   - NotificationSender: 通知發送者協議

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Protocol, Sequence, runtime_checkable

from csp_lib.equipment.alarm import AlarmLevel

if TYPE_CHECKING:
    from .event import EventNotification, NotificationItem


class NotificationEvent(str, Enum):
    """
    通知事件類型

    Values:
        TRIGGERED: 告警觸發
        RESOLVED: 告警解除
    """

    TRIGGERED = "triggered"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class Notification:
    """
    通知資料類別

    封裝一則告警通知的完整資訊，用於傳遞給各通知通道。

    Attributes:
        title: 通知標題（如 "[ALARM] inverter_001 溫度過高"）
        body: 詳細描述
        level: 告警等級
        device_id: 設備識別碼
        alarm_key: 告警唯一鍵
        event: 通知事件類型（TRIGGERED / RESOLVED）
        occurred_at: 發生時間
    """

    title: str
    body: str
    level: AlarmLevel
    device_id: str
    alarm_key: str
    event: NotificationEvent
    occurred_at: datetime


class NotificationChannel(ABC):
    """
    通知通道抽象

    定義通知通道的介面，未來可實作 Line / Telegram / Email / Webhook 等。
    子類別可覆寫 send_batch() 與 send_event() 以支援批次與事件通知。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """通道名稱"""
        ...

    @abstractmethod
    async def send(self, notification: Notification) -> None:
        """
        發送通知

        Args:
            notification: 通知資料
        """
        ...

    async def send_batch(self, items: Sequence[NotificationItem]) -> None:
        """
        批次發送通知

        預設實作：逐一發送 Notification 類型的項目。
        子類別可覆寫以實現自訂的批次格式（如摘要訊息）。

        Args:
            items: 通知項目列表（Notification 或 EventNotification）
        """
        for item in items:
            if isinstance(item, Notification):
                await self.send(item)
            else:
                await self.send_event(item)

    async def send_event(self, event: EventNotification) -> None:
        """
        發送事件通知

        預設為 no-op。子類別可覆寫以支援事件通知。

        Args:
            event: 事件通知資料
        """


@runtime_checkable
class NotificationSender(Protocol):
    """
    通知發送者協議

    定義最小的通知發送介面，讓 NotificationDispatcher
    與 NotificationBatcher 都能作為通知來源使用。
    """

    async def dispatch(self, notification: Notification) -> None:
        """
        分發通知

        Args:
            notification: 通知資料
        """
        ...


__all__ = [
    "Notification",
    "NotificationChannel",
    "NotificationEvent",
    "NotificationSender",
]
