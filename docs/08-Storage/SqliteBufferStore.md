---
tags:
  - type/class
  - layer/storage
  - status/complete
source: csp_lib/mongo/local_buffer/sqlite_store.py
created: 2026-04-18
updated: 2026-04-18
version: ">=0.8.2"
---

# SqliteBufferStore

`LocalBufferStore` 的第一個官方實作，基於 `aiosqlite` + WAL 模式提供 crash-safe 的本地緩衝儲存（v0.8.2）。另一個實作為 [[MongoBufferStore]]（本地 mongod backend）。隸屬於 [[_MOC Storage|Storage 模組]]。

> [!note] 安裝需求
> 需安裝獨立 extra：
> ```bash
> uv pip install 'csp0924_lib[local-buffer]'
> ```
> 未安裝 `aiosqlite` 時，建構 `SqliteBufferStore` 會拋出：
> ```
> ImportError: SqliteBufferStore requires 'aiosqlite' package.
>             Install with: uv pip install 'csp0924_lib[local-buffer]'
> ```

## Quick Example

```python
from csp_lib.mongo import (
    SqliteBufferStore,
    LocalBufferedUploader,
    LocalBufferConfig,
    MongoBatchUploader,
)

# 建立 store（不會立即開啟連線，lifecycle 由 LocalBufferedUploader 驅動）
store = SqliteBufferStore(
    db_path="./data/buffer.db",
    wal_mode=True,           # 預設 True（推薦）
    synchronous="NORMAL",    # 預設 NORMAL（效能 / 安全性平衡）
)

# 注入 LocalBufferedUploader
async with LocalBufferedUploader(downstream=mongo_uploader, store=store) as buf:
    await buf.ensure_indexes()
    await buf.enqueue("telemetry", {"device_id": "bess_01", "soc": 75.5})
```

## 建構參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `db_path` | `str \| Path` | （必填）| SQLite 檔案路徑；建議使用 persistent volume 的絕對路徑 |
| `wal_mode` | `bool` | `True` | 啟用 WAL journal 模式（推薦，提高並發讀取效能） |
| `synchronous` | `Literal["OFF", "NORMAL", "FULL"]` | `"NORMAL"` | SQLite `synchronous` PRAGMA 值，控制 durability/效能 tradeoff |

`db_path` 不可為空字串，否則 `__init__` 拋 `ValueError`。

## SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS pending_documents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_name  TEXT    NOT NULL,
    document_json    TEXT    NOT NULL,
    idempotency_key  TEXT    NOT NULL,
    enqueued_at      REAL    NOT NULL,
    synced           INTEGER NOT NULL DEFAULT 0,
    synced_at        REAL,
    retry_count      INTEGER NOT NULL DEFAULT 0
);

-- 加速 fetch_pending 查詢（依 synced + collection + id 排序）
CREATE INDEX IF NOT EXISTS idx_pending_synced
    ON pending_documents (synced, collection_name, id);

-- 加速 delete_synced_before 清理查詢
CREATE INDEX IF NOT EXISTS idx_pending_synced_at
    ON pending_documents (synced, synced_at);

-- idempotency_key 唯一約束（重複入列時 INSERT OR IGNORE 路徑）
CREATE UNIQUE INDEX IF NOT EXISTS idx_idempotency_key
    ON pending_documents (idempotency_key);
