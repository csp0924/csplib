---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/alarm/persistence.py
---

# AlarmPersistenceManager

告警持久化管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`AlarmPersistenceManager` 繼承自 [[DeviceEventSubscriber]]，自動將設備事件持久化至資料庫。採用觀察者模式訂閱 `AsyncModbusDevice` 的連線與告警事件，實現事件驅動的告警管理。

### 職責

1. 訂閱多個 `AsyncModbusDevice` 的事件
2. 斷線/告警觸發 → 寫入 DB（新增告警記錄）
3. 恢復/告警解除 → 更新 `resolved_at`（解除告警）
4. 可選的通知分發（透過 `NotificationDispatcher`）

## AlarmStatus 列舉

| 狀態 | 說明 |
|------|------|
| `ACTIVE` | 告警啟用中 |
| `RESOLVED` | 告警已解除 |

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `repository` | `AlarmRepository` | 告警資料存取層（遵循 AlarmRepository Protocol） |
| `dispatcher` | `NotificationDispatcher \| None` | 通知分發器（可選） |

## 訂閱的事件

| 事件 | 處理 |
|------|------|
| `disconnected` | 建立斷線類型告警記錄 |
| `connected` | 解除對應的斷線告警 |
| `alarm_triggered` | 建立設備內部告警記錄 |
| `alarm_cleared` | 解除對應的設備告警 |

## 常數

| 常數 | 值 | 說明 |
|------|------|------|
| `DISCONNECT_CODE` | `"DISCONNECT"` | 斷線告警的固定代碼 |
| `DISCONNECT_NAME` | `"設備斷線"` | 斷線告警的顯示名稱 |

## 使用範例

```python
from csp_lib.manager import AlarmPersistenceManager, MongoAlarmRepository

repo = MongoAlarmRepository(db)
manager = AlarmPersistenceManager(
    device=device,
    repository=repo,
    redis_client=redis,
    dispatcher=notification_dispatcher,  # Optional
)
```

## 相關頁面

- [[DeviceEventSubscriber]] — 基底類別
- [[UnifiedDeviceManager]] — 自動串接告警管理器
- [[_MOC Storage]] — 告警資料最終儲存至 MongoDB
