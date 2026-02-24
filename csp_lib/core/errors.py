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


__all__ = [
    "DeviceError",
    "DeviceConnectionError",
    "CommunicationError",
    "AlarmError",
    "ConfigurationError",
]
