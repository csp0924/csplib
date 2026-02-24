---
tags:
  - type/moc
  - layer/equipment
  - status/complete
---

# _MOC Equipment

> **設備抽象層 (`csp_lib.equipment`)**

Equipment 模組是 csp_lib 的核心抽象層，建構於 [[_MOC Modbus]] 之上，提供完整的非同步 Modbus 設備管理能力。本層將底層暫存器 I/O 封裝為高階設備模型，包含點位定義、資料轉換管線、告警系統、傳輸優化、以及事件驅動架構。

---

## 索引

### 點位定義

| 頁面 | 說明 |
|------|------|
| [[ReadPoint]] | 讀取點位定義 |
| [[WritePoint]] | 寫入點位定義 |
| [[Validators]] | 值驗證器（Range / Enum / Composite） |

### 資料處理

| 頁面 | 說明 |
|------|------|
| [[Transforms]] | 10 種資料轉換步驟 |
| [[ProcessingPipeline]] | 串聯多個轉換步驟的處理管線 |

### 告警系統

| 頁面 | 說明 |
|------|------|
| [[AlarmDefinition]] | 告警定義、等級、遲滯設定 |
| [[Alarm Evaluators]] | 三種告警評估器（BitMask / Threshold / Table） |
| [[AlarmStateManager]] | 告警狀態管理與遲滯處理 |

### 設備本體

| 頁面 | 說明 |
|------|------|
| [[AsyncModbusDevice]] | 核心設備類別，整合讀寫、告警、事件 |
| [[DeviceConfig]] | 設備設定參數 |
| [[DeviceEventEmitter]] | 事件發射器與 9 種事件類型 |

### 傳輸層

| 頁面 | 說明 |
|------|------|
| [[PointGrouper]] | 點位分組器，合併相鄰暫存器 |
| [[GroupReader]] | 群組批次讀取與解碼 |
| [[ReadScheduler]] | 固定 + 輪替讀取排程 |
| [[ValidatedWriter]] | 驗證寫入與讀回確認 |

### 聚合與模擬

| 頁面 | 說明 |
|------|------|
| [[Aggregators]] | 聚合器（CoilToBitmask / ComputedValue / Pipeline） |
| [[VirtualMeter]] | 虛擬電表模擬器 |
| [[CurveRegistry]] | 測試曲線註冊表 |

---

## Dataview

```dataview
TABLE tags AS "標籤", source AS "來源"
FROM "04-Equipment"
WHERE file.name != "_MOC Equipment"
SORT file.name ASC
```

---

## 相關模組

- 上游：[[_MOC Modbus]] -- 底層 Modbus 通訊
- 下游：[[_MOC Controller]] -- 控制策略層
- 下游：[[_MOC Integration]] -- 系統整合層
- 下游：[[_MOC Manager]] -- 管理層
