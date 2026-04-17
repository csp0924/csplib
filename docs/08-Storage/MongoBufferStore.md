---
tags:
  - type/class
  - layer/storage
  - status/complete
source: csp_lib/mongo/local_buffer/mongo_store.py
created: 2026-04-18
updated: 2026-04-18
version: ">=0.8.2"
---

# MongoBufferStore

`LocalBufferStore` 的第二個官方實作，以本地 mongod（motor）作為 buffer backend（v0.8.2）。隸屬於 [[_MOC Storage|Storage 模組]]。

> [!note] 安裝需求
> `MongoBufferStore` 依賴 motor，已包含在 `csp_lib[mongo]` extra，不需額外安裝：
> ```bash
> uv pip install 'csp0924_lib[mongo]'
> ```
> 未安裝 motor 時，建構 `MongoBufferStore` 會拋出：
> ```
> ImportError: MongoBufferStore requires 'motor' / 'pymongo'.
>             Install with: uv pip install 'csp0924_lib[mongo]'
> ```

## 部署情境

`MongoBufferStore` 對應「雙 MongoDB 拓樸」的容錯上傳模式：

```
應用程式
   ↓ enqueue / write_immediate
LocalBufferedUploader
   ↓ append / fetch_pending
MongoBufferStore（本地 mongod，buffer 用途）
   ↓ 背景 replay
MongoBatchUploader → 遠端 mongod（主儲存）
```

**適用場景**：

- 站場已部署本地 mongod（例如用於設備資料快取或 Edge 運算）
- 希望本地 buffer 與遠端 MongoDB 使用相同技術棧（mongodump/mongostat 等工具可通用）
- 需要 buffer 支援較大資料量或多進程共享（SQLite WAL 在多進程情境有限制）
- 部署環境不想引入 aiosqlite 依賴（已有 motor 即可）

> [!warning] 資料庫命名
> `MongoBufferStore` 使用的 `database` / `collection` 名稱，**不得**與下游 `MongoBatchUploader` 寫入的遠端 database 相同，以避免 buffer 資料與業務資料混淆。
>
> 建議慣例：
> - 本地 buffer：`database="csp_local_buffer"`, `collection="pending_documents"`（預設值）
> - 遠端業務資料：`database="bess_telemetry"`, `collection="telemetry"` 等

## Quick Example

```python
from motor.motor_asyncio import AsyncIOMotorClient
from csp_lib.mongo import (
    MongoBufferStore,
    LocalBufferedUploader,
    LocalBufferConfig,
    MongoBatchUploader,
    MongoConfig,
    create_mongo_client,
)

# 1. 本地 mongod client（由應用程式持有 lifecycle）
local_client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")

# 2. 建立 MongoBufferStore（指向本地 mongod 的 buffer collection）
store = MongoBufferStore(
    client=local_client,
    database="csp_local_buffer",    # 預設值，可省略
    collection="pending_documents", # 預設值，可省略
)

# 3. 建立下游遠端 MongoBatchUploader
remote_config = MongoConfig(host="remote-mongo.prod", port=27017)
remote_client = create_mongo_client(remote_config)
remote_uploader = MongoBatchUploader(
    client=remote_client,
    database="bess_telemetry",
)

# 4. 組合 LocalBufferedUploader
buffer_uploader = LocalBufferedUploader(
    downstream=remote_uploader,
    store=store,
    config=LocalBufferConfig(replay_interval=5.0),
)

# 5. 啟動（lifecycle 由 context manager 驅動）
async with buffer_uploader:
    await buffer_uploader.ensure_indexes()
    await buffer_uploader.enqueue("telemetry", {"device_id": "bess_01", "soc": 75.5})
    # store.open() 在此已自動完成（index 已建立）
    # 資料落地本地 mongod，背景 replay 至遠端

# 應用程式結束時關閉本地 client
local_client.close()
```

## 建構參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `client` | `AsyncIOMotorClient` | （必填）| 指向本地 mongod 的 motor client；lifecycle 由外部管理，`close()` 不關此 client |
| `database` | `str` | `"csp_local_buffer"` | Buffer 使用的 database 名稱；不可為空字串 |
| `collection` | `str` | `"pending_documents"` | Buffer 使用的 collection 名稱；不可為空字串 |

`database` 或 `collection` 為空字串時，`__init__` 拋 `ValueError`。

## MongoDB Schema

