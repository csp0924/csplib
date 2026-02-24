# =============== Notification - Event ===============
#
# 事件通知定義
#
# 提供非告警類型的通知支援：
#   - EventCategory: 事件分類（系統/報告/維護/自訂）
#   - EventNotification: 事件通知資料類別
#   - NotificationItem: 通知聯合型別

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Union

from .base import Notification


class EventCategory(str, Enum):
    """
    事件分類

    Values:
        SYSTEM: 系統事件（啟動/停止/重啟）
        REPORT: 報告事件（日報/週報產出）
        MAINTENANCE: 維護事件（排程維護/韌體更新）
        CUSTOM: 自訂事件
    """

    SYSTEM = "system"
    REPORT = "report"
    MAINTENANCE = "maintenance"
    CUSTOM = "custom"


@dataclass(frozen=True)
class EventNotification:
    """
    事件通知資料類別

    封裝一則非告警事件通知的完整資訊。

    Attributes:
        title: 通知標題
        body: 詳細描述
        category: 事件分類
        source: 事件來源（如模組名稱）
        immediate: 是否立即發送（繞過批次佇列）
        metadata: 額外資訊
        occurred_at: 發生時間
    """

    title: str
    body: str
    category: EventCategory
    source: str = ""
    immediate: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=datetime.now)


NotificationItem = Union[Notification, EventNotification]
"""通知聯合型別：告警通知或事件通知"""


__all__ = [
    "EventCategory",
    "EventNotification",
    "NotificationItem",
]
