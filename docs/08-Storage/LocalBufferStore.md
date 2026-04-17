---
tags:
  - type/protocol
  - layer/storage
  - status/complete
source: csp_lib/mongo/local_buffer/store.py
created: 2026-04-18
updated: 2026-04-18
version: ">=0.8.2"
---

# LocalBufferStore

`@runtime_checkable` Protocol，定義 `LocalBufferedUploader` 的 backend-agnostic 純 CRUD 介面（v0.8.2）。隸屬於 [[_MOC Storage|Storage 模組]]。

## 設計動機

在 v0.8.2 重構前，`LocalBufferedUploader` 內嵌 SQLite 邏輯，導致：
- 無法在測試中注入 in-memory store
- 無法因應不同部署場景（例如已有 mongod 環境不想再部署 SQLite 檔案）

重構後，`LocalBufferedUploader` 只依賴此 Protocol，具體 backend 由外部注入：

```
LocalBufferedUploader
    ↓ uses
LocalBufferStore (Protocol)
    ↑ implements
SqliteBufferStore     ← v0.8.2（aiosqlite，需 [local-buffer]）
MongoBufferStore      ← v0.8.2（本地 mongod，需 [mongo]）
自訂 InMemoryStore    ← 測試 / 特殊場景
```

## BufferedRow

`fetch_pending` 回傳的唯讀資料快照，`@dataclass(frozen=True, slots=True)`。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `row_id` | `int \| str` | Backend 賦予的 id，用於 `mark_synced` / `bump_retry` 指定目標列。SQLite backend 回傳 `int`；MongoDB backend 回傳 `str`（ObjectId 字串） |
| `collection` | `str` | 目標 MongoDB collection 名稱 |
| `doc_json` | `str` | 序列化後的 document JSON 字串（unicode 直出，非 ASCII 不跳脫） |
| `idempotency_key` | `str` | 用於下游去重的唯一 key；replay 時由上層注入 payload |
| `enqueued_at` | `float` | 入列時間戳（UTC epoch 秒），供監控或審計使用 |
| `retry_count` | `int` | 已累計的 replay 重試次數，僅作診斷用途 |

## Protocol 方法

### Lifecycle

| 方法 | 說明 |
|------|------|
| `async open() -> None` | 開啟底層資源（連線 / 檔案 / schema 建立）；若已開啟則不應重複建立，也不 raise |
| `async close() -> None` | 關閉底層資源；若尚未開啟或已關閉，必須為 no-op，不得拋錯 |

### 寫入

| 方法 | 簽名 | 說明 |
|------|------|------|
| `append` | `(collection, doc_json, idempotency_key, *, synced=False) -> int \| str \| None` | 新增一筆資料；`idempotency_key` 重複視為已存在，回 `None`（非錯誤） |

### 讀取

| 方法 | 簽名 | 說明 |
|------|------|------|
| `fetch_pending` | `(limit: int) -> list[BufferedRow]` | 抓取 `synced=0` 的資料，依 `row_id` 升冪；無資料回空 list |
| `count_pending` | `() -> int` | 回傳 `synced=0` 的資料筆數 |
| `max_synced_sequence` | `() -> int \| str` | 回傳已同步資料中最新的 `row_id`（供監控使用）；無則回 `0` |
| `health_check` | `() -> bool` | 檢查 backend 是否可查詢；`False` 表示尚未開啟或連線錯誤 |

### 狀態更新

| 方法 | 簽名 | 說明 |
|------|------|------|
| `mark_synced` | `(row_ids: Sequence[int \| str]) -> None` | 標記為已同步並記錄 `synced_at`；空序列為 no-op |
| `bump_retry` | `(row_ids: Sequence[int \| str]) -> None` | 將 `retry_count` +1（仍保持 `synced=0`）；空序列為 no-op |
| `delete_synced_before` | `(cutoff_ts: float) -> int` | 刪除 `synced=1` 且 `synced_at < cutoff_ts` 的 row；回傳刪除筆數 |

## 現有實作

| 實作 | 模組 | 狀態 | 說明 |
|------|------|------|------|
| `SqliteBufferStore` | `csp_lib.mongo.local_buffer.sqlite_store` | v0.8.2（可用） | aiosqlite + WAL 模式，需 `csp_lib[local-buffer]` |
| `MongoBufferStore` | `csp_lib.mongo.local_buffer.mongo_store` | v0.8.2（可用） | 本地 mongod 作為 buffer，需 `csp_lib[mongo]`（motor） |
| `FileBufferStore` | （規劃中）| 未定 | JSONL 追加寫入，無額外依賴，適合超輕量部署 |

詳細比較見各實作頁面：[[SqliteBufferStore]] | [[MongoBufferStore]]。

## Row ID 型別設計

Protocol 中所有涉及 `row_id` 的方法，型別均為 `int | str`：

| 方法 | 型別 |
|------|------|
| `BufferedRow.row_id` | `int \| str` |
| `append()` 回傳 | `int \| str \| None` |
| `mark_synced(row_ids)` 參數 | `Sequence[int \| str]` |
| `bump_retry(row_ids)` 參數 | `Sequence[int \| str]` |
| `max_synced_sequence()` 回傳 | `int \| str` |

