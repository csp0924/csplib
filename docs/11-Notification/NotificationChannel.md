---
tags:
  - type/protocol
  - layer/notification
  - status/complete
source: csp_lib/notification/base.py
created: 2026-02-17
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
| `send(notification)` | 發送通知（`@abstractmethod`，非同步方法） |

---

## 介面簽名

```python
from abc import ABC, abstractmethod

class NotificationChannel(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """通道名稱"""
        ...

    @abstractmethod
    async def send(self, notification: Notification) -> None:
        """發送通知"""
        ...
```

---

## 實作要點

1. **`name` 屬性**：回傳唯一的通道名稱字串（如 `"line"`、`"telegram"`），用於日誌與錯誤識別
2. **`send` 方法**：接收 `Notification` 物件，執行實際的發送邏輯
3. **例外處理**：`send` 拋出的例外會被 [[NotificationDispatcher]] 捕獲並記錄，不會中斷其他通道的發送

---

## 相關頁面

- [[NotificationDispatcher]] -- 使用 channel 分發通知
- [[Custom Channel Guide]] -- 完整的自訂通道實作範例
- [[_MOC Notification]] -- 模組總覽
