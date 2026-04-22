---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/alarm/persistence.py
created: 2026-02-17
updated: 2026-04-23
version: ">=0.10.0"
---

# AlarmPersistenceManager

告警持久化管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

> [!warning] v0.6.0 Breaking Change
> `AlarmRecord` 的 timestamp 欄位已更名：
> - `occurred_at` → `timestamp`
> - `resolved_at` → `resolved_timestamp`
>
> 若有直接存取 `AlarmRecord` 欄位的程式碼，需配合更新。MongoDB 中既有文件的欄位名稱也會隨之改變。

## 概述

`AlarmPersistenceManager` 繼承自 [[DeviceEventSubscriber]]，自動將設備事件持久化至資料庫。採用觀察者模式訂閱 `AsyncModbusDevice` 的連線與告警事件，實現事件驅動的告警管理。

### 職責

1. 訂閱多個 `AsyncModbusDevice` 的事件
2. 斷線/告警觸發 → 寫入 DB（新增告警記錄）
3. 恢復/告警解除 → 更新 `resolved_timestamp`（解除告警）
4. 可選的通知分發（透過 `NotificationSender`）

## AlarmRecord

`@dataclass` 資料類別，對應 MongoDB Document。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `alarm_key` | `str` | 業務唯一鍵，格式 `"<device_id>:<alarm_type>:<alarm_code>"` |
| `device_id` | `str` | 設備識別碼 |
| `alarm_type` | `AlarmType` | 告警類型（`DISCONNECT` / `DEVICE_ALARM`） |
| `alarm_code` | `str` | 告警代碼 |
| `name` | `str` | 告警名稱（用於顯示） |
| `level` | `AlarmLevel` | 告警等級（`INFO` / `WARNING` / `ERROR` / `CRITICAL`） |
| `description` | `str` | 告警描述 |
| `timestamp` | `datetime \| None` | 發生時間 |
| `resolved_timestamp` | `datetime \| None` | 解除時間（`None` 表示進行中） |
| `status` | `AlarmStatus` | 告警狀態（`ACTIVE` / `RESOLVED`） |

### AlarmType 列舉

| 值 | 說明 |
|------|------|
| `DISCONNECT` | 設備斷線告警（通訊中斷） |
| `DEVICE_ALARM` | 設備內部告警（如過溫、過載等） |
| `CAPABILITY_DEGRADED` | 設備能力降級（v0.10.0）— 設備啟動時預期具備某能力但未滿足（如 PCS 啟動但功率控制 capability 未就緒） |

> [!note] v0.10.0 新增 `CAPABILITY_DEGRADED`（PR #107）
> 由 `DeviceManager._on_start` 在偵測到設備 capability 不足時觸發。
> 可用於 dashboard 顯示哪些設備能力降級、或觸發通知提醒運維人員。

### AlarmStatus 列舉

| 狀態 | 說明 |
|------|------|
| `ACTIVE` | 告警啟用中 |
| `RESOLVED` | 告警已解除 |

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `repository` | `AlarmRepository` | 告警資料存取層（遵循 AlarmRepository Protocol） |
| `dispatcher` | `NotificationSender \| None` | 通知分發器（可選），用於告警觸發/解除時發送通知 |
| `config` | `AlarmPersistenceConfig \| None` | 告警持久化配置（可選，預設使用 `AlarmPersistenceConfig()`） |
| `buffered_uploader` | `LocalBufferedUploader \| None` | 選擇性 SQLite 緩衝層（keyword-only，v0.8.2 新增）。提供時，告警建立/解除成功後額外以 `write_immediate` 寫一份不可變歷史記錄到 `config.history_collection`；寫入失敗僅 log warning，不影響主流程 |

> [!note] v0.8.2：告警歷史不遺失
> 注入 `buffered_uploader` 後，每次告警建立或解除，都會在 repository 操作成功後，額外呼叫 `buffered_uploader.write_immediate(history_collection, ...)` 寫一份快照。即使 MongoDB 斷線，此紀錄也會先落地 SQLite，背景 replay 後再寫入 MongoDB。

### AlarmPersistenceConfig

`@dataclass(frozen=True, slots=True)` 配置。

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `disconnect_code` | `str` | `"DISCONNECT"` | 斷線告警的固定代碼 |
| `disconnect_name` | `str` | `"設備斷線"` | 斷線告警的顯示名稱 |
| `history_collection` | `str` | `"alarm_history"` | 告警歷史記錄 collection 名稱（v0.8.2 新增）；`__post_init__` 驗證非空字串 |

## 訂閱的事件

| 事件 | 處理 |
|------|------|
| `disconnected` | 建立斷線類型告警記錄 |
| `connected` | 解除對應的斷線告警 |
| `alarm_triggered` | 建立設備內部告警記錄 |
| `alarm_cleared` | 解除對應的設備告警 |

## Quick Example

```python
from csp_lib.manager.alarm import AlarmPersistenceManager, MongoAlarmRepository

repo = MongoAlarmRepository(db)
await repo.ensure_indexes()

manager = AlarmPersistenceManager(
    repository=repo,
    dispatcher=notification_sender,  # 可選：NotificationSender 實例
)

# 訂閱設備事件
manager.subscribe(device)

# 取消訂閱
manager.unsubscribe(device)
```

## Common Patterns

### 啟用告警歷史不遺失（v0.8.2）

WAN/MongoDB 不穩定時，注入 `LocalBufferedUploader` 確保告警歷史記錄不遺失：

```python
from csp_lib.manager.alarm import AlarmPersistenceManager, MongoAlarmRepository, AlarmPersistenceConfig
from csp_lib.mongo import MongoBatchUploader
from csp_lib.mongo.local_buffer import LocalBufferedUploader, LocalBufferConfig

mongo_uploader = MongoBatchUploader(db=mongo_db).start()
buffer_cfg = LocalBufferConfig(db_path="./alarm_buffer.db")
local = LocalBufferedUploader(downstream=mongo_uploader, config=buffer_cfg)

repo = MongoAlarmRepository(db)
await repo.ensure_indexes()

# 啟動 local buffer 後再建立 manager
async with local:
    config = AlarmPersistenceConfig(
        history_collection="alarm_history",  # 預設值，可自訂
    )
    manager = AlarmPersistenceManager(
        repository=repo,
        config=config,
        buffered_uploader=local,  # keyword-only
    )
    manager.subscribe(device)

    # 每次告警建立/解除，history_collection 都會有一份副本
```

## Gotchas / Tips

- `buffered_uploader` 必須在 `AlarmPersistenceManager` 使用期間保持啟動狀態（`async with local`）；停止後寫入會因 SQLite 連線關閉而失敗並 log warning
- `history_collection` 記錄的是**事件快照**（triggered/resolved），不是告警的最新狀態；查最新狀態應用 `repository`
- 告警歷史 collection 建議搭配 `ensure_indexes()` 建立 `_idempotency_key` 唯一稀疏索引，確保 replay 冪等

## 相關頁面

- [[DeviceEventSubscriber]] — 基底類別
- [[LocalBufferedUploader]] — SQLite WAL 本地緩衝層（v0.8.2）
- [[MongoBatchUploader]] — 底層 MongoDB 上傳器
- [[UnifiedDeviceManager]] — 自動串接告警管理器
- [[_MOC Storage]] — 告警資料最終儲存至 MongoDB