**設計理由**：不使用 `TypeVar[T]` 泛型，因為上層 `LocalBufferedUploader` 不依賴 row_id 的具體型別（僅在 `mark_synced` / `bump_retry` 時原封不動回傳給 store），泛型只增加複雜度而無實質好處。

**實作慣例**：
- SQLite backend：`row_id` 為 `int`（AUTOINCREMENT），`max_synced_sequence` 回傳 `int`
- MongoDB backend：`row_id` 為 `str`（ObjectId 字串），`max_synced_sequence` 回傳 `str`（無資料時回 `int(0)`）
- 自訂 backend：可自行選擇；無資料時 `max_synced_sequence` 慣例回 `0`（`int`）

## 自訂 Backend 範例

實作 Protocol 只需提供以下 10 個 async method，無需繼承任何基類：

```python
from collections.abc import Sequence
from csp_lib.mongo.local_buffer import LocalBufferStore, BufferedRow

class InMemoryBufferStore:
    """測試用記憶體 buffer，實作 LocalBufferStore Protocol"""

    def __init__(self) -> None:
        self._rows: dict[int, dict] = {}
        self._next_id = 1

    async def open(self) -> None:
        pass  # 記憶體 store 不需要開啟資源

    async def close(self) -> None:
        pass

    async def append(
        self,
        collection: str,
        doc_json: str,
        idempotency_key: str,
        *,
        synced: bool = False,
    ) -> int | str | None:
        # 檢查重複
        for row in self._rows.values():
            if row["idempotency_key"] == idempotency_key:
                return None
        row_id = self._next_id
        self._next_id += 1
        self._rows[row_id] = {
            "row_id": row_id,
            "collection": collection,
            "doc_json": doc_json,
            "idempotency_key": idempotency_key,
            "enqueued_at": 0.0,
            "retry_count": 0,
            "synced": synced,
        }
        return row_id

    async def fetch_pending(self, limit: int) -> list[BufferedRow]:
        rows = [r for r in self._rows.values() if not r["synced"]]
        rows.sort(key=lambda r: r["row_id"])
        return [
            BufferedRow(
                row_id=r["row_id"],
                collection=r["collection"],
                doc_json=r["doc_json"],
                idempotency_key=r["idempotency_key"],
                enqueued_at=r["enqueued_at"],
                retry_count=r["retry_count"],
            )
            for r in rows[:limit]
        ]

    async def mark_synced(self, row_ids: Sequence[int | str]) -> None:
        for rid in row_ids:
            if rid in self._rows:
                self._rows[rid]["synced"] = True

    async def bump_retry(self, row_ids: Sequence[int | str]) -> None:
        for rid in row_ids:
            if rid in self._rows:
                self._rows[rid]["retry_count"] += 1

    async def delete_synced_before(self, cutoff_ts: float) -> int:
        to_del = [k for k, v in self._rows.items() if v["synced"]]
        for k in to_del:
            del self._rows[k]
        return len(to_del)

    async def count_pending(self) -> int:
        return sum(1 for r in self._rows.values() if not r["synced"])

    async def max_synced_sequence(self) -> int | str:
        synced = [r["row_id"] for r in self._rows.values() if r["synced"]]
        return max(synced) if synced else 0

    async def health_check(self) -> bool:
        return True


# 使用自訂 store
store = InMemoryBufferStore()
assert isinstance(store, LocalBufferStore)  # @runtime_checkable，可用 isinstance 驗證

local = LocalBufferedUploader(downstream=mock_uploader, store=store)
```

## Protocol 契約

實作者需滿足以下不變量：

1. **`open` / `close` 冪等**：可多次呼叫，不應 raise 或重複建立資源
2. **`append` idempotency**：相同 `idempotency_key` 第二次呼叫應靜默跳過並回 `None`，不拋錯
3. **`fetch_pending` 排序**：必須依 `row_id` 升冪返回，保證 replay 的因果順序
4. **空序列為 no-op**：`mark_synced([])`、`bump_retry([])` 不應拋錯或產生副作用
5. **`health_check` 不拋錯**：即便 backend 未開啟，也應回 `False` 而非拋例外
6. **Task safety**：實作者自行負責 coroutine 安全，`LocalBufferedUploader` 不加額外保護

## Import 路徑

```python
from csp_lib.mongo import LocalBufferStore, BufferedRow        # 頂層便捷 import
from csp_lib.mongo.local_buffer import LocalBufferStore, BufferedRow  # 子模組 import
```

## 相關頁面

- [[SqliteBufferStore]] — 第一個官方實作（aiosqlite + WAL，需 `[local-buffer]`）
- [[MongoBufferStore]] — 第二個官方實作（本地 mongod，需 `[mongo]`，v0.8.2）
- [[LocalBufferedUploader]] — 使用此 Protocol 的上層 Uploader
- [[_MOC Storage]] — Storage 模組總覽
