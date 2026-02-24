# =============== Notification - Config ===============
#
# 通知配置
#
# 定義通知分發相關參數：
#   - NotificationConfig: 事件標籤與標題模板

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationConfig:
    """
    通知配置

    Attributes:
        triggered_label: 告警觸發時的事件標籤
        resolved_label: 告警解除時的事件標籤
        title_template: 通知標題模板，支援 {level}, {device_id}, {name}, {event_label} 佔位符
    """

    triggered_label: str = "觸發"
    resolved_label: str = "解除"
    title_template: str = "[{level}] {device_id} {name} - {event_label}"

    def __post_init__(self) -> None:
        if not self.triggered_label:
            raise ValueError("triggered_label 不可為空")
        if not self.resolved_label:
            raise ValueError("resolved_label 不可為空")
        if not self.title_template:
            raise ValueError("title_template 不可為空")


__all__ = [
    "NotificationConfig",
]
