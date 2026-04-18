---
tags:
  - type/class
  - layer/storage
  - status/complete
source: csp_lib/mongo/uploader.py
created: 2026-02-17
updated: 2026-04-18
version: ">=0.8.2"
---

# MongoBatchUploader

MongoDB 批次上傳器，隸屬於 [[_MOC Storage|Storage 模組]]。

## 概述

`MongoBatchUploader` 實作 [[BatchUploader]] Protocol（v0.6.0），組合 `BatchQueue` + `MongoWriter`，提供集合式批次上傳功能：

### Protocol 關係

```
BatchUploader (Protocol)        ← csp_lib/manager/base.py
    ├── register_collection()
    └── enqueue()
          ▲
          │ 實作
MongoBatchUploader              ← csp_lib/mongo/uploader.py
    ├── register_collection()
    ├── enqueue()
    ├── write_immediate()       ← v0.8.2 新增
    ├── writer (property)       ← v0.8.2 新增
    ├── start() / stop()
    └── flush_all()
```

`MongoBatchUploader` 除了滿足 `BatchUploader` Protocol 的兩個方法外，還提供生命週期管理（`start`/`stop`）、強制 flush、即時寫入出口等擴充功能。

- 所有資料按 collection 進入對應的 queue
- 定期或資料量達閾值時批次上傳（`insert_many`）
- v0.8.2：閾值達標立即觸發 flush（`_threshold_event`），不必等待整個 `flush_interval`
- 支援重試機制與容量上限保護

> [!note] v0.8.2 修復：高頻 enqueue 靜默資料遺失
> 修復前，queue 滿後 `popleft()` 會靜默丟棄最舊資料。v0.8.2 引入 `_threshold_event` 機制：`enqueue()` 達到 `batch_size_threshold` 時立即喚醒 `_flush_loop`，避免 queue 累積至上限。

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

| 方法 / 屬性 | 說明 |
|------------|------|
| `register_collection(name)` | 預先註冊 collection 的 queue |
| `enqueue(collection_name, document)` | 將資料加入對應 collection 的 queue；達閾值時立即喚醒 flush |
| `write_immediate(collection_name, document) -> WriteResult` | 繞過 batch queue，直接寫入 MongoDB（v0.8.2） |
| `writer` | read-only property，回傳底層 `MongoWriter` 實例（v0.8.2） |
| `start() -> self` | 啟動定期 flush 任務（支援 fluent interface） |
| `stop()` | 停止 flush 任務，確保所有資料都已上傳 |
| `flush_all()` | 強制將所有 queue 中的資料上傳 |

### write_immediate

```python
async def write_immediate(
    self,
    collection_name: str,
    document: dict[str, Any],
) -> WriteResult:
```

繞過 batch queue，直接將單一文件寫入 MongoDB。用於告警記錄、命令記錄等必須即時落庫的關鍵資料。

- 不進入任何 queue，不觸發 threshold/flush 機制
- 回傳 `csp_lib.mongo.WriteResult`（非 `csp_lib.equipment.transport.WriteResult`）
- 失敗由呼叫方自行處理 `WriteResult`（不做自動重試）

### writer property

```python
@property
def writer(self) -> MongoWriter:
```

回傳底層 `MongoWriter` 實例（v0.8.2 新增）。主要供 [[LocalBufferedUploader]] replay 路徑使用 `write_batch(ordered=False)` 細粒度介面；一般應用不需直接使用此屬性。

## 上傳觸發時機

1. **閾值觸發**（v0.8.2 改進）：單一 collection 累積文件數達到 `batch_size_threshold`，立即喚醒 `_flush_loop`
2. **定期觸發**：每隔 `flush_interval` 秒自動 flush 所有 queue
3. **停止前**：收到停止信號時，先 flush 所有殘留資料

## 重試機制

- 寫入失敗時，將文件回放至 queue 等待重試
- 超過 `max_retry_count` 次後丟棄該批資料並 log error
- 重試計數以 collection 為單位

## Quick Example

```python
from csp_lib.mongo import MongoBatchUploader, UploaderConfig

# 基本使用：批次上傳
uploader = MongoBatchUploader(db).start()
await uploader.enqueue("measurements", {"voltage": 220.5, "current": 5.0})
await uploader.stop()

# 即時寫入（告警、命令等關鍵資料）
result = await uploader.write_immediate("alarms", {"type": "disconnect", "device": "pcs1"})
if not result.success:
    logger.error(f"告警寫入失敗: {result.error_message}")
```

## Common Patterns

### 搭配 LocalBufferedUploader 實現資料不遺失

當 WAN/MongoDB 連線不穩定時，可在前面加一層 [[LocalBufferedUploader]] SQLite 緩衝：

```python
from csp_lib.mongo import MongoBatchUploader
from csp_lib.mongo.local_buffer import LocalBufferedUploader, LocalBufferConfig

mongo_uploader = MongoBatchUploader(db).start()

buffer_cfg = LocalBufferConfig(db_path="./buffer.db", replay_interval=5.0)
local = LocalBufferedUploader(downstream=mongo_uploader, config=buffer_cfg)

async with local:
    # local 的 enqueue 先落 SQLite，背景 replay 到 MongoDB
    await local.enqueue("telemetry", {"ts": 123, "val": 42})
```

### 使用 write_immediate 確保告警即時持久化

```python
from csp_lib.mongo import MongoBatchUploader, WriteResult

uploader = MongoBatchUploader(db).start()

# 告警必須即時落庫，不能等 batch flush
result: WriteResult = await uploader.write_immediate(
    "alarm_history",
    {"alarm_key": "pcs1:DISCONNECT:DISCONNECT", "active": True},
)
```

## 相關頁面

- [[BatchUploader]] — 此類別實作的 Protocol 介面
- [[LocalBufferedUploader]] — SQLite WAL 本地緩衝前置層（v0.8.2）
- [[MongoConfig]] — MongoDB 連線配置
- [[DataUploadManager]] — 使用 MongoBatchUploader 進行設備資料上傳
- [[AlarmPersistenceManager]] — 使用 write_immediate 寫入告警歷史
- [[_MOC Storage]] — Storage 模組總覽
