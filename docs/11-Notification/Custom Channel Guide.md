---
tags:
  - type/guide
  - layer/notification
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
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

### 3. 覆寫 `send_batch()` / `send_event()`（可選）

若需要自訂批次格式或支援事件通知：

```python
from typing import Sequence
from csp_lib.notification import EventNotification, NotificationItem, NotificationChannel, Notification

class LineChannel(NotificationChannel):
    @property
    def name(self) -> str:
        return "line"

    async def send(self, notification: Notification) -> None:
        # 發送單則告警
        ...

    async def send_batch(self, items: Sequence[NotificationItem]) -> None:
        # 自訂批次格式（如摘要訊息）
        summary = f"共 {len(items)} 則通知\n"
        for item in items:
            summary += f"- {item.title}\n"
        await self._send_line_message(summary)

    async def send_event(self, event: EventNotification) -> None:
        # 發送非告警事件
        await self._send_line_message(f"[{event.category.value}] {event.title}")
```

### 4. 整合 AlarmPersistenceManager

將 dispatcher 或 batcher 注入 `AlarmPersistenceManager`（兩者均滿足 `NotificationSender`），告警觸發/解除時自動發送通知：

```python
from csp_lib.manager.alarm import AlarmPersistenceManager

# 即時模式
alarm_manager = AlarmPersistenceManager(
    device=device,
    repository=repo,
    redis_client=redis,
    dispatcher=dispatcher,
)

# 批次模式（防抖 + 去重）
from csp_lib.notification import NotificationBatcher
batcher = NotificationBatcher(channels=[LineChannel(), TelegramChannel()])
alarm_manager = AlarmPersistenceManager(
    device=device,
    repository=repo,
    redis_client=redis,
    dispatcher=batcher,
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

- **錯誤處理**：`send()` 拋出的例外會被 dispatcher/batcher 捕獲，不需在內部做全域 catch
- **逾時控制**：建議在 HTTP 呼叫中設定合理的 timeout（如 10 秒）
- **等級過濾**：可在 `send()` 中根據 `notification.level` 過濾低等級告警
- **批次發送**：使用 `NotificationBatcher` 即可自動防抖 + 去重，或覆寫 `send_batch()` 自訂批次格式
- **事件通知**：覆寫 `send_event()` 以支援 `EventNotification`（系統事件、報告、維護等）

---

## 相關頁面

- [[NotificationChannel]] -- 通知通道 ABC
- [[NotificationDispatcher]] -- 多通道分發器
- [[_MOC Manager]] -- AlarmPersistenceManager
- [[_MOC Notification]] -- 模組總覽
