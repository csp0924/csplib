---
tags:
  - type/guide
  - layer/manager
  - status/complete
created: 2026-04-04
updated: 2026-04-04
version: ">=0.6.1"
---

# 實作自訂 Repository

> [!info] v0.6.1 新增
> csp_lib v0.6.1 正式公開三個 Repository Protocol，並提供 InMemory 參考實作，
> 讓你可以對接任何資料庫後端。

csp_lib 的 Manager 層採用依賴倒置原則：業務邏輯（`AlarmPersistenceManager`、
`WriteCommandManager`、`ScheduleService`）依賴 Protocol 介面而非具體實作。
只要你的類別滿足 Protocol 的方法簽名，就可以無縫替換儲存後端。

本指南以 **SQLite** 為例，展示如何實作三個 Repository Protocol，
並注入至對應的 Manager 中。

---

## Quick Example

```python
import asyncio
import aiosqlite
from csp_lib.manager import AlarmPersistenceManager, WriteCommandManager

# 假設你已經實作了 SQLiteAlarmRepository（見下方）
from my_app.repos import SQLiteAlarmRepository, SQLiteCommandRepository

async def main() -> None:
    alarm_repo = SQLiteAlarmRepository("my_alarms.db")
    await alarm_repo.initialize()

    command_repo = SQLiteCommandRepository("my_commands.db")
    await command_repo.initialize()

    # 注入自訂 Repository
    alarm_manager = AlarmPersistenceManager(alarm_repo)
    command_manager = WriteCommandManager(command_repo)

    # 接下來正常使用 Manager — 底層使用你的 SQLite 實作
    print("自訂 Repository 注入完成")

asyncio.run(main())
```

---

## Repository Protocol 總覽

csp_lib 定義了三個 Repository Protocol，分別對應告警、指令、排程三個業務域：

| Protocol | 路徑 | 使用者 |
|----------|------|--------|
| `AlarmRepository` | `csp_lib.manager.alarm.repository` | [[AlarmPersistenceManager]] |
| `CommandRepository` | `csp_lib.manager.command.repository` | [[WriteCommandManager]] |
| `ScheduleRepository` | `csp_lib.manager.schedule.repository` | [[ScheduleService]] |

所有 Protocol 均標記 `@runtime_checkable`，可用 `isinstance()` 驗證合規性。

---

## AlarmRepository Protocol

### 介面定義

```python
from typing import Protocol, runtime_checkable
from datetime import datetime
from csp_lib.manager.alarm.schema import AlarmRecord

@runtime_checkable
class AlarmRepository(Protocol):
    async def health_check(self) -> bool: ...

    async def upsert(self, record: AlarmRecord) -> tuple[str, bool]:
        """新增或更新告警記錄。若 alarm_key 已有 ACTIVE 告警則跳過，回傳 (id, is_new)"""
        ...

    async def resolve(self, alarm_key: str, resolved_at: datetime) -> bool:
        """將 ACTIVE 告警標記為 RESOLVED，回傳是否成功"""
        ...

    async def get_active_alarms(self) -> list[AlarmRecord]:
        """回傳所有 ACTIVE 告警"""
        ...

    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]:
        """回傳指定設備的所有 ACTIVE 告警"""
        ...
```

### 資料結構：AlarmRecord

`AlarmRecord` 是一般的 `@dataclass`（非 frozen），各欄位如下：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `alarm_key` | `str` | 業務唯一鍵，格式 `"<device_id>:<alarm_type>:<alarm_code>"` |
| `device_id` | `str` | 設備識別碼 |
| `alarm_type` | `AlarmType` | `"disconnect"` 或 `"device_alarm"` |
| `alarm_code` | `str` | 告警代碼（如 `"SOC_HIGH"`） |
| `name` | `str` | 顯示名稱 |
| `level` | `AlarmLevel` | `INFO / WARNING / ERROR / CRITICAL` |
| `description` | `str` | 詳細說明 |
| `timestamp` | `datetime \| None` | 發生時間 |
| `resolved_timestamp` | `datetime \| None` | 解除時間（`None` = 進行中） |
| `status` | `AlarmStatus` | `"active"` 或 `"resolved"` |