Buffer collection 的文件結構：

| 欄位 | BSON 型別 | 說明 |
|------|-----------|------|
| `_id` | `ObjectId` | 天然單調遞增（Unix timestamp ms 前綴），作為 row_id |
| `collection` | `str` | 目標下游 MongoDB collection 名稱 |
| `doc_json` | `str` | 序列化後的文件 JSON 字串（unicode 直出，非 ASCII 不跳脫） |
| `idempotency_key` | `str` | 唯一鍵（unique index），用於入列去重 |
| `enqueued_at` | `datetime` | UTC 入列時間 |
| `synced` | `bool` | `True` = 已同步至下游；`False` = 待 replay |
| `synced_at` | `datetime?` | 同步時間（UTC），`synced=False` 時為 `null` |
| `retry_count` | `int` | replay 累計重試次數，僅作診斷用途 |

## Indexes

`open()` 時以 `create_index(...)`（冪等）自動建立以下 3 個 index：

| Index 名稱 | 欄位 | 唯一 | 用途 |
|-----------|------|------|------|
| `idempotency_key_unique` | `{idempotency_key: 1}` | `unique=True` | 入列去重；重複 key 時 `append()` 回 `None` |
| `synced_id_compound` | `{synced: 1, _id: 1}` | 否 | 加速 `fetch_pending`（篩 `synced=False` + 升冪 `_id`） |
| `synced_synced_at_compound` | `{synced: 1, synced_at: 1}` | 否 | 加速 `delete_synced_before`（篩 `synced=True` + 時間範圍） |

Index 已存在時 MongoDB 直接略過（不 raise），`open()` 可安全重複呼叫。

## Row ID 語義

`MongoBufferStore` 的 `row_id` 以 `str(ObjectId)` 表示（24 位元小寫十六進位字串），對應 `LocalBufferStore` Protocol 的 `int | str` 型別。

ObjectId 的結構保證天然單調遞增：

```
 4 bytes  3 bytes   2 bytes      3 bytes
 ╔══════╦═════════╦══════════╦═════════════╗
 ║ Unix ║ Machine ║ Process  ║   Counter   ║
 ║ sec  ║   ID    ║    ID    ║ (random)    ║
 ╚══════╩═════════╩══════════╩═════════════╝
```

這意味著 `fetch_pending` 依 `_id` 升冪排序，等同於「依入列時間排序」，保證 replay 的因果順序。

> [!note] 字串排序 ≠ 數值排序
> ObjectId 字串的字典序（lexicographic）不等同於時間序。跨秒範圍的 ObjectId 字串若需比較時序，應先轉回 `ObjectId` 物件比較。
>
> 在 `LocalBufferedUploader` 中，`_synced_cursor` 儲存「最後一筆成功同步的 row_id」，純粹作為監控用途，**不做字串大小比較**。

## API Reference

### Lifecycle

| 方法 | 說明 |
|------|------|
| `async open() -> None` | 建立 3 個 index（冪等）；重複呼叫為 no-op；index 建立失敗只 log warning，不 raise |
| `async close() -> None` | no-op；motor client lifecycle 由外部管理，`close()` 僅重置 `_opened` 旗標 |

### CRUD（實作 `LocalBufferStore` Protocol）

| 方法 | 簽名 | 說明 |
|------|------|------|
| `append` | `(collection, doc_json, idempotency_key, *, synced=False) -> int \| str \| None` | 新增一筆資料；`idempotency_key` 重複（DuplicateKeyError）時跳過並回 `None` |
| `fetch_pending` | `(limit: int) -> list[BufferedRow]` | 抓取 `synced=False` 的資料，依 `_id` 升冪排序；無資料回空 list；`limit <= 0` 回空 list |
| `mark_synced` | `(row_ids: Sequence[int \| str]) -> None` | 標記為 `synced=True` 並記錄 `synced_at`；非合法 ObjectId 字串會被 debug log 後略過 |
| `bump_retry` | `(row_ids: Sequence[int \| str]) -> None` | 將 `retry_count` +1；非合法 ObjectId 字串略過 |
| `delete_synced_before` | `(cutoff_ts: float) -> int` | 刪除 `synced=True` 且 `synced_at < cutoff_ts` 的 row；回傳刪除筆數 |
| `count_pending` | `() -> int` | 回傳 `synced=False` 的資料筆數 |
| `max_synced_sequence` | `() -> int \| str` | 回傳最新已同步 row 的 ObjectId 字串；無已同步資料則回 `0`（`int`，符合 Protocol 慣例） |
| `health_check` | `() -> bool` | 以 `admin.command("ping")` 驗證 motor client 可用；未 open 或連線失敗回 `False` |

