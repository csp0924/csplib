---
tags:
  - type/class
  - layer/storage
  - status/complete
source: csp_lib/mongo/local_buffer/uploader.py
created: 2026-04-18
updated: 2026-04-18
version: ">=0.8.2"
---

# LocalBufferedUploader

本地緩衝上傳器（v0.8.2），隸屬於 [[_MOC Storage|Storage 模組]]。

> [!note] 安裝需求
> - **基本使用**（`LocalBufferedUploader` + 自訂 `LocalBufferStore` 實作）：只需 `csp_lib[mongo]`
> - **使用 `SqliteBufferStore`（預設 backend）**：需額外安裝 `csp_lib[local-buffer]`
>
> ```bash
> uv pip install 'csp0924_lib[mongo]'               # LocalBufferedUploader + MongoBatchUploader
> uv pip install 'csp0924_lib[local-buffer]'        # SqliteBufferStore（aiosqlite 後端）
> uv pip install 'csp0924_lib[mongo,local-buffer]'  # 完整本地緩衝功能
> ```
>
> `pyproject.toml` extras 應按以下 diff 更新（human scope，文件僅提示）：
> ```diff
> -mongo = ["motor>=3.3.0", "aiosqlite>=0.19.0,<0.21"]
> +mongo = ["motor>=3.3.0"]
> +local-buffer = ["aiosqlite>=0.19.0,<0.21"]
> ```

## 概述

`LocalBufferedUploader` 提供「先落地 `LocalBufferStore`，再背景 replay 到 MongoDB」的容錯上傳策略。v0.8.2 重構後，Storage backend 改為可插拔 Protocol，上層 Uploader 不再綁定任何具體實作：

```
上層（DataUploadManager / AlarmPersistenceManager）
      ↓ enqueue / write_immediate
LocalBufferedUploader（此類）
      ↓ append → LocalBufferStore（例如 SqliteBufferStore）
      ↓ 背景 replay（_replay_loop）
下游 MongoBatchUploader
      ↓ write_batch(ordered=False)
MongoDB
```

### 核心保證

- **資料不遺失**：所有寫入先落地 `LocalBufferStore`，下游 MongoDB 斷線時資料不遺失
- **冪等 replay**：透過 `_idempotency_key` + MongoDB 唯一稀疏索引，重複 replay 不產生重複文件
- **零侵入整合**：完整實作 `BatchUploader` Protocol，可無痛替換 `MongoBatchUploader`
- **重啟恢復**：啟動時自動讀取 Store 中未同步的資料，繼續 replay
- **Backend 可插拔**：實作 `LocalBufferStore` Protocol 即可更換 backend（`SqliteBufferStore` / `MongoBufferStore` / 自訂）

## Quick Example

**使用 SqliteBufferStore（輕量節點，無本地 mongod）：**

```python
from csp_lib.mongo import (
    LocalBufferedUploader,
    LocalBufferConfig,
    SqliteBufferStore,
    MongoBatchUploader,
)

# 1. 建立 SQLite backend store（需 csp_lib[local-buffer]）
store = SqliteBufferStore("./data/buffer.db")

# 2. 建立本地緩衝上傳器
buffer_uploader = LocalBufferedUploader(
    downstream=mongo_batch_uploader,
    store=store,
    config=LocalBufferConfig(replay_interval=5.0, retention_seconds=86400 * 7),
)

# 3. 啟動（async context manager）
async with buffer_uploader:
    await buffer_uploader.ensure_indexes()           # 啟動時建立一次 idempotency index
    await buffer_uploader.enqueue("telemetry", {"v": 1})
```

**使用 MongoBufferStore（已有本地 mongod 的站場）：**

