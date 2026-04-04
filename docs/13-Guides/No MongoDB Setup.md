---
tags:
  - type/guide
  - layer/manager
  - status/complete
created: 2026-04-04
updated: 2026-04-04
version: ">=0.6.1"
---

# 不使用 MongoDB 運行

> [!info] v0.6.1 新增
> `NullBatchUploader`、`InMemoryBatchUploader`、`InMemoryAlarmRepository`、
> `InMemoryCommandRepository` 均在 v0.6.1 加入，讓 csp_lib 可在零外部依賴下運行。

csp_lib 的 Manager 層透過 Protocol 解耦儲存後端，讓你在不安裝 MongoDB 的情況下運行完整的設備管理系統。
這對以下場景特別有用：

- **本地開發 / Demo**：不想在開發機上啟動 MongoDB
- **單元測試 / 整合測試**：需要可控的記憶體後端，方便驗證資料
- **純控制場景**：不需要持久化，只需設備通訊與控制策略
- **嵌入式或邊緣部署**：資源受限，外部 DB 不可用

---

## Quick Example

```python
import asyncio
from csp_lib.manager import (
    InMemoryAlarmRepository,
    InMemoryBatchUploader,
    InMemoryCommandRepository,
    UnifiedConfig,
    UnifiedDeviceManager,
)

async def main() -> None:
    alarm_repo = InMemoryAlarmRepository()
    command_repo = InMemoryCommandRepository()
    uploader = InMemoryBatchUploader()

    config = UnifiedConfig(
        alarm_repository=alarm_repo,
        command_repository=command_repo,
        mongo_uploader=uploader,   # 替代 MongoBatchUploader
        redis_client=None,
        notification_dispatcher=None,
    )

    manager = UnifiedDeviceManager(config)
    # manager.register(device, collection_name="my_data")

    async with manager:
        await asyncio.sleep(5)

    # 檢視記憶體中的資料
    docs = uploader.get_documents("my_data")
    print(f"已收集 {len(docs)} 筆文件")

asyncio.run(main())
```

---

## 三種上傳器選擇

### NullBatchUploader — 純丟棄

完全不儲存任何資料，適合**純控制場景**或**生產環境想暫時關閉上傳**。

```python
from csp_lib.manager import NullBatchUploader

uploader = NullBatchUploader()
# register_collection / enqueue 皆為 no-op
# health_check() 永遠回傳 True
```

| 方法 | 行為 |
|------|------|
| `register_collection(name)` | no-op，不做任何事 |
| `enqueue(name, doc)` | no-op，靜默丟棄文件 |
| `health_check()` | 永遠回傳 `True` |

> [!tip]
> 若你的應用程式完全不需要資料上傳（例如純 PQ 控制或 Demo），`NullBatchUploader`
> 是最輕量的選擇，不佔用任何記憶體。

### InMemoryBatchUploader — 記憶體暫存

將文件存在記憶體中，並提供查詢輔助方法。適合**測試驗證**與**開發除錯**。

```python
from csp_lib.manager import InMemoryBatchUploader

uploader = InMemoryBatchUploader()

# 查詢特定 collection 的所有文件
docs = uploader.get_documents("pcs_data")

# 查詢所有 collection
all_docs = uploader.get_all_documents()
# {"pcs_data": [...], "meter_data": [...]}

# 清除特定 collection
uploader.clear("pcs_data")

# 清除全部
uploader.clear()
```

| 方法 | 說明 |
|------|------|
| `register_collection(name)` | 預先登記 collection 名稱 |
| `enqueue(name, doc)` | 將文件加入對應 collection |
| `get_documents(name)` | 取得指定 collection 的文件列表副本 |
| `get_all_documents()` | 取得所有 collection 的映射副本 |
| `clear(name=None)` | 清除指定或全部 collection |
| `health_check()` | 永遠回傳 `True` |

> [!note]
> `InMemoryBatchUploader` 使用 `threading.Lock` 保護內部狀態，在 asyncio 事件迴圈
> 中從多個協程並發存取是安全的。

### 自訂 BatchUploader — 對接其他資料庫

若你想對接 PostgreSQL、SQLite 或其他後端，只需實作 [[BatchUploader]] Protocol：