> [!tip] `upsert` 語意
> - 若 `alarm_key` 已存在且 `status == ACTIVE` → **跳過**，回傳 `(existing_id, False)`
> - 若不存在或已 RESOLVED → **新增**，回傳 `(new_id, True)`
>
> 這確保同一告警不會被重複寫入（每個輪詢週期都可能觸發同一告警）。

### SQLite 實作範例

```python
import threading
from datetime import datetime
from typing import Any
import aiosqlite

from csp_lib.manager.alarm.schema import AlarmRecord, AlarmStatus, AlarmType
from csp_lib.equipment.alarm import AlarmLevel


class SQLiteAlarmRepository:
    """SQLite 告警 Repository 實作，示範如何實作 AlarmRepository Protocol"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        """建立資料表（應用程式啟動時呼叫一次）"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS alarms (
                    alarm_key        TEXT PRIMARY KEY,
                    device_id        TEXT NOT NULL,
                    alarm_type       TEXT NOT NULL,
                    alarm_code       TEXT NOT NULL DEFAULT '',
                    name             TEXT NOT NULL DEFAULT '',
                    level            TEXT NOT NULL DEFAULT 'info',
                    description      TEXT NOT NULL DEFAULT '',
                    timestamp        TEXT,
                    resolved_timestamp TEXT,
                    status           TEXT NOT NULL DEFAULT 'active'
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_device ON alarms(device_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_status ON alarms(status)")
            await db.commit()

    async def health_check(self) -> bool:
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def upsert(self, record: AlarmRecord) -> tuple[str, bool]:
        async with aiosqlite.connect(self._db_path) as db:
            # 檢查是否已有 ACTIVE 告警
            cursor = await db.execute(
                "SELECT alarm_key FROM alarms WHERE alarm_key = ? AND status = 'active'",
                (record.alarm_key,),
            )
            existing = await cursor.fetchone()
            if existing:
                return record.alarm_key, False

            # 插入新記錄
            ts = record.timestamp.isoformat() if record.timestamp else None
            await db.execute(
                """
                INSERT OR REPLACE INTO alarms
                    (alarm_key, device_id, alarm_type, alarm_code, name, level,
                     description, timestamp, resolved_timestamp, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'active')
                """,
                (
                    record.alarm_key, record.device_id, record.alarm_type.value,
                    record.alarm_code, record.name, record.level.value,
                    record.description, ts,
                ),
            )
            await db.commit()
        return record.alarm_key, True

    async def resolve(self, alarm_key: str, resolved_at: datetime) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            result = await db.execute(
                """
                UPDATE alarms
                SET status = 'resolved', resolved_timestamp = ?
                WHERE alarm_key = ? AND status = 'active'
                """,
                (resolved_at.isoformat(), alarm_key),
            )
            await db.commit()
            return result.rowcount == 1

    async def get_active_alarms(self) -> list[AlarmRecord]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM alarms WHERE status = 'active'"
            )
            rows = await cursor.fetchall()
        return [self._row_to_record(dict(r)) for r in rows]

    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM alarms WHERE device_id = ? AND status = 'active'",
                (device_id,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_record(dict(r)) for r in rows]

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> AlarmRecord:
        def parse_dt(val: str | None) -> datetime | None:
            return datetime.fromisoformat(val) if val else None

        return AlarmRecord(
            alarm_key=row["alarm_key"],
            device_id=row["device_id"],
            alarm_type=AlarmType(row["alarm_type"]),
            alarm_code=row["alarm_code"],
            name=row["name"],
            level=AlarmLevel(row["level"]),
            description=row["description"],
            timestamp=parse_dt(row["timestamp"]),
            resolved_timestamp=parse_dt(row["resolved_timestamp"]),
            status=AlarmStatus(row["status"]),
        )
```

---

## CommandRepository Protocol

### 介面定義

