---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/alarm/persistence.py
updated: 2026-04-04
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

### AlarmPersistenceConfig

`@dataclass(frozen=True)` 配置。

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `disconnect_code` | `str` | `"DISCONNECT"` | 斷線告警的固定代碼 |
| `disconnect_name` | `str` | `"設備斷線"` | 斷線告警的顯示名稱 |

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

## 相關頁面

- [[DeviceEventSubscriber]] — 基底類別
- [[UnifiedDeviceManager]] — 自動串接告警管理器
- [[_MOC Storage]] — 告警資料最終儲存至 MongoDB
