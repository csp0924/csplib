# =============== Manager Alarm - Config ===============
#
# 告警持久化配置
#
# 定義告警持久化相關參數：
#   - AlarmPersistenceConfig: 斷線告警代碼與名稱

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlarmPersistenceConfig:
    """
    告警持久化配置

    Attributes:
        disconnect_code: 斷線告警的固定代碼
        disconnect_name: 斷線告警的顯示名稱
    """

    disconnect_code: str = "DISCONNECT"
    disconnect_name: str = "設備斷線"

    def __post_init__(self) -> None:
        if not self.disconnect_code:
            raise ValueError("disconnect_code 不可為空")
        if not self.disconnect_name:
            raise ValueError("disconnect_name 不可為空")


__all__ = [
    "AlarmPersistenceConfig",
]