```python
from typing import Protocol, runtime_checkable, Any
from csp_lib.manager.command.schema import CommandRecord, CommandStatus

@runtime_checkable
class CommandRepository(Protocol):
    async def health_check(self) -> bool: ...

    async def create(self, record: CommandRecord) -> str:
        """建立指令記錄，回傳記錄 ID"""
        ...

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """更新指令狀態，回傳是否成功"""
        ...

    async def get(self, command_id: str) -> CommandRecord | None:
        """依 command_id 取得記錄"""
        ...

    async def list_by_device(self, device_id: str, limit: int = 100) -> list[CommandRecord]:
        """取得指定設備的指令記錄（timestamp DESC）"""
        ...
```

### 資料結構：CommandRecord

| 欄位 | 型別 | 說明 |
|------|------|------|
| `command_id` | `str` | 業務唯一識別碼（UUID） |
| `device_id` | `str` | 目標設備 ID |
| `point_name` | `str` | 點位名稱 |
| `value` | `Any` | 寫入值 |
| `source` | `str` | 來源（`"internal"`, `"redis_pubsub"` 等） |
| `source_info` | `dict` | 來源詳細資訊 |
| `status` | `CommandStatus` | `PENDING / EXECUTING / SUCCESS / FAILED / DEVICE_NOT_FOUND` |
| `result` | `dict \| None` | 執行結果 |
| `timestamp` | `datetime` | 建立時間 |
| `executed_at` | `datetime \| None` | 開始執行時間 |
| `completed_at` | `datetime \| None` | 完成時間 |
| `error_message` | `str \| None` | 錯誤訊息 |

> [!warning] `command_id` vs 記錄 ID
> `CommandRepository.create()` 接收一個 `CommandRecord`，其中已含 `command_id`（UUID）。
> `create()` 應回傳一個**內部記錄 ID**（如 MongoDB 的 `_id` 或 SQLite 的 `rowid`），
> 而非 `command_id` 本身。`update_status()` 和 `get()` 則使用 `command_id`（業務 ID）查詢。

### SQLite 實作範例

```python
import json
from datetime import datetime, timezone
from typing import Any
import aiosqlite

from csp_lib.manager.command.schema import CommandRecord, CommandStatus


class SQLiteCommandRepository:
    """SQLite 指令記錄 Repository 實作"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS commands (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_id   TEXT UNIQUE NOT NULL,
                    device_id    TEXT NOT NULL,
                    point_name   TEXT NOT NULL,
                    value        TEXT,
                    source       TEXT NOT NULL DEFAULT 'internal',
                    source_info  TEXT NOT NULL DEFAULT '{}',
                    status       TEXT NOT NULL DEFAULT 'pending',
                    result       TEXT,
                    timestamp    TEXT NOT NULL,
                    executed_at  TEXT,
                    completed_at TEXT,
                    error_message TEXT
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_cmd_device ON commands(device_id)")
            await db.commit()

    async def health_check(self) -> bool:
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def create(self, record: CommandRecord) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO commands
                    (command_id, device_id, point_name, value, source, source_info,
                     status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.command_id, record.device_id, record.point_name,
                    json.dumps(record.value), record.source,
                    json.dumps(record.source_info), record.status.value,
                    record.timestamp.isoformat(),
                ),
            )
            await db.commit()
            return str(cursor.lastrowid)

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        fields: list[str] = ["status = ?"]
        values: list[Any] = [status.value]

        if status == CommandStatus.EXECUTING:
            fields.append("executed_at = ?")
            values.append(now)
        elif status in (CommandStatus.SUCCESS, CommandStatus.FAILED, CommandStatus.DEVICE_NOT_FOUND):
            fields.append("completed_at = ?")
            values.append(now)

        if result is not None:
            fields.append("result = ?")
            values.append(json.dumps(result))

        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)

        values.append(command_id)
        sql = f"UPDATE commands SET {', '.join(fields)} WHERE command_id = ?"

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(sql, values)
            await db.commit()
            return cursor.rowcount == 1

    async def get(self, command_id: str) -> CommandRecord | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM commands WHERE command_id = ?", (command_id,)
            )
            row = await cursor.fetchone()
        return self._row_to_record(dict(row)) if row else None

    async def list_by_device(self, device_id: str, limit: int = 100) -> list[CommandRecord]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM commands WHERE device_id = ? ORDER BY timestamp DESC LIMIT ?",
                (device_id, limit),
            )
            rows = await cursor.fetchall()
        return [self._row_to_record(dict(r)) for r in rows]

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> CommandRecord:
        def parse_dt(val: str | None) -> datetime | None:
            return datetime.fromisoformat(val) if val else None

        return CommandRecord(
            command_id=row["command_id"],
            device_id=row["device_id"],
            point_name=row["point_name"],
            value=json.loads(row["value"]) if row["value"] else None,
            source=row["source"],
            source_info=json.loads(row["source_info"]),
            status=CommandStatus(row["status"]),
            result=json.loads(row["result"]) if row["result"] else None,
            timestamp=datetime.fromisoformat(row["timestamp"]),
            executed_at=parse_dt(row["executed_at"]),
            completed_at=parse_dt(row["completed_at"]),
            error_message=row["error_message"],
        )
```

