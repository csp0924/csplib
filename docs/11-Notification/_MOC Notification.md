---
tags:
  - type/moc
  - layer/notification
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# Notification 模組總覽

> **通知分發系統 (`csp_lib.notification`)**

Notification 模組提供多通道告警通知分發機制。透過 `NotificationDispatcher`（即時）或 `NotificationBatcher`（批次）將告警通知扇出到多個 `NotificationChannel` 實作（如 LINE、Telegram、Email 等），個別通道失敗不影響其他通道。兩者均滿足 `NotificationSender` Protocol，可互換使用。

---

## 架構概覽

```
AlarmPersistenceManager / SystemMonitor
  ├── NotificationDispatcher（即時發送，滿足 NotificationSender）
  │     ├── LineChannel.send()
  │     ├── TelegramChannel.send()
  │     └── ...其他自訂通道
  └── NotificationBatcher（批次發送，AsyncLifecycleMixin，滿足 NotificationSender）
        ├── 防抖時間窗 + 閾值 flush
        ├── alarm_key 去重
        ├── 分組發送（level:event / category）
        └── 停止時含重試的 final flush
```

---

## 索引

| 頁面 | 說明 |
|------|------|
| [[NotificationDispatcher]] | 多通道通知分發器（即時 + 批次） |
| [[NotificationChannel]] | 通知通道抽象（ABC，含 `send_batch` / `send_event`） |
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
