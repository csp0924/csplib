# =============== Notification Module ===============
#
# 推播通知模組
#
# 提供可擴充的告警通知框架：
#   - Notification: 通知資料類別
#   - NotificationEvent: 通知事件類型（觸發/解除）
#   - NotificationChannel: 通知通道抽象（ABC）
#   - NotificationSender: 通知發送者協議
#   - NotificationDispatcher: 多通道通知分發器（即時發送）
#   - NotificationBatcher: 批次通知管理器（防抖 + 去重 + 分組）
#   - EventCategory / EventNotification: 非告警事件通知
#
# 使用方式：
#   1. 實作 NotificationChannel（如 LineChannel / TelegramChannel）
#   2. 建立 NotificationDispatcher（即時）或 NotificationBatcher（批次）
#   3. 將 dispatcher/batcher 傳入 AlarmPersistenceManager（均滿足 NotificationSender）
#   4. 告警觸發/解除時自動發送通知

from .base import Notification, NotificationChannel, NotificationEvent, NotificationSender
from .batch_config import BatchNotificationConfig
from .batcher import NotificationBatcher
from .config import NotificationConfig
from .dispatcher import NotificationDispatcher
from .event import EventCategory, EventNotification, NotificationItem

__all__ = [
    "BatchNotificationConfig",
    "EventCategory",
    "EventNotification",
    "Notification",
    "NotificationBatcher",
    "NotificationChannel",
    "NotificationConfig",
    "NotificationDispatcher",
    "NotificationEvent",
    "NotificationItem",
    "NotificationSender",
]
