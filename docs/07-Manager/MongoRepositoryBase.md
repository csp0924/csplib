---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/base.py
created: 2026-04-23
updated: 2026-04-23
version: ">=0.10.0"
---

# MongoRepositoryBase

Mongo Repository 共用基底 — 收斂三個 Mongo Repository 的 `__init__` / `health_check` 樣板。

> [!info] 回到 [[_MOC Manager]]

## 概述

`MongoRepositoryBase` 合併 `MongoAlarmRepository`、`MongoCommandRepository`、`MongoScheduleRepository` 三者共通的重複程式碼：

- `__init__(db, collection_name)` — 儲存 `_db` / `_collection`
- `health_check()` — 走 `db.command("ping")` 實作

子類只需覆寫 `ensure_indexes()`，宣告自己的索引結構。

> [!note] v0.10.0 重構（PR #110）
> 三個 Mongo Repository 改繼承 `MongoRepositoryBase`。`MongoCommandRepository` 新增
> `collection=` deprecated alias（等同 `collection_name`），便於存量程式碼過渡。

---

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `db` | `AsyncIOMotorDatabase` | Motor 非同步資料庫連線 |
| `collection_name` | `str` | Collection 名稱（子類常以 `COLLECTION_NAME` 類別常數當預設） |

### Protected 屬性

| 屬性 | 說明 |
|------|------|
| `_db` | Motor 資料庫連線（供子類使用） |
| `_collection` | Motor collection（`db[collection_name]`）（供子類使用） |

---

## 方法

| 方法 | 回傳 | 說明 |
|------|------|------|
| `health_check()` | `bool` | 呼叫 `db.command("ping")`；成功回 `True`，任何例外回 `False` |
| `ensure_indexes()` | `None` | **子類必須覆寫**；預設 raise `NotImplementedError` |

---

## Quick Example

### 繼承 MongoRepositoryBase

```python
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING
from csp_lib.manager.base import MongoRepositoryBase

class MongoEventRepository(MongoRepositoryBase):
    COLLECTION_NAME = "events"

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str = COLLECTION_NAME) -> None:
        super().__init__(db, collection_name)

    async def ensure_indexes(self) -> None:
        await self._collection.create_indexes([
            IndexModel([("device_id", ASCENDING), ("timestamp", ASCENDING)]),
        ])

    async def insert_event(self, device_id: str, data: dict) -> None:
        await self._collection.insert_one({"device_id": device_id, **data})
```

### 啟動時建立索引

```python
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient("mongodb://localhost:27017")
db = client["my_db"]

repo = MongoEventRepository(db)
await repo.ensure_indexes()  # 啟動時呼叫一次

# 健康檢查
ok = await repo.health_check()
print(f"MongoDB 連線: {'正常' if ok else '異常'}")
```

---

## 設計備註

- **非 ABC** — 不繼承 `ABC`，以簡化測試 Mock，且允許 caller 透過 `isinstance` 檢查。
- `ensure_indexes` 預設 raise `NotImplementedError`；子類**必須**覆寫，避免忘記宣告索引。
- Motor 為可選依賴（`csp_lib[mongo]`）；`MongoRepositoryBase` 使用 `TYPE_CHECKING` guard，不在 runtime 強制 import。

---

## Import 路徑

```python
from csp_lib.manager.base import MongoRepositoryBase
```

---

## 相關頁面

- [[AlarmPersistenceManager]] — `MongoAlarmRepository` 繼承此基底
- [[WriteCommandManager]] — `MongoCommandRepository` 繼承此基底
- [[ScheduleService]] — `MongoScheduleRepository` 繼承此基底
- [[_MOC Manager]] — 回到模組總覽
