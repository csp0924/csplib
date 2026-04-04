---
tags:
  - type/protocol
  - layer/notification
  - status/complete
source: csp_lib/notification/base.py
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# NotificationChannel

> 通知通道抽象（ABC）

`NotificationChannel` 是通知通道的抽象基礎類別，定義了所有通知通道必須實作的介面。未來可實作 LINE、Telegram、Email、Webhook 等通道。

---

## 介面定義

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `name` | `str` | 通道名稱（`@property @abstractmethod`） |

### 方法

| 方法 | 說明 |
|------|------|
| `send(notification)` | 發送單則通知（`@abstractmethod`，非同步方法） |
| `send_batch(items)` | 批次發送通知（預設逐一呼叫 `send` / `send_event`，子類可覆寫） |
| `send_event(event)` | 發送事件通知（預設 no-op，子類可覆寫） |

---

## 介面簽名

```python
from abc import ABC, abstractmethod
from typing import Sequence

class NotificationChannel(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """通道名稱"""
        ...

    @abstractmethod
    async def send(self, notification: Notification) -> None:
        """發送單則通知"""
        ...

    async def send_batch(self, items: Sequence[NotificationItem]) -> None:
        """批次發送通知（預設逐一 send / send_event）"""
        ...

    async def send_event(self, event: EventNotification) -> None:
        """發送事件通知（預設 no-op）"""
        ...
```

---

## NotificationSender Protocol

最小的通知發送介面，讓 [[NotificationDispatcher]] 與 `NotificationBatcher` 都能作為通知來源使用：

```python
@runtime_checkable
class NotificationSender(Protocol):
    async def dispatch(self, notification: Notification) -> None: ...
```

---

## 實作要點

1. **`name` 屬性**：回傳唯一的通道名稱字串（如 `"line"`、`"telegram"`），用於日誌與錯誤識別
2. **`send` 方法**：接收 `Notification` 物件，執行實際的發送邏輯
3. **`send_batch` 方法**：可覆寫以實現自訂的批次格式（如摘要訊息），預設逐一呼叫 `send` / `send_event`
4. **`send_event` 方法**：可覆寫以支援非告警事件通知（如系統事件、報告）
5. **例外處理**：`send` 拋出的例外會被 [[NotificationDispatcher]] 捕獲並記錄，不會中斷其他通道的發送

---

## 相關頁面

- [[NotificationDispatcher]] -- 使用 channel 分發通知
- [[Custom Channel Guide]] -- 完整的自訂通道實作範例
- [[_MOC Notification]] -- 模組總覽
