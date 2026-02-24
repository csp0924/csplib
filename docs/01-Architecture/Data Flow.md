---
tags: [type/concept, status/complete]
---
# Data Flow

> 核心資料流圖 — 讀取循環、控制循環、模式切換

## 4.1 讀取循環（每 1~60 秒）

設備週期性讀取的完整資料流，從暫存器排程到事件發射：

```
ReadScheduler.get_next_groups()
    │  (固定點位 + 當前輪替點位)
    ▼
PointGrouper 合併相鄰暫存器
    │  (減少 Modbus 請求數)
    ▼
GroupReader.read_many()
    │  (Modbus TCP/RTU 通訊)
    ▼
raw registers [0x1234, 0x5678, ...]
    │
    ▼
ModbusDataType.decode()  →  typed values (float, int, str)
    │
    ▼
ProcessingPipeline.process()  →  transformed values
    │  (Scale × 0.1, BitExtract, EnumMap...)
    ▼
AggregatorPipeline.process()  →  computed values
    │  (CoilToBitmask, ComputedValue...)
    ▼
AsyncModbusDevice._latest_values  (更新快取)
    │
    ├── emit(VALUE_CHANGE)  →  訂閱者
    ├── emit(READ_COMPLETE) →  DataUploadManager → MongoDB
    │                       →  StateSyncManager  → Redis
    │
    └── AlarmEvaluator.evaluate()
            │
            ▼
        AlarmStateManager.update()  (套用遲滯邏輯)
            │
            ├── emit(ALARM_TRIGGERED) → AlarmPersistenceManager → MongoDB
            └── emit(ALARM_CLEARED)   → StateSyncManager → Redis
```

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| [[ReadScheduler]] | 管理固定 + 輪替排程 | [[_MOC Equipment]] |
| [[PointGrouper]] | 合併相鄰暫存器以減少請求 | [[_MOC Equipment]] |
| [[GroupReader]] | 批次讀取 + 解碼 | [[_MOC Equipment]] |
| [[ModbusDataType]] | 二進位 → 型別值解碼 | [[_MOC Modbus]] |
| [[ProcessingPipeline]] | Transform 串接處理 | [[_MOC Equipment]] |
| [[AlarmStateManager]] | 遲滯邏輯告警管理 | [[_MOC Equipment]] |
| [[DeviceEventEmitter]] | 非同步事件發射 | [[Event System]] |
| [[DataUploadManager]] | 批次上傳至 MongoDB | [[_MOC Manager]] |
| [[StateSyncManager]] | 即時同步至 Redis | [[_MOC Manager]] |

## 4.2 控制循環

從設備數據聚合到功率命令寫入的完整流程：

```
ContextBuilder.build()
    │  讀取 DeviceRegistry 中各設備的 latest_values
    │  根據 ContextMapping 聚合、轉換
    ▼
StrategyContext { soc, extra: {voltage, frequency, ...} }
    │
    ▼
StrategyExecutor  (PERIODIC / TRIGGERED / HYBRID)
    │  呼叫當前 Strategy.execute(context)
    ▼
Command { p_target: 500.0, q_target: 100.0 }
    │
    ▼
ProtectionGuard.apply()  (保護鏈)
    │  SOCProtection → ReversePowerProtection → SystemAlarmProtection
    ▼
Protected Command { p_target: 450.0, q_target: 100.0 }
    │
    ▼
CommandRouter.route()
    │  根據 CommandMapping 路由到設備
    │  單播 (device_id) 或 廣播 (trait)
    ▼
AsyncModbusDevice.write("active_power", 450.0)
    │  ValidatedWriter → encode → Modbus write → (verify)
    ▼
物理設備執行功率命令
```

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| [[ContextBuilder]] | 設備數據 -> [[StrategyContext]] | [[_MOC Integration]] |
| [[DeviceRegistry]] | Trait-based 設備查詢 | [[_MOC Integration]] |
| [[StrategyExecutor]] | 週期/觸發/混合模式執行 | [[_MOC Controller]] |
| [[ProtectionGuard]] | 保護規則鏈 | [[_MOC Controller]] |
| [[CommandRouter]] | Command -> 設備寫入路由 | [[_MOC Integration]] |
| [[ValidatedWriter]] | 驗證 + 寫入 + 回讀 | [[_MOC Equipment]] |

## 4.3 模式切換流程

[[ModeManager]] 管理多模式優先級切換，支援基礎模式與覆蓋模式：

```
ModeManager
    │
    ├── register("pq", PQModeStrategy, priority=10)
    ├── register("pv_smooth", PVSmoothStrategy, priority=10)
    ├── register("qv", QVStrategy, priority=10)
    ├── register("protection_stop", StopStrategy, priority=100)
    │
    ├── set_base_mode("pq")           →  正常運行用 PQ
    ├── add_base_mode("qv")           →  多策略 → CascadingStrategy
    ├── push_override("protection_stop") →  告警時覆蓋為停機
    └── pop_override("protection_stop")  →  告警解除，恢復原策略

    優先級邏輯:
    ┌─────────────────────────────────────┐
    │  Override Stack (高優先)             │
    │   protection_stop (100) ← 最高優先   │
    │   manual_override (50)              │
    ├─────────────────────────────────────┤
    │  Base Modes (低優先)                 │
    │   pq (10)                           │
    │   qv (10)  ← 多個 base → Cascading  │
    └─────────────────────────────────────┘
```

### 運作機制

1. **基礎模式 (Base Mode)** — 正常運行時使用的策略，可註冊多個相同優先級的策略
2. **覆蓋模式 (Override)** — 高優先級事件觸發，例如保護停機，優先於所有基礎模式
3. **多策略級聯** — 當有多個基礎模式時，自動組合為 [[CascadingStrategy]] 進行功率分配
4. **優先級堆疊** — Override 以堆疊方式管理，pop 後自動恢復前一策略

### 關鍵元件

| 元件 | 職責 | 頁面 |
|------|------|------|
| [[ModeManager]] | 模式註冊、切換、優先級管理 | [[_MOC Controller]] |
| [[CascadingStrategy]] | 多策略功率級聯分配 | [[_MOC Controller]] |
| [[ProtectionGuard]] | 觸發自動停機覆蓋 | [[_MOC Controller]] |

## 相關頁面

- [[Layered Architecture]] — 各層職責與依賴關係
- [[Design Patterns]] — 相關設計模式（Strategy、Command、Chain of Responsibility）
- [[Event System]] — 資料流中的事件機制
- [[_MOC Architecture]] — 返回架構索引