```python
from motor.motor_asyncio import AsyncIOMotorClient
from csp_lib.mongo import (
    LocalBufferedUploader,
    LocalBufferConfig,
    MongoBufferStore,
)

# 1. 建立本地 mongod client（由應用程式管理 lifecycle）
local_client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")

# 2. 建立 MongoDB backend store（不需額外 extra，已在 [mongo] 範疇）
store = MongoBufferStore(local_client)

# 3. 組合 LocalBufferedUploader
buffer_uploader = LocalBufferedUploader(
    downstream=mongo_batch_uploader,
    store=store,
    config=LocalBufferConfig(replay_interval=5.0),
)

async with buffer_uploader:
    await buffer_uploader.ensure_indexes()
    await buffer_uploader.enqueue("telemetry", {"v": 1})

local_client.close()  # 應用程式結束時手動關閉
```

## Backend 可插拔（Protocol）

v0.8.2 將 SQLite 邏輯從 `LocalBufferedUploader` 抽離，定義 `LocalBufferStore` Protocol：

| 版本 | 實作 | 依賴 extra | 說明 |
|------|------|-----------|------|
| v0.8.2 | `SqliteBufferStore` | `[local-buffer]`（aiosqlite） | WAL 模式，適合無本地 mongod 的輕量節點 |
| v0.8.2 | `MongoBufferStore` | `[mongo]`（motor，已有即可） | 本地 mongod 作為 buffer，適合雙 MongoDB 拓樸 |
| 自訂 | 任意實作 | — | 只需實作 `LocalBufferStore` Protocol 10 個 async method |

切換 backend 只需替換建構時傳入的 `store` 物件，`LocalBufferedUploader` 本身無需修改：

```python
# 使用 SQLite backend
store = SqliteBufferStore("./buf.db")

# 改用 MongoDB backend（雙 MongoDB 拓樸場景）
from motor.motor_asyncio import AsyncIOMotorClient
local_client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
store = MongoBufferStore(local_client)

buffer_uploader = LocalBufferedUploader(downstream=mongo_uploader, store=store)
```

詳細 Protocol 定義與自訂 backend 實作教學，參見 [[LocalBufferStore]]。

## LocalBufferConfig

`@dataclass(frozen=True, slots=True)` 配置。v0.8.2 起 `db_path` 欄位已移除（移至 `SqliteBufferStore.__init__`）。

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `replay_interval` | `float` | `5.0` | 背景 replay 間隔（秒） |
| `replay_batch_size` | `int` | `500` | 單次 replay 從 store 取出的最大筆數 |
| `cleanup_interval` | `float` | `3600.0` | 已同步資料清理間隔（秒） |
| `retention_seconds` | `float` | `604800.0` | 已同步資料保留秒數（預設 7 天）；超過則刪除 |
| `max_retry_count` | `int` | `100` | 單筆資料的最大 replay 重試次數（超過記 log 但不刪除） |

`__post_init__` 對所有正數欄位做 `ValueError` 驗證。

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `downstream` | `MongoBatchUploader` | 下游上傳器，供 replay 使用 |
| `store` | `LocalBufferStore` | **必填**。本地緩衝儲存後端，實作 `LocalBufferStore` Protocol（v0.8.2 新增） |
| `config` | `LocalBufferConfig \| None` | 本地 buffer 設定；未提供則使用預設值 |

> [!warning] v0.8.2 Breaking Change
> `store` 參數為必填，舊有僅傳 `downstream` 與 `config` 的呼叫方式**不再有效**。
>
> ```python
> # 舊（v0.8.1）
> LocalBufferedUploader(downstream=uploader, config=LocalBufferConfig(db_path="./buf.db"))
>
> # 新（v0.8.2）
> store = SqliteBufferStore("./buf.db")
> LocalBufferedUploader(downstream=uploader, store=store, config=LocalBufferConfig())
> ```

## API

