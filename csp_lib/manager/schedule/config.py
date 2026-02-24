# =============== Manager Schedule - Config ===============
#
# 排程服務配置
#
# 定義排程服務相關參數：
#   - ScheduleServiceConfig: 輪詢間隔、時區、站點 ID

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduleServiceConfig:
    """
    排程服務配置

    Attributes:
        site_id: 站點識別碼
        poll_interval: 輪詢間隔（秒）
        timezone_name: 時區名稱
    """

    site_id: str = ""
    poll_interval: float = 30.0
    timezone_name: str = "Asia/Taipei"

    def __post_init__(self) -> None:
        if not self.site_id:
            raise ValueError("site_id 不可為空")
        if self.poll_interval <= 0:
            raise ValueError(f"poll_interval 必須大於 0，收到: {self.poll_interval}")


__all__ = [
    "ScheduleServiceConfig",
]
