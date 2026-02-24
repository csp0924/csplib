---
tags:
  - type/class
  - layer/storage
  - status/complete
source: csp_lib/mongo/uploader.py
---

# MongoBatchUploader

MongoDB 批次上傳器，隸屬於 [[_MOC Storage|Storage 模組]]。

## 概述

`MongoBatchUploader` 組合 `BatchQueue` + `MongoWriter`，提供集合式批次上傳功能：

- 所有資料按 collection 進入對應的 queue
- 定期或資料量達閾值時批次上傳（`insert_many`）
- 支援重試機制與容量上限保護

## UploaderConfig

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `flush_interval` | `int` | `5` | 定期 flush 間隔（秒） |
| `batch_size_threshold` | `int` | `100` | 單一 collection 累積幾筆後觸發上傳 |
| `max_queue_size` | `int` | `10000` | Queue 上限，超過後丟棄最舊資料 |
| `max_retry_count` | `int` | `3` | 單批資料最大重試次數，超過後丟棄 |

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `mongo_db` | `AsyncIOMotorDatabase` | Motor async MongoDB 資料庫實例 |
| `config` | `UploaderConfig \| None` | 上傳器設定（未提供則使用預設值） |

## API

| 方法 | 說明 |
|------|------|
| `register_collection(name)` | 預先註冊 collection 的 queue |
| `enqueue(collection_name, document)` | 將資料加入對應 collection 的 queue |
| `start() -> self` | 啟動定期 flush 任務（支援 fluent interface） |
| `stop()` | 停止 flush 任務，確保所有資料都已上傳 |
| `flush_all()` | 強制將所有 queue 中的資料上傳 |

## 上傳觸發時機

1. **閾值觸發**：單一 collection 累積文件數達到 `batch_size_threshold`
2. **定期觸發**：每隔 `flush_interval` 秒自動 flush 所有 queue
3. **停止前**：收到停止信號時，先 flush 所有殘留資料

## 重試機制

- 寫入失敗時，將文件回放至 queue 等待重試
- 超過 `max_retry_count` 次後丟棄該批資料並 log error
- 重試計數以 collection 為單位

## 使用範例

```python
from csp_lib.mongo import MongoBatchUploader, UploaderConfig

config = UploaderConfig(
    flush_interval=5,           # Flush every 5 seconds
    batch_size_threshold=100,   # Or when 100 docs accumulated
    max_queue_size=10000,       # Queue limit
    max_retry_count=3,          # Max retries per batch
)

uploader = MongoBatchUploader(db=db, config=config)
async with uploader:
    await uploader.enqueue("collection_name", {"key": "value"})
```

## 相關頁面

- [[MongoConfig]] — MongoDB 連線配置
- [[DataUploadManager]] — 使用 MongoBatchUploader 進行設備資料上傳
- [[_MOC Storage]] — Storage 模組總覽