### 內部工具方法

| 方法 | 說明 |
|------|------|
| `_coerce_object_ids(row_ids)` | 將 `int \| str` 序列轉為 `ObjectId` list；非字串型別或無法解析的字串靜默略過（debug log） |

## 與 SqliteBufferStore 的對比

| 面向 | `SqliteBufferStore` | `MongoBufferStore` |
|------|---------------------|---------------------|
| 依賴 extra | `csp_lib[local-buffer]`（aiosqlite） | `csp_lib[mongo]`（motor，已有即可） |
| 儲存後端 | 本地 SQLite WAL 檔 | 本地 mongod |
| 適用場景 | 無本地 mongod 的輕量節點 | 已有本地 mongod 的站場（雙 MongoDB 拓樸） |
| Row ID 型別 | `int`（AUTOINCREMENT） | `str`（ObjectId 字串） |
| 查詢語言 | SQL | MongoDB Query Language |
| 並發控制 | `asyncio.Lock`（單連線序列化） | motor 原生（event loop，天然序列化） |
| Replication | 需手動備份 SQLite 檔 | 可使用 MongoDB Replica Set |
| Client lifecycle | `open()` 建立連線、`close()` 關閉 | Client 由外部管理，`close()` 為 no-op |

## Common Patterns

### 搭配 AlarmPersistenceManager 確保告警不遺失

```python
from motor.motor_asyncio import AsyncIOMotorClient
from csp_lib.mongo import MongoBufferStore, LocalBufferedUploader, LocalBufferConfig
from csp_lib.manager.alarm import AlarmPersistenceManager, AlarmPersistenceConfig

local_client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
store = MongoBufferStore(local_client)

local = LocalBufferedUploader(downstream=remote_uploader, store=store)

alarm_manager = AlarmPersistenceManager(
    repository=repo,
    config=AlarmPersistenceConfig(history_collection="alarm_history"),
    buffered_uploader=local,
)
```

### 健康檢查

```python
is_healthy = await store.health_check()
if not is_healthy:
    logger.warning("本地 mongod buffer 不可用，請確認本地 MongoDB 服務狀態")
```

### 監控積壓量

```python
pending = await buffer_uploader.get_pending_count()
if pending > 5000:
    logger.warning(f"本地 mongod buffer 積壓 {pending} 筆，請確認遠端 MongoDB 連線")
```

## Gotchas / Tips

- **Client lifecycle 由外部管理**：`MongoBufferStore.close()` 是 no-op，**不會**關閉 motor client。應用程式結束時需自行呼叫 `local_client.close()`。
- **`open()` 在 `async with LocalBufferedUploader` 進入時自動呼叫**：通常不需手動呼叫 `store.open()`，由 `LocalBufferedUploader._on_start` 代為呼叫。
- **`database` 與遠端業務資料庫應分開**：預設 `csp_local_buffer` 是為 buffer 保留的，請勿與遠端 `MongoBatchUploader` 使用的 database 混用。
- **Index 建立失敗不 raise**：`open()` 時若 index ensure 失敗（例如 mongod 暫時不可用），僅 log warning 並繼續標記 `_opened=True`。建議監控 log 以偵測啟動期 index 缺失。
- **非合法 ObjectId 的 row_id 會被靜默略過**：`mark_synced` / `bump_retry` 傳入無法解析的 id 不拋錯，只記 debug log。這是 Protocol 允許的行為（空序列 = no-op 語義延伸）。
- **`max_synced_sequence()` 無資料時回 `int(0)` 而非空字串**：符合 Protocol 約定，呼叫方需注意型別為 `int | str`。

## 相關頁面

- [[LocalBufferStore]] — `LocalBufferStore` Protocol 定義與 `BufferedRow` dataclass
- [[SqliteBufferStore]] — 第一個官方實作（aiosqlite + WAL）
- [[LocalBufferedUploader]] — 使用此 store 的上層 Uploader
- [[MongoBatchUploader]] — 下游遠端批次上傳器（replay 目標）
- [[_MOC Storage]] — Storage 模組總覽
