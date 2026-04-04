---
tags:
  - type/class
  - layer/notification
  - status/complete
source: csp_lib/notification/dispatcher.py
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# NotificationDispatcher

> 多通道通知分發器

`NotificationDispatcher` 將通知扇出到多個 [[NotificationChannel]]，個別通道發送失敗不影響其他通道，僅記錄警告日誌。

---

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `channels` | `Sequence[NotificationChannel]` | 通知通道列表 |

---

## 方法

| 方法 | 說明 |
|------|------|
| `dispatch(notification)` | 將通知分發到所有通道（個別失敗不中斷） |
| `dispatch_batch(notifications)` | 批次分發 `NotificationItem` 列表到所有通道（透過 `send_batch`） |
| `from_alarm_record(record, event, config=None)` | 靜態工廠方法：從 `AlarmRecord` 建構 `Notification`（可傳入 `NotificationConfig` 自訂標籤模板） |

---

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `channels` | `list[NotificationChannel]` | 已註冊的通知通道列表（複製） |

---

## Notification

通知資料類別（frozen dataclass）：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `title` | `str` | 通知標題（如 `"[ALARM] inverter_001 溫度過高"`） |
| `body` | `str` | 詳細描述 |
| `level` | `AlarmLevel` | 告警等級 |
| `device_id` | `str` | 設備識別碼 |
| `alarm_key` | `str` | 告警唯一鍵 |
| `event` | `NotificationEvent` | 通知事件類型 |
| `occurred_at` | `datetime` | 發生時間 |

---

## NotificationEvent

通知事件類型列舉：

| 值 | 說明 |
|----|------|
| `TRIGGERED` | 告警觸發 |
| `RESOLVED` | 告警解除 |

---

## 程式碼範例

```python
from csp_lib.notification import NotificationDispatcher

dispatcher = NotificationDispatcher(channels=[line_channel, email_channel])
await dispatcher.dispatch(notification)

# 批次分發
await dispatcher.dispatch_batch([notification_1, event_notification])
```

---

## NotificationBatcher

> 批次通知管理器（`AsyncLifecycleMixin`，滿足 `NotificationSender`）

收集通知到內部佇列，以防抖時間窗批次發送。支援去重、分組、立即發送、以及停止時含重試的 final flush。

### 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `channels` | `Sequence[NotificationChannel]` | (必填) | 通知通道列表 |
| `config` | `BatchNotificationConfig \| None` | `None` | 批次配置 |
| `group_key_fn` | `Callable[[NotificationItem], str] \| None` | `None` | 自訂分組函式 |

### BatchNotificationConfig

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `flush_interval` | `float` | `5.0` | 防抖時間窗（秒） |
| `batch_size_threshold` | `int` | `50` | 累積達此數量時立即 flush |
| `max_queue_size` | `int` | `5000` | 佇列最大容量 |
| `deduplicate_by_key` | `bool` | `True` | 同一時間窗內相同 `alarm_key` 僅保留最新一則 |

### 方法

| 方法 | 說明 |
|------|------|
| `dispatch(notification)` | 加入批次佇列（滿足 `NotificationSender`） |
| `dispatch_event(event)` | 發送事件通知（`immediate=True` 則立即發送） |
| `dispatch_immediate(notification)` | 立即發送（繞過佇列） |
| `flush()` | 強制 flush 佇列中所有通知 |

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `pending_count` | `int` | 佇列中待發送的通知數量 |
| `channels` | `list[NotificationChannel]` | 已註冊的通知通道列表 |

### Final Flush 重試

停止時 (`_on_stop`)，`NotificationBatcher` 會嘗試 flush 所有殘留通知。若首次 flush 失敗，等待 1 秒後重試一次；若仍失敗，記錄錯誤並丟棄殘留通知。

### Quick Example

```python
from csp_lib.notification import NotificationBatcher, BatchNotificationConfig

batcher = NotificationBatcher(
    channels=[line_channel, email_channel],
    config=BatchNotificationConfig(flush_interval=5.0, batch_size_threshold=50),
)

async with batcher:
    await batcher.dispatch(notification)  # 進入佇列
    await batcher.dispatch_immediate(urgent)  # 立即發送
    await batcher.dispatch_event(event_notif)  # 事件通知
```

---

## EventNotification 與 EventCategory

非告警事件通知（frozen dataclass）：

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `title` | `str` | (必填) | 通知標題 |
| `body` | `str` | (必填) | 詳細描述 |
| `category` | `EventCategory` | (必填) | 事件分類 |
| `source` | `str` | `""` | 事件來源（如模組名稱） |
| `immediate` | `bool` | `False` | 是否立即發送（繞過批次佇列） |
| `metadata` | `dict[str, Any]` | `{}` | 額外資訊 |
| `occurred_at` | `datetime` | `datetime.now()` | 發生時間 |

### EventCategory

| 值 | 說明 |
|----|------|
| `SYSTEM` | 系統事件（啟動/停止/重啟） |
| `REPORT` | 報告事件（日報/週報產出） |
| `MAINTENANCE` | 維護事件（排程維護/韌體更新） |
| `CUSTOM` | 自訂事件 |

### NotificationItem

`NotificationItem = Union[Notification, EventNotification]` -- 通知聯合型別。

---

## NotificationConfig

通知配置（frozen dataclass），用於 `from_alarm_record` 工廠方法：

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `triggered_label` | `str` | `"觸發"` | 告警觸發時的事件標籤 |
| `resolved_label` | `str` | `"解除"` | 告警解除時的事件標籤 |
| `title_template` | `str` | `"[{level}] {device_id} {name} - {event_label}"` | 標題模板 |

---

## 相關頁面

- [[NotificationChannel]] -- 通知通道抽象
- [[Custom Channel Guide]] -- 自訂通道實作指南
- [[_MOC Notification]] -- 模組總覽