---

## ScheduleRepository Protocol

### 介面定義

```python
from typing import Protocol, runtime_checkable
from datetime import datetime
from csp_lib.manager.schedule.schema import ScheduleRule

@runtime_checkable
class ScheduleRepository(Protocol):
    async def health_check(self) -> bool: ...

    async def find_active_rules(self, site_id: str, now: datetime) -> list[ScheduleRule]:
        """查詢當前時間匹配的啟用規則（依 priority DESC）"""
        ...

    async def get_all_enabled(self, site_id: str) -> list[ScheduleRule]:
        """取得指定站點所有啟用的規則"""
        ...

    async def upsert(self, rule: ScheduleRule) -> str:
        """新增或更新規則（以 site_id + name 作為唯一鍵）"""
        ...
```

> [!note] 時間匹配邏輯
> `find_active_rules()` 需要過濾「當前時間匹配」的規則。
> 若你對接的後端不支援複雜時間查詢，可參考 `MongoScheduleRepository` 的做法：
> 先用 `get_all_enabled()` 拉回所有啟用規則，再在 Python 端用
> `csp_lib.manager.schedule.matcher` 模組做過濾。

### 使用 matcher 模組簡化實作

```python
from datetime import datetime
from csp_lib.manager.schedule import matcher
from csp_lib.manager.schedule.schema import ScheduleRule


class MyScheduleRepository:
    # ... 省略 initialize / health_check / get_all_enabled / upsert ...

    async def find_active_rules(self, site_id: str, now: datetime) -> list[ScheduleRule]:
        all_enabled = await self.get_all_enabled(site_id)

        now_time = now.strftime("%H:%M")
        now_weekday = now.weekday()       # 0=Mon..6=Sun
        now_date = now.date()

        matched = [
            rule for rule in all_enabled
            if matcher.matches_time(rule, now_time)
            and matcher.matches_schedule(rule, now_weekday, now_date)
        ]

        matched.sort(key=lambda r: r.priority, reverse=True)
        return matched
```

---

## 注入至 Manager

### AlarmPersistenceManager

```python
from csp_lib.manager import AlarmPersistenceManager

# 注入自訂 Repository
alarm_manager = AlarmPersistenceManager(repository=my_sqlite_alarm_repo)
```

### WriteCommandManager

```python
from csp_lib.manager import WriteCommandManager

command_manager = WriteCommandManager(repository=my_sqlite_command_repo)
# 設備透過 register_device() 加入
command_manager.register_device(pcs_device)
```

### ScheduleService

```python
from csp_lib.manager import ScheduleService

schedule_service = ScheduleService(
    repository=my_sqlite_schedule_repo,
    mode_controller=system_controller,
    site_id="site_001",
    check_interval=60.0,
)
```

### UnifiedDeviceManager（整合注入）

```python
from csp_lib.manager import UnifiedConfig, UnifiedDeviceManager

config = UnifiedConfig(
    alarm_repository=my_sqlite_alarm_repo,
    command_repository=my_sqlite_command_repo,
    mongo_uploader=my_postgres_uploader,  # 實作 BatchUploader Protocol 即可
    redis_client=None,
    notification_dispatcher=None,
)

manager = UnifiedDeviceManager(config)
```