```python
from typing import Any
import asyncpg  # 範例：PostgreSQL

class PostgresBatchUploader:
    """實作 BatchUploader Protocol 的 PostgreSQL 版本"""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)

    def register_collection(self, collection_name: str) -> None:
        # PostgreSQL 版本：確保對應資料表存在
        # 實際應用中可於此處建立 table（或預先建立）
        pass

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        if self._pool is None:
            return
        import json
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {collection_name} (data) VALUES ($1)",
                json.dumps(document),
            )

    async def health_check(self) -> bool:
        if self._pool is None:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False
```

> [!warning]
> Protocol 合規性（`isinstance` 檢查）僅驗證 `register_collection` 和 `enqueue` 兩個方法。
> 若你的實作需要非同步初始化（如連接池），記得在注入 `UnifiedConfig` 之前手動呼叫初始化方法。

---

## 完整範例：InMemory 全套配合 UnifiedDeviceManager

以下展示使用三種 InMemory 實作取代 MongoDB 的完整工作流程，
對應 `examples/19_custom_database.py`：

```python
import asyncio
from csp_lib.manager import (
    InMemoryAlarmRepository,
    InMemoryBatchUploader,
    InMemoryCommandRepository,
    UnifiedConfig,
    UnifiedDeviceManager,
    WriteCommand,
)

async def run_without_mongodb(pcs_device, meter_device) -> None:
    # ── 1. 建立三個 InMemory 後端 ──
    alarm_repo = InMemoryAlarmRepository()
    command_repo = InMemoryCommandRepository()
    uploader = InMemoryBatchUploader()

    # ── 2. 組裝 UnifiedConfig ──
    config = UnifiedConfig(
        alarm_repository=alarm_repo,
        command_repository=command_repo,
        mongo_uploader=uploader,
        redis_client=None,
        notification_dispatcher=None,
    )

    # ── 3. 建立並啟動 Manager ──
    manager = UnifiedDeviceManager(config)
    manager.register(pcs_device, collection_name="pcs_data")
    manager.register(meter_device, collection_name="meter_data")

    async with manager:
        # 等待數次讀取週期
        await asyncio.sleep(5.0)

        # ── 4. 查詢 InMemory 中的資料 ──

        # 告警：查詢目前進行中的告警
        active_alarms = await alarm_repo.get_active_alarms()
        print(f"進行中告警: {len(active_alarms)} 筆")

        # 指令：執行一次寫入並查看記錄
        if manager.command_manager is not None:
            cmd = WriteCommand(device_id="pcs_01", point_name="p_set", value=-50.0)
            result = await manager.command_manager.execute(cmd)
            print(f"指令結果: {result.status.value}")

        # 上傳資料：查看已收集的文件
        pcs_docs = uploader.get_documents("pcs_data")
        print(f"PCS 上傳文件數: {len(pcs_docs)}")

        # 取得所有告警記錄（含已解除）
        all_alarms = alarm_repo.get_all_records()
        print(f"告警記錄總數: {len(all_alarms)}")

        # 取得所有指令記錄
        all_cmds = command_repo.get_all_records()
        print(f"指令記錄總數: {len(all_cmds)}")
```

---

## 各元件替換對照表

| MongoDB 元件 | InMemory 替代 | 說明 |
|-------------|--------------|------|
| `MongoBatchUploader` | `InMemoryBatchUploader` | 資料上傳（DataUploadManager） |
| `NullBatchUploader` | — | 完全不上傳 |
| `MongoAlarmRepository` | `InMemoryAlarmRepository` | 告警持久化（AlarmPersistenceManager） |
| `MongoCommandRepository` | `InMemoryCommandRepository` | 指令記錄（WriteCommandManager） |
| `MongoScheduleRepository` | 需自行實作 | 排程規則（ScheduleService） |

> [!note]
> `ScheduleService` 的 `ScheduleRepository` 目前尚無內建 InMemory 實作。
> 若需測試排程功能，請參考 [[Custom Repository]] 自行實作。

---

## 相關資源

- [[BatchUploader]] — Protocol 介面定義
- [[InMemoryBatchUploader]] — 記憶體上傳器 API 參考
- [[UnifiedDeviceManager]] — 統一設備管理器
- [[Custom Repository]] — 如何實作自訂 Repository Protocol
- [[AlarmPersistenceManager]] — 告警持久化管理器
- [[WriteCommandManager]] — 指令管理器