```

Schema 在 `open()` 時以 `CREATE TABLE/INDEX IF NOT EXISTS` 建立，重複呼叫冪等。

## PRAGMA 設定

| PRAGMA | 預設值 | 說明 |
|--------|--------|------|
| `journal_mode=WAL` | 啟用（`wal_mode=True`） | Write-Ahead Logging；讀寫並發、crash 安全；建議保持開啟 |
| `synchronous=NORMAL` | 可調整 | 見下表 |
| `foreign_keys=ON` | 固定開啟 | 啟用外鍵約束（目前 schema 無外鍵，保留為最佳實踐） |

### `synchronous` 選項對照

| 值 | Durability | 效能 | 適用場景 |
|----|-----------|------|---------|
| `"FULL"` | 最高（每次 commit 均 fsync） | 最慢 | 關鍵資料，不容許任何資料損失 |
| `"NORMAL"` | 高（WAL checkpoint 時 fsync） | **推薦預設** | 一般工業 BESS 場景 |
| `"OFF"` | 低（OS cache，crash 可能損失） | 最快 | 測試環境或可接受資料損失場景 |

> [!warning] `synchronous="OFF"` 注意事項
> 系統崩潰（非正常關機）時，WAL 檔案可能未同步到主資料庫，導致資料損失。
> 生產環境建議使用 `"NORMAL"` 或 `"FULL"`。

## API Reference

### Lifecycle

| 方法 | 說明 |
|------|------|
| `async open() -> None` | 開啟 SQLite 連線、設置 PRAGMA 並建立 schema；重複呼叫為 no-op |
| `async close() -> None` | 關閉 SQLite 連線；重複呼叫或尚未開啟為 no-op，不拋錯 |

### CRUD（實作 `LocalBufferStore` Protocol）

| 方法 | 說明 |
|------|------|
| `async append(collection, doc_json, idempotency_key, *, synced=False) -> int \| None` | 新增一筆資料；`idempotency_key` 重複時跳過並回 `None` |
| `async fetch_pending(limit) -> list[BufferedRow]` | 抓取尚未同步的資料，依 `row_id` 升冪排序 |
| `async mark_synced(row_ids: Sequence[int]) -> None` | 將指定 row 標記為已同步，記錄 `synced_at` |
| `async bump_retry(row_ids: Sequence[int]) -> None` | 將指定 row 的 `retry_count` +1 |
| `async delete_synced_before(cutoff_ts: float) -> int` | 刪除 `synced=1` 且 `synced_at < cutoff_ts` 的 row；回傳刪除筆數 |
| `async count_pending() -> int` | 回傳 `synced=0` 的資料筆數 |
| `async max_synced_sequence() -> int` | 回傳已同步資料中最大的 `row_id`；無資料則回 `0` |
| `async health_check() -> bool` | 執行 `SELECT 1` 確認連線可用；連線未開啟或例外時回 `False` |

### 並發控制

所有 CUD 操作（`append`、`mark_synced`、`bump_retry`、`delete_synced_before`）均透過 `asyncio.Lock` 序列化，避免多 coroutine 同時 commit 引起 SQLite 鎖衝突。`fetch_pending`、`count_pending`、`max_synced_sequence`、`health_check` 為純讀取，不持鎖。

## 與 LocalBufferedUploader 組合

```python
from csp_lib.mongo import (
    SqliteBufferStore,
    LocalBufferedUploader,
    LocalBufferConfig,
)

store = SqliteBufferStore(
    db_path="/var/lib/bess/local_buffer.db",  # 建議絕對路徑 + persistent volume
    wal_mode=True,
    synchronous="NORMAL",
)

cfg = LocalBufferConfig(
    replay_interval=5.0,
    replay_batch_size=500,
    cleanup_interval=3600.0,
    retention_seconds=86400.0 * 7,  # 保留 7 天
)

async with LocalBufferedUploader(downstream=mongo_uploader, store=store, config=cfg) as buf:
    await buf.ensure_indexes()
    # 開始正常寫入...
```

## Gotchas / Tips

- **`db_path` 建議使用絕對路徑**，避免 CWD 不確定造成不同啟動位置產生多個 DB 檔
- **Persistent Volume**：部署在 Docker/K8s 時，`db_path` 必須掛在 persistent volume，否則 container 重啟後資料遺失
- **單一連線 + Lock 序列化**：`SqliteBufferStore` 使用單一 `aiosqlite.Connection`，所有寫入已自動序列化，呼叫方不需額外同步
- **`wal_mode=False` 情境**：若已有外部工具鎖住同一 DB 檔且不相容 WAL，可設為 `False` 切回 DELETE journal；一般情況不需調整
- **`open()` 已冪等**：可安全重複呼叫（例如健康恢復後嘗試重連），不會重建 schema 或重複開啟

## 相關頁面

- [[LocalBufferStore]] — `LocalBufferStore` Protocol 定義與自訂 backend 教學
- [[MongoBufferStore]] — 第二個官方實作（本地 mongod backend，v0.8.2）
- [[LocalBufferedUploader]] — 使用此 store 的上層 Uploader
- [[BufferedRow]] — `fetch_pending` 回傳的 frozen dataclass（定義於 `LocalBufferStore.md`）
- [[_MOC Storage]] — Storage 模組總覽
