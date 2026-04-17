---
tags:
  - type/protocol
  - layer/manager
  - status/complete
source: csp_lib/manager/base.py
created: 2026-04-04
updated: 2026-04-18
version: ">=0.8.2"
---

# BatchUploader

批次上傳器 Protocol，隸屬於 [[_MOC Manager|Manager 模組]]。

> [!info] v0.6.0 新增
> `BatchUploader` 是 v0.6.0 新增的 `@runtime_checkable` Protocol，用以解耦 [[DataUploadManager]] 對 [[MongoBatchUploader]] 的直接依賴。

## 概述

`BatchUploader` 定義了批次上傳器的最小介面，讓上層模組（如 [[DataUploadManager]]、`StatisticsManager`）可以注入任何實作此 Protocol 的上傳器，而非硬依賴 MongoDB 實作。

```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class BatchUploader(Protocol):
    def register_collection(self, collection_name: str) -> None: ...
    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None: ...
```

## 方法

| 方法 | 說明 |
|------|------|
| `register_collection(collection_name)` | 註冊 collection 名稱，確保上傳器為該 collection 準備好佇列 |
| `enqueue(collection_name, document)` | 將文件加入上傳佇列（async） |

### register_collection

```python
def register_collection(self, collection_name: str) -> None
```

| 參數 | 型別 | 說明 |
|------|------|------|
| `collection_name` | `str` | MongoDB collection 名稱 |

### enqueue

```python
async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None
```

| 參數 | 型別 | 說明 |
|------|------|------|
| `collection_name` | `str` | 目標 collection 名稱 |
| `document` | `dict[str, Any]` | 要上傳的文件 |

## 既有實作

| 類別 | 模組 | 說明 |
|------|------|------|
| [[MongoBatchUploader]] | `csp_lib.mongo` | MongoDB 批次上傳器（組合 BatchQueue + MongoWriter） |
| [[LocalBufferedUploader]] | `csp_lib.mongo.local_buffer` | SQLite WAL 本地緩衝前置層，需 aiosqlite（v0.8.2） |

## 自訂實作範例

```python
from csp_lib.manager.base import BatchUploader

class InMemoryUploader:
    """測試用的記憶體上傳器"""

    def __init__(self) -> None:
        self._collections: dict[str, list[dict]] = {}

    def register_collection(self, collection_name: str) -> None:
        self._collections.setdefault(collection_name, [])

    async def enqueue(self, collection_name: str, document: dict) -> None:
        self._collections[collection_name].append(document)

# runtime_checkable 驗證
assert isinstance(InMemoryUploader(), BatchUploader)
```

## Quick Example

```python
from csp_lib.manager.base import BatchUploader
from csp_lib.mongo import MongoBatchUploader

# 使用既有的 MongoDB 實作
uploader: BatchUploader = MongoBatchUploader(db=mongo_db)
uploader.register_collection("device_data")
await uploader.enqueue("device_data", {"device_id": "dev_001", "value": 42})
```

## 相關頁面

- [[DeviceEventSubscriber]] — 同在 `base.py` 中定義的基底類別
- [[MongoBatchUploader]] — MongoDB 實作
- [[LocalBufferedUploader]] — SQLite WAL 本地緩衝前置層（v0.8.2）
- [[DataUploadManager]] — 主要消費者
- [[UnifiedDeviceManager]] — 透過 `UnifiedConfig.mongo_uploader` 注入
