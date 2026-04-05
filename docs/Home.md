---
tags: [type/reference, status/complete]
updated: 2026-04-04
version: 0.6.1
---
# CSP Library 知識庫

> **csp_lib** — 模組化 Python 工具集，專為能源管理系統與工業設備通訊設計。

## 架構總覽

```
┌─────────────────────────────────────────────────────────┐
│                    Integration Layer                     │
│  DeviceRegistry · ContextBuilder · CommandRouter         │
│  GridControlLoop · SystemController · GroupController     │
│  PowerDistributor · HeartbeatService                     │
├─────────────────────────────────────────────────────────┤
│              Manager Layer              │   Controller   │
│  DeviceManager · AlarmPersistence       │   Strategy     │
│  DataUpload · StateSync · Unified       │   Executor     │
│  WriteCommand · ScheduleService         │   Protection   │
├─────────────────────────────────────────┤   ModeManager  │
│              Equipment Layer            │   Cascading    │
│  AsyncModbusDevice · AsyncCANDevice     │   CommandProc  │
│  Points · Alarms · DeviceProtocol       │   EventOverride│
│  Transport · Transforms · Pipeline      │   Compensator  │
├─────────────────────────────────────────┴────────────────┤
│             Modbus Layer     │        CAN Layer           │
│  DataTypes · Codec           │  CANBusConfig · CANFrame   │
│  Clients (TCP/RTU/Shared)    │  PythonCANClient           │
├──────────────────────────────┴──────────────────────────┤
│                       Core Layer                         │
│  Logging · Lifecycle · Errors · Health · CircuitBreaker   │
│  RuntimeParameters                                       │
└─────────────────────────────────────────────────────────┘

附加模組: Mongo · Redis · Cluster · Monitor · Notification
         Modbus Server · Modbus Gateway · GUI · Statistics · gRPC
```

## 模組導覽

### 核心層級

| 圖示 | 模組 | 說明 |
|------|------|------|
| 🔧 | [[_MOC Core]] | 日誌、生命週期、錯誤、健康檢查、斷路器 |
| 📡 | [[_MOC Modbus]] | Modbus 通訊協定、資料型別、客戶端 |
| 🚌 | [[_MOC CAN]] | CAN Bus 通訊協定、設定、客戶端 |
| ⚙️ | [[_MOC Equipment]] | 設備抽象、點位、告警、傳輸 |
| 🧠 | [[_MOC Controller]] | 控制策略、保護規則、模式管理 |
| 🔗 | [[_MOC Integration]] | 設備-控制器整合、控制迴圈 |
| 📦 | [[_MOC Manager]] | 設備管理、持久化、狀態同步 |

### 儲存與基礎設施

| 圖示 | 模組 | 說明 |
|------|------|------|
| 🗄️ | [[_MOC Storage]] | MongoDB + Redis 客戶端 |
| 🌐 | [[_MOC Cluster]] | 分散式高可用控制 (etcd) |
| 📊 | [[_MOC Monitor]] | 系統監控 (CPU/RAM/Disk) |
| 🔔 | [[_MOC Notification]] | 通知分發系統 |
| 🧪 | [[_MOC Modbus Server]] | 模擬測試伺服器 |
| 🔌 | [[_MOC Modbus Gateway]] | Modbus TCP Gateway（EMS/SCADA 整合） |
| 📈 | [[_MOC Statistics]] | 統計引擎與追蹤器 |

### 使用資源

| 圖示 | 區塊 | 說明 |
|------|------|------|
| 🏁 | [[_MOC Guides]] | 快速入門與使用教學 |
| 📖 | [[_MOC Reference]] | 類別索引、列舉、事件 |
| 🛠️ | [[_MOC Development]] | 開發環境、測試、CI/CD |
| 📐 | [[_MOC Architecture]] | 系統架構與設計模式 |
| 📘 | [[_MOC Guide]] | Vault 使用指南 |

## 快速連結

- [[Quick Start]] — 5 分鐘快速入門
- [[Layered Architecture]] — 分層架構詳解
- [[Design Patterns]] — 設計模式總覽
- [[All Classes]] — 所有類別索引
- [[Version History]] — 版本歷程

## 專案資訊

- **套件名稱**: `csp0924_lib`
- **作者**: Cheng Sin Pang (鄭善淜)
- **聯絡**: donaldpang123@gmail.com
- **Python**: 3.13+
- **目前版本**: 0.6.2
- **授權**: Apache-2.0
