# =============== Core - Errors ===============
#
# 統一錯誤層次結構
#
# 提供可程式化的例外類別：
#   - DeviceError: 設備層基礎例外
#   - DeviceConnectionError: 連線/斷線失敗
#   - CommunicationError: 讀寫逾時/解碼錯誤
#   - AlarmError: 告警觸發
#   - ConfigurationError: 配置無效（非設備層級）
#   - StrategyExecutionError: 策略執行失敗（非設備層級）
#   - ProtectionError: 保護鏈失敗（非設備層級）
#   - DeviceRegistryError: 設備註冊/查詢失敗

from __future__ import annotations


class DeviceError(Exception):
    """設備層基礎例外"""

    def __init__(self, device_id: str, message: str):
        self.device_id = device_id
        super().__init__(f"[{device_id}] {message}")


class DeviceConnectionError(DeviceError):
    """連線/斷線失敗"""


class CommunicationError(DeviceError):
    """讀寫逾時/解碼錯誤"""


class AlarmError(DeviceError):
    """告警觸發"""

    def __init__(self, device_id: str, alarm_code: str, message: str):
        self.alarm_code = alarm_code
        super().__init__(device_id, message)


class ConfigurationError(Exception):
    """配置無效（非設備層級）"""


class StrategyExecutionError(Exception):
    """Strategy execution failure (not device-scoped)."""

    def __init__(self, strategy_name: str, message: str) -> None:
        self.strategy_name = strategy_name
        super().__init__(f"Strategy '{strategy_name}': {message}")


class ProtectionError(Exception):
    """Protection chain failure (not device-scoped)."""

    def __init__(self, rule_name: str, message: str) -> None:
        self.rule_name = rule_name
        super().__init__(f"Protection rule '{rule_name}': {message}")


class DeviceRegistryError(DeviceError):
    """Device registry lookup/registration failure."""


class NotLeaderError(Exception):
    """操作需 leader 身份但目前節點非 leader。

    用於 WriteCommandManager / 其他受 LeaderGate 守門的寫入端，
    在非 leader 時 raise，讓呼叫者可重試或改路由到 leader 節點。

    刻意繼承 ``Exception``（而非 ``DeviceError``），因為 leader 身份問題
    屬於集群/節點層次，並非特定設備的錯誤，不應被 device-scoped
    例外處理邏輯誤當成設備故障處理。
    """

    def __init__(self, operation: str, message: str = "not leader") -> None:
        self.operation = operation
        super().__init__(f"[{operation}] {message}")


__all__ = [
    "DeviceError",
    "DeviceConnectionError",
    "CommunicationError",
    "AlarmError",
    "ConfigurationError",
    "StrategyExecutionError",
    "ProtectionError",
    "DeviceRegistryError",
    "NotLeaderError",
]