---

## Protocol Conformance 測試指引

實作完成後，建議撰寫 Protocol 合規性測試，確保你的實作行為與 Protocol 語意一致：

```python
import pytest
from csp_lib.manager.alarm.repository import AlarmRepository
from csp_lib.manager.command.repository import CommandRepository
from csp_lib.manager.schedule.repository import ScheduleRepository

# ── Protocol isinstance 測試 ──

def test_alarm_repo_isinstance():
    repo = SQLiteAlarmRepository(":memory:")
    assert isinstance(repo, AlarmRepository)

def test_command_repo_isinstance():
    repo = SQLiteCommandRepository(":memory:")
    assert isinstance(repo, CommandRepository)


# ── 行為語意測試：AlarmRepository ──

async def test_upsert_dedup():
    """同一 alarm_key 的第二次 upsert 應被跳過"""
    from datetime import datetime, timezone
    from csp_lib.manager.alarm.schema import AlarmRecord, AlarmStatus, AlarmType

    repo = SQLiteAlarmRepository(":memory:")
    await repo.initialize()

    record = AlarmRecord(
        alarm_key="dev01:device_alarm:SOC_HIGH",
        device_id="dev01",
        alarm_type=AlarmType.DEVICE_ALARM,
        alarm_code="SOC_HIGH",
        name="SOC 過高",
        timestamp=datetime.now(timezone.utc),
    )

    _, is_new_1 = await repo.upsert(record)
    _, is_new_2 = await repo.upsert(record)

    assert is_new_1 is True    # 第一次：新增
    assert is_new_2 is False   # 第二次：跳過


async def test_resolve():
    """resolve 後 get_active_alarms 不應再包含該告警"""
    from datetime import datetime, timezone
    from csp_lib.manager.alarm.schema import AlarmRecord, AlarmType

    repo = SQLiteAlarmRepository(":memory:")
    await repo.initialize()

    record = AlarmRecord(
        alarm_key="dev01:device_alarm:OT",
        device_id="dev01",
        alarm_type=AlarmType.DEVICE_ALARM,
        alarm_code="OT",
        name="過溫",
        timestamp=datetime.now(timezone.utc),
    )
    await repo.upsert(record)

    resolved = await repo.resolve(record.alarm_key, datetime.now(timezone.utc))
    assert resolved is True

    active = await repo.get_active_alarms()
    assert all(r.alarm_key != record.alarm_key for r in active)


# ── 行為語意測試：CommandRepository ──

async def test_command_lifecycle():
    """指令從 PENDING → EXECUTING → SUCCESS 的完整流程"""
    from csp_lib.manager.command.schema import CommandRecord, CommandStatus, WriteCommand

    repo = SQLiteCommandRepository(":memory:")
    await repo.initialize()

    cmd = WriteCommand(device_id="pcs_01", point_name="p_set", value=-50.0)
    record = CommandRecord.from_command(cmd)

    rid = await repo.create(record)
    assert rid is not None

    ok = await repo.update_status(cmd.command_id, CommandStatus.EXECUTING)
    assert ok is True

    ok = await repo.update_status(
        cmd.command_id, CommandStatus.SUCCESS, result={"written": -50.0}
    )
    assert ok is True

    fetched = await repo.get(cmd.command_id)
    assert fetched is not None
    assert fetched.status == CommandStatus.SUCCESS
```

> [!tip]
> 使用 `":memory:"` 作為 SQLite 路徑可讓測試在完全隔離的 DB 中執行，
> 不需要 cleanup fixture。

---

## 相關資源

- [[AlarmPersistenceManager]] — 告警持久化管理器 API
- [[WriteCommandManager]] — 指令管理器 API
- [[ScheduleService]] — 排程服務 API
- [[No MongoDB Setup]] — 使用 InMemory 實作（無外部 DB）
- [[BatchUploader]] — 資料上傳 Protocol