| 方法 / 屬性 | 說明 |
|------------|------|
| `register_collection(collection_name)` | 同步轉發給下游，並記錄 collection 供 `ensure_indexes` 使用 |
| `async enqueue(collection_name, document)` | 寫入 Store buffer（不直接呼叫下游）；資料由 `_replay_loop` 異步送出 |
| `async write_immediate(collection_name, document) -> WriteResult` | 先落地 Store，再立即嘗試同步至下游；無論下游結果如何資料都已落地 |
| `async ensure_indexes(db=None)` | 對所有已註冊 collection 建立 `_idempotency_key` 唯一稀疏索引（應在啟動時呼叫一次） |
| `async health_check() -> bool` | 代理 `store.health_check()`；`True` 表示 backend 正常 |
| `async get_pending_count() -> int` | 代理 `store.count_pending()`；回傳尚未同步的筆數 |
| `async get_sync_cursor() -> int \| str` | 代理 `store.max_synced_sequence()`；最新已同步 row id（SQLite 回 `int`，MongoDB 回 `str`，無資料時回 `0`） |

生命週期方法（繼承自 `AsyncLifecycleMixin`）：

| 方法 | 說明 |
|------|------|
| `async __aenter__` | 呼叫 `store.open()`、刷新計數器、啟動 replay / cleanup 背景任務 |
| `async __aexit__` | set stop_event → gather 背景 task → 最後 drain 一次 → 呼叫 `store.close()` |

## Common Patterns

### 搭配 AlarmPersistenceManager 確保告警不遺失

```python
from csp_lib.mongo import SqliteBufferStore, LocalBufferedUploader, LocalBufferConfig
from csp_lib.manager.alarm import AlarmPersistenceManager, AlarmPersistenceConfig

store = SqliteBufferStore("./alarm_buffer.db")
local = LocalBufferedUploader(downstream=mongo_uploader, store=store)

config = AlarmPersistenceConfig(history_collection="alarm_history")
alarm_manager = AlarmPersistenceManager(
    repository=repo,
    config=config,
    buffered_uploader=local,
)
alarm_manager.subscribe(device)
# 每次告警建立/解除，都先落 Store，再 replay 到 MongoDB
```

### 監控待同步筆數

```python
pending = await local.get_pending_count()
if pending > 10000:
    logger.warning(f"本地 buffer 積壓 {pending} 筆，請確認 MongoDB 連線狀態")
```

### 注入自訂 Backend（測試或特殊場景）

```python
from csp_lib.mongo import LocalBufferStore

class InMemoryBufferStore:
    """測試用記憶體 buffer（實作 LocalBufferStore Protocol）"""
    async def open(self) -> None: ...
    async def close(self) -> None: ...
    # ... 其他 9 個 method

store = InMemoryBufferStore()
local = LocalBufferedUploader(downstream=mock_uploader, store=store)
```

## Gotchas / Tips

- `store` 參數務必在傳入前先初始化（`SqliteBufferStore.__init__` 不呼叫 `open()`，lifecycle 由 `LocalBufferedUploader` 驅動）
- `retention_seconds` 清理的是**已同步**的資料，未同步資料永遠保留直到成功 replay
- `max_retry_count` 超過後**不刪除**資料，只記 warning log；管理員可手動清理或調高重試上限
- `_replay_loop` 以 `replay_batch_size` 為單位，高積壓量時可能需多次 replay 才能清空
- `write_immediate` 的成功判定：Store 落地成功且下游寫入成功才標記 synced；下游失敗時留在 Store 等待背景 replay

## 相關頁面

- [[LocalBufferStore]] — `LocalBufferStore` Protocol 與 `BufferedRow` 定義（可插拔 backend 介面）
- [[SqliteBufferStore]] — aiosqlite WAL 實作（需 `[local-buffer]`，v0.8.2）
- [[MongoBufferStore]] — 本地 mongod 實作（需 `[mongo]`，v0.8.2）
- [[MongoBatchUploader]] — 下游批次上傳器
- [[BatchUploader]] — `LocalBufferedUploader` 實作的 Protocol
- [[DataUploadManager]] — 使用 `buffered_uploader` 參數注入
- [[AlarmPersistenceManager]] — 使用 `buffered_uploader` 參數注入
- [[_MOC Storage]] — Storage 模組總覽
