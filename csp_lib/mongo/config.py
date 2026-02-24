"""
MongoBatchUploader 設定模組

定義上傳器的配置參數，使用 frozen dataclass 確保不可變性。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UploaderConfig:
    """
    批次上傳器設定

    Attributes:
        flush_interval: 定期 flush 間隔（秒），預設 5 秒
        batch_size_threshold: 單一 collection 累積幾筆後觸發上傳，預設 100 筆
        max_queue_size: Queue 上限，超過後丟棄最舊資料，預設 10000 筆
        max_retry_count: 單批資料最大重試次數，超過後丟棄，預設 3 次
    """

    flush_interval: int = 5
    batch_size_threshold: int = 100
    max_queue_size: int = 10000
    max_retry_count: int = 3

    def __post_init__(self) -> None:
        """驗證設定值的合理性"""
        if self.flush_interval <= 0:
            raise ValueError(f"flush_interval 必須為正整數，收到: {self.flush_interval}")
        if self.batch_size_threshold <= 0:
            raise ValueError(f"batch_size_threshold 必須為正整數，收到: {self.batch_size_threshold}")
        if self.max_queue_size <= 0:
            raise ValueError(f"max_queue_size 必須為正整數，收到: {self.max_queue_size}")
        if self.max_retry_count < 0:
            raise ValueError(f"max_retry_count 不可為負數，收到: {self.max_retry_count}")
