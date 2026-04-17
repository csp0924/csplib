# =============== Manager Alarm - Config ===============
#
# 告警持久化配置
#
# 定義告警持久化相關參數：
#   - AlarmPersistenceConfig: 斷線告警代碼與名稱、history collection

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlarmPersistenceConfig:
    """
    告警持久化配置

    Attributes:
        disconnect_code: 斷線告警的固定代碼
        disconnect_name: 斷線告警的顯示名稱
        history_collection: 告警歷史記錄 collection 名稱。供
            ``LocalBufferedUploader`` 在告警建立/解除時額外寫入一份
            不可變的歷史記錄，確保 MongoDB 短暫斷線也不遺失。
    """

    disconnect_code: str = "DISCONNECT"
    disconnect_name: str = "設備斷線"
    history_collection: str = "alarm_history"

    def __post_init__(self) -> None:
        if not self.disconnect_code:
            raise ValueError("disconnect_code 不可為空")
        if not self.disconnect_name:
            raise ValueError("disconnect_name 不可為空")
        if not self.history_collection:
            raise ValueError("history_collection 不可為空")


__all__ = [
    "AlarmPersistenceConfig",
]
