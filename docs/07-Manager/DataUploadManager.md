---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/data/upload.py
created: 2026-02-17
updated: 2026-04-18
version: ">=0.8.2"
---

# DataUploadManager

資料上傳管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

> [!warning] v0.6.0 Changed
> 建構子參數 `uploader` 的型別從 `MongoBatchUploader` 放寬為 [[BatchUploader]] Protocol。既有程式碼傳入 `MongoBatchUploader` 仍然相容，無需修改。

## 概述

`DataUploadManager` 繼承自 [[DeviceEventSubscriber]]，自動將設備讀取資料上傳至 MongoDB（或任何實作 [[BatchUploader]] Protocol 的上傳器）。採用觀察者模式訂閱 `AsyncModbusDevice` 的 `read_complete` 與 `disconnected` 事件。

### 職責

1. 訂閱多個 `AsyncModbusDevice` 的事件
2. `read_complete` → 上傳讀取資料並快取結構
3. `disconnected` → 上傳空值記錄（保留巢狀結構，讓前端圖表正確顯示斷線區間）

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `uploader` | [[BatchUploader]] | 批次上傳器實例（實作 `BatchUploader` Protocol） |
| `buffered_uploader` | `LocalBufferedUploader \| None` | 選擇性 SQLite 緩衝層（keyword-only，v0.8.2 新增）。提供時所有 enqueue 改走本地 SQLite buffer，下游 MongoDB 斷線期間資料不遺失；`None` 時行為與舊版完全一致 |

> [!note] v0.8.2 opt-in 本地緩衝
> `buffered_uploader` 注入時，`DataUploadManager` 內部將 `self._uploader` 替換為 `LocalBufferedUploader`。`uploader` 參數仍需傳入（作為 `LocalBufferedUploader` 的下游），但 `DataUploadManager` 本身只與 `LocalBufferedUploader` 互動。

## API

| 方法 | 說明 |
|------|------|
| `configure(device_id, collection_name, save_interval=None)` | 預先配置設備的上傳參數（必須在 `subscribe()` 之前呼叫） |
| `subscribe(device)` | 訂閱設備事件；若未呼叫 `configure()` 則使用預設 collection `"device_data"` |
| `unsubscribe(device)` | 取消訂閱設備事件（繼承自 [[DeviceEventSubscriber]]） |

### configure 參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `device_id` | `str` | 必填 | 設備 ID |
| `collection_name` | `str` | 必填 | 資料上傳的 MongoDB collection 名稱 |
| `save_interval` | `float \| None` | `None` | 最小儲存間隔（秒）。`None` 或 `0` 表示每次讀取都儲存 |

## 訂閱的事件

| 事件 | 處理 |
|------|------|
| `read_complete` | 將讀取資料加入上傳佇列，並快取值結構。若設有 `save_interval`，僅在超過間隔時上傳 |
| `disconnected` | 從快取結構產生空值記錄並上傳 |

### 斷線空值記錄

斷線時會使用 `nullify_nested()` 函式將快取的值結構轉為空值：

- 保留 `dict` 和 `list` 的巢狀結構
- 所有葉節點值替換為 `None`
- 用途：讓前端圖表能正確顯示斷線區間（有資料點但值為 null）

### 降頻儲存

透過 `configure()` 的 `save_interval` 參數控制每台設備的最小儲存間隔。使用 `time.monotonic()` 計時，確保即使系統時間調整也能正確運作。

## Quick Example

```python
from csp_lib.mongo import MongoBatchUploader
from csp_lib.manager.data import DataUploadManager

# 基本使用（不需要 local buffer）
uploader = MongoBatchUploader(db=mongo_db)

async with uploader:
    data_manager = DataUploadManager(uploader)

    # 配置設備的上傳參數
    data_manager.configure("meter_001", collection_name="meter_data", save_interval=5.0)
    data_manager.subscribe(meter_device)

    # 設備讀取時資料自動上傳（每 5 秒最多一次）
    # 設備斷線時自動上傳空值記錄
```

## Common Patterns

### 搭配 LocalBufferedUploader 實現資料不遺失（v0.8.2）

部署於 WAN 不穩定環境時，可注入 `LocalBufferedUploader` 確保 MongoDB 斷線期間資料不遺失：

```python
from csp_lib.mongo import MongoBatchUploader
from csp_lib.mongo.local_buffer import LocalBufferedUploader, LocalBufferConfig
from csp_lib.manager.data import DataUploadManager

mongo_uploader = MongoBatchUploader(db=mongo_db).start()

buffer_cfg = LocalBufferConfig(
    db_path="./device_buffer.db",
    replay_interval=5.0,
    retention_seconds=86400.0 * 7,  # 保留 7 天
)
local = LocalBufferedUploader(downstream=mongo_uploader, config=buffer_cfg)

async with local:
    # 注入 buffered_uploader，DataUploadManager 的 enqueue 改走本地 SQLite
    data_manager = DataUploadManager(uploader=mongo_uploader, buffered_uploader=local)
    data_manager.configure("meter_001", "meter_data", save_interval=5.0)
    data_manager.subscribe(meter_device)
```

## 相關頁面

- [[DeviceEventSubscriber]] — 基底類別
- [[BatchUploader]] — 上傳器 Protocol 定義
- [[MongoBatchUploader]] — MongoDB 批次上傳器實作
- [[LocalBufferedUploader]] — SQLite WAL 本地緩衝層（v0.8.2）
- [[UnifiedDeviceManager]] — 自動串接資料上傳管理器
