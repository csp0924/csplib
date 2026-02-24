---
tags:
  - type/guide
  - layer/notification
  - status/complete
created: 2026-02-17
---

# Custom Channel Guide

> 自訂通知通道實作指南

本指南說明如何實作自訂的 [[NotificationChannel]]，並整合到 [[NotificationDispatcher]] 與 `AlarmPersistenceManager`。

---

## 實作步驟

### 1. 繼承 NotificationChannel

實作 `name` 屬性與 `send()` 方法：

```python
from csp_lib.notification import NotificationChannel, Notification

class LineChannel(NotificationChannel):
    @property
    def name(self) -> str:
        return "line"

    async def send(self, notification: Notification) -> None:
        # Send via LINE Notify API
        ...
```

```python
class TelegramChannel(NotificationChannel):
    @property
    def name(self) -> str:
        return "telegram"

    async def send(self, notification: Notification) -> None:
        # Send via Telegram Bot API
        ...
```

### 2. 建立 NotificationDispatcher

將自訂通道傳入 `NotificationDispatcher`：

```python
from csp_lib.notification import NotificationDispatcher

dispatcher = NotificationDispatcher(channels=[LineChannel(), TelegramChannel()])
```

### 3. 整合 AlarmPersistenceManager

將 dispatcher 注入 `AlarmPersistenceManager`，告警觸發/解除時自動發送通知：

```python
from csp_lib.manager.alarm import AlarmPersistenceManager

alarm_manager = AlarmPersistenceManager(
    device=device,
    repository=repo,
    redis_client=redis,
    dispatcher=dispatcher,
)
```

---

## Notification 物件結構

`send()` 方法接收的 `Notification` 物件包含以下欄位：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `title` | `str` | 通知標題（含告警等級與設備資訊） |
| `body` | `str` | 詳細描述 |
| `level` | `AlarmLevel` | 告警等級 |
| `device_id` | `str` | 設備識別碼 |
| `alarm_key` | `str` | 告警唯一鍵 |
| `event` | `NotificationEvent` | `TRIGGERED` 或 `RESOLVED` |
| `occurred_at` | `datetime` | 發生時間 |

---

## 實作建議

- **錯誤處理**：`send()` 拋出的例外會被 dispatcher 捕獲，不需在內部做全域 catch
- **逾時控制**：建議在 HTTP 呼叫中設定合理的 timeout（如 10 秒）
- **等級過濾**：可在 `send()` 中根據 `notification.level` 過濾低等級告警
- **批次發送**：對於高頻告警場景，可考慮在 channel 內部實作 debounce 或 batch 機制

---

## 相關頁面

- [[NotificationChannel]] -- 通知通道 ABC
- [[NotificationDispatcher]] -- 多通道分發器
- [[_MOC Manager]] -- AlarmPersistenceManager
- [[_MOC Notification]] -- 模組總覽
