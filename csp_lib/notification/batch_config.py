# =============== Notification - Batch Config ===============
#
# 批次通知配置
#
# 定義批次通知的相關參數：
#   - BatchNotificationConfig: 防抖時間窗、批次大小、佇列上限、去重

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatchNotificationConfig:
    """
    批次通知配置

    Attributes:
        flush_interval: 防抖時間窗（秒），預設 5 秒
        batch_size_threshold: 累積達此數量時立即 flush
        max_queue_size: 佇列最大容量
        deduplicate_by_key: 同一時間窗內，相同 alarm_key 僅保留最新一則
    """

    flush_interval: float = 5.0
    batch_size_threshold: int = 50
    max_queue_size: int = 5000
    deduplicate_by_key: bool = True

    def __post_init__(self) -> None:
        if self.flush_interval <= 0:
            raise ValueError("flush_interval 必須為正數")
        if self.batch_size_threshold <= 0:
            raise ValueError("batch_size_threshold 必須為正整數")
        if self.max_queue_size <= 0:
            raise ValueError("max_queue_size 必須為正整數")


__all__ = [
    "BatchNotificationConfig",
]
