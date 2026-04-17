---
tags:
  - type/moc
  - layer/manager
  - status/complete
updated: 2026-04-18
version: ">=0.8.2"
---

# Manager 模組總覽

系統整合管理層，負責設備生命週期、外部儲存、即時同步。

Manager 模組建構在 [[_MOC Equipment|Equipment]] 與 [[_MOC Integration|Integration]] 之上，提供設備讀取循環管理、告警持久化、資料批次上傳、外部指令路由、Redis 即時狀態同步等功能。所有 Manager 皆採用觀察者模式訂閱設備事件，實現事件驅動的系統整合。

## 頁面索引

### 基底類別與 Protocol

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[DeviceEventSubscriber]] | class | 所有 Manager 的基底類別，事件訂閱框架 |
| [[BatchUploader]] | Protocol | 批次上傳器介面（v0.6.0 新增，解耦 MongoBatchUploader 依賴） |

### 設備管理

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[DeviceManager]] | class | 設備讀取循環管理（standalone / group） |
| [[DeviceGroup]] | dataclass | RTU 共線順序讀取群組 |

### 子管理器

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[AlarmPersistenceManager]] | class | 告警持久化（MongoDB + 可選告警歷史不遺失，v0.8.2 新增 `buffered_uploader`） |
| [[DataUploadManager]] | class | 批次資料上傳至 MongoDB（v0.8.2 新增 `buffered_uploader` opt-in） |
| [[WriteCommandManager]] | class | 外部命令路由（Redis → 設備寫入） |
| [[StateSyncManager]] | class | Redis 即時狀態同步 |

### 統一入口

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[UnifiedDeviceManager]] | class | 整合所有 Manager 的統一入口 |

### 排程服務（v0.4.2 新增）

| 頁面 | 類型 | 說明 |
|------|------|------|
| [[ScheduleService]] | class | 週期輪詢排程規則並透過 [[ScheduleModeController]] 驅動策略切換 |

## 相關模組

- 上游：[[_MOC Equipment]]、[[_MOC Integration]]
- 下游：[[_MOC Storage]]
