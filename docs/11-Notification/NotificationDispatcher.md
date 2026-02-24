---
tags:
  - type/class
  - layer/notification
  - status/complete
source: csp_lib/notification/dispatcher.py
created: 2026-02-17
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
| `from_alarm_record(record, event)` | 靜態工廠方法：從 `AlarmRecord` 建構 `Notification` |

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
```

---

## 相關頁面

- [[NotificationChannel]] -- 通知通道抽象
- [[Custom Channel Guide]] -- 自訂通道實作指南
- [[_MOC Notification]] -- 模組總覽
