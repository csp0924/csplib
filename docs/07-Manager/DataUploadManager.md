---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/data/upload.py
---

# DataUploadManager

資料上傳管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`DataUploadManager` 繼承自 [[DeviceEventSubscriber]]，自動將設備讀取資料上傳至 MongoDB。採用觀察者模式訂閱 `AsyncModbusDevice` 的 `read_complete` 與 `disconnected` 事件。

### 職責

1. 訂閱多個 `AsyncModbusDevice` 的事件
2. `read_complete` → 上傳讀取資料並快取結構
3. `disconnected` → 上傳空值記錄（保留巢狀結構，讓前端圖表正確顯示斷線區間）

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `uploader` | [[MongoBatchUploader]] | MongoDB 批次上傳器實例 |

## API

| 方法 | 說明 |
|------|------|
| `subscribe(device, collection_name)` | 訂閱設備事件並指定 MongoDB collection 名稱 |

## 訂閱的事件

| 事件 | 處理 |
|------|------|
| `read_complete` | 將讀取資料加入上傳佇列，並快取值結構 |
| `disconnected` | 從快取結構產生空值記錄並上傳 |

### 斷線空值記錄

斷線時會使用 `nullify_nested()` 函式將快取的值結構轉為空值：

- 保留 `dict` 和 `list` 的巢狀結構
- 所有葉節點值替換為 `None`
- 用途：讓前端圖表能正確顯示斷線區間（有資料點但值為 null）

## 使用範例

```python
from csp_lib.manager import DataUploadManager

manager = DataUploadManager(device=device, uploader=batch_uploader)
```

## 相關頁面

- [[DeviceEventSubscriber]] — 基底類別
- [[MongoBatchUploader]] — 批次上傳器
- [[UnifiedDeviceManager]] — 自動串接資料上傳管理器
