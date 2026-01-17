# =============== Manager - Device ===============
#
# 設備管理模組
#
# 提供設備讀取管理功能：
#   - DeviceGroup: 設備群組（共用 Client 順序讀取）
#   - DeviceManager: 設備管理器（統一管理獨立與群組設備）
#
# 使用方式：
#   1. 建立 DeviceManager 實例
#   2. 使用 register() 註冊獨立設備
#   3. 使用 register_group() 註冊共用 Client 的群組
#   4. 呼叫 start() 啟動所有設備，stop() 停止

from .group import DeviceGroup
from .manager import DeviceManager

__all__ = [
    "DeviceGroup",
    "DeviceManager",
]
