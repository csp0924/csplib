---
tags:
  - type/moc
  - layer/notification
  - status/complete
created: 2026-02-17
---

# Notification 模組總覽

> **通知分發系統 (`csp_lib.notification`)**

Notification 模組提供多通道告警通知分發機制。透過 `NotificationDispatcher` 將告警通知扇出到多個 `NotificationChannel` 實作（如 LINE、Telegram、Email 等），個別通道失敗不影響其他通道。

---

## 架構概覽

```
AlarmPersistenceManager / SystemMonitor
  └── NotificationDispatcher
        ├── LineChannel.send()
        ├── TelegramChannel.send()
        └── ...其他自訂通道
```

---

## 索引

| 頁面 | 說明 |
|------|------|
| [[NotificationDispatcher]] | 多通道通知分發器 |
| [[NotificationChannel]] | 通知通道抽象（ABC） |
| [[Custom Channel Guide]] | 自訂通道實作指南 |

---

## Dataview 查詢

```dataview
TABLE source AS "原始碼", tags AS "標籤"
FROM "11-Notification"
WHERE file.name != "_MOC Notification"
SORT file.name ASC
```

---

## 相關 MOC

- 上游：[[_MOC Manager]] -- AlarmPersistenceManager 使用 dispatcher 發送通知
- 上游：[[_MOC Monitor]] -- SystemMonitor 使用 dispatcher 發送系統告警通知
- 使用：[[_MOC Equipment]] -- 複用 AlarmLevel 定義
