# =============== Manager - Data ===============
#
# 資料上傳管理模組
#
# 提供設備資料自動上傳功能：
#   - DataUploadManager: 訂閱設備事件並自動上傳資料至 MongoDB
#   - UploadTarget / WritePolicy: fan-out 多 collection 與寫入策略
#
# 使用方式：
#   1. 建立 MongoBatchUploader 實例
#   2. 建立 DataUploadManager 並注入 Uploader
#   3. 呼叫 subscribe() 訂閱 AsyncModbusDevice
#   4. 讀取資料自動上傳至指定 collection（可 fan-out 到多個 target）

from .targets import TransformFn, TransformResult, UploadTarget, WritePolicy
from .upload import DataUploadManager

__all__ = [
    "DataUploadManager",
    "TransformFn",
    "TransformResult",
    "UploadTarget",
    "WritePolicy",
]
