---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-17
version: ">=0.8.1"

---

# 所有類別

使用 Dataview 動態查詢所有標記為 `type/class` 的頁面。

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class")
SORT file.name ASC
```

---

## 依模組分類

### Core

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/core")
SORT file.name ASC
```

**快速參考：**

| 類別 | 說明 |
|------|------|
| [[AsyncLifecycleMixin]] | 非同步生命週期管理基類 |
| [[HealthCheckable]] | 健康檢查協定 |
| [[CircuitBreaker]] | 斷路器 |
| [[RetryPolicy]] | 重試策略 |
| [[RuntimeParameters]] | 執行期可變參數容器（v0.5.0） |
| [[Logging\|LogFilter]] | 模組等級過濾器，最長前綴匹配（v0.7.0） |
| [[Logging\|SinkManager]] | 全域 Sink 生命週期管理單例（v0.7.0） |
| [[Logging\|SinkInfo]] | Sink 資訊 frozen dataclass（v0.7.0） |
| [[Logging\|FileSinkConfig]] | 檔案 Sink 配置 frozen dataclass（v0.7.0） |
| [[Logging\|LogContext]] | Async-safe 結構化日誌上下文（v0.7.0） |
| [[Logging\|LogCapture]] | 測試用日誌捕獲器（v0.7.0） |
| [[Logging\|CapturedRecord]] | 單筆捕獲 log 記錄（v0.7.0） |
| [[Logging\|RemoteLevelSource]] | 遠端等級來源 Protocol（v0.7.0） |
| [[Logging\|AsyncSinkAdapter]] | 非同步 Sink 轉接器（v0.7.0） |

### Modbus

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/modbus")
SORT file.name ASC
```

### CAN（v0.4.2）

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/can")
SORT file.name ASC
```

### Equipment

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/equipment")
SORT file.name ASC
```

**快速參考（v0.5.0+ 新增）：**

| 類別 | 說明 |
|------|------|
| [[Actionable]] | DO 動作介面（v0.5.0） |
| [[EquipmentTemplate]] | 設備模型範本定義（v0.5.2） |
| [[PointOverride]] | 點位覆寫定義（v0.5.2） |
| [[DeviceFactory]] | 設備工廠（v0.5.2） |

### Controller

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/controller")
SORT file.name ASC
```

**快速參考（v0.5.0+ 新增）：**

| 類別 | 說明 |
|------|------|
| [[DroopStrategy]] | Droop 控制策略（v0.5.0） |
| [[RampStopStrategy]] | 斜率停機策略（v0.5.0） |
| [[PowerCompensator]] | FF + I 閉迴路功率補償器（v0.5.1） |
| [[FFCalibrationStrategy]] | FF 表格校準策略（v0.5.1） |
| [[CommandProcessor]] | 後保護命令處理管線協定（v0.5.1） |
| [[DynamicSOCProtection]] | 動態 SOC 保護規則（v0.5.0） |
| [[GridLimitProtection]] | 電網限制保護規則（v0.5.0） |
| [[RampStopProtection]] | 斜率停機保護規則（v0.5.0） |

**快速參考（v0.8.0 新增）：**

| 名稱 | 說明 |
|------|------|
| [[Command\|NoChange]] | `Command.p_target` / `q_target` 的「此軸不變更」sentinel 類別（v0.8.0） |

### Manager

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/manager")
SORT file.name ASC
```

**快速參考（v0.5.0+ 新增）：**

| 類別 | 說明 |
|------|------|
| [[BatchUploader]] | 批次上傳基底類別（v0.5.0） |

### Integration

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/integration")
SORT file.name ASC
```

**快速參考（v0.5.0+ 新增）：**

| 類別 | 說明 |
|------|------|
| [[AggregationResult]] | 聚合結果資料結構（v0.5.0） |
| [[CapabilityRequirement]] | 能力需求定義（v0.5.0） |

**快速參考（v0.8.1 新增）：**

| 類別 | 說明 |
|------|------|
| [[Command Refresh\|CommandRefreshService]] | Reconciler：把 desired state 週期重傳到設備（v0.8.1） |
| [[SystemController\|CommandRefreshConfig]] | `CommandRefreshService` 的 frozen dataclass 配置（v0.8.1） |
| [[SystemController\|HeartbeatConfig]] | 心跳服務結構化配置（收攏舊版 6 欄位，v0.8.1） |
| [[Command Refresh\|HeartbeatValueGenerator]] | 心跳值產生器 `@runtime_checkable` Protocol（v0.8.1） |
| [[Command Refresh\|ToggleGenerator]] | 0/1 交替的心跳值產生器（v0.8.1） |
| [[Command Refresh\|IncrementGenerator]] | 遞增計數心跳值產生器，到 `max_value` 後歸零（v0.8.1） |
| [[Command Refresh\|ConstantGenerator]] | 常數值心跳值產生器（v0.8.1） |
| [[Command Refresh\|HeartbeatTarget]] | 心跳寫入目標 `@runtime_checkable` Protocol（v0.8.1） |
| [[Command Refresh\|DeviceHeartbeatTarget]] | `AsyncModbusDevice` 點位的心跳寫入目標（v0.8.1） |
| [[Command Refresh\|GatewayRegisterHeartbeatTarget]] | Modbus Gateway register 的心跳寫入目標（v0.8.1） |

### Storage (Mongo / Redis)

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND (contains(tags, "layer/mongo") OR contains(tags, "layer/redis"))
SORT file.name ASC
```

### Cluster

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/cluster")
SORT file.name ASC
```

### Modbus Gateway（v0.6.0）

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/modbus_gateway")
SORT file.name ASC
```

**快速參考：**

| 類別 | 說明 |
|------|------|
| [[ModbusGatewayServer]] | Modbus TCP 閘道伺服器 |
| [[GatewayRegisterMap]] | 閘道暫存器映射 |
| [[CommunicationWatchdog]] | 通訊看門狗 |
| [[AddressWhitelistValidator]] | 位址白名單驗證器 |
| [[RedisPublishHook]] | Redis 發佈鉤子 |
| [[CallbackHook]] | 回呼鉤子 |
| [[StatePersistHook]] | 狀態持久化鉤子 |
| [[RedisSubscriptionSource]] | Redis 訂閱資料來源 |
| [[PollingCallbackSource]] | 輪詢回呼資料來源 |
| [[GatewayConfig\|RegisterNotWritableError]] | EMS 寫入 writable=False register 時拋出（v0.7.3） |

### Modbus Server（v0.5.2）

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/modbus_server")
SORT file.name ASC
```

**快速參考：**

| 類別 | 說明 |
|------|------|
| [[SimulationServer]] | Modbus TCP 模擬伺服器 |
| [[MicrogridSimulator]] | 微電網模擬器 |
| [[PCSSimulator]] | PCS 模擬器 |
| [[PowerMeterSimulator]] | 電錶模擬器 |
| [[SolarSimulator]] | 太陽能模擬器 |
| [[GeneratorSimulator]] | 發電機模擬器 |
| [[LoadSimulator]] | 負載模擬器 |
| [[DeviceLinkConfig]] | 設備到電表的功率路由配置（v0.6.2） |
| [[MeterAggregationConfig]] | 電表聚合樹配置（v0.6.2） |

### Statistics（v0.6.0）

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/statistics")
SORT file.name ASC
```

**快速參考：**

| 類別 | 說明 |
|------|------|
| [[StatisticsEngine]] | 統計計算引擎 |
| [[DeviceEnergyTracker]] | 設備能源追蹤器 |
| [[StatisticsManager]] | 統計管理器 |

### GUI（v0.5.2）

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/gui")
SORT file.name ASC
```

### Hierarchical Control（v0.6.0）

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/hierarchical")
SORT file.name ASC
```

**快速參考：**

| 類別 | 說明 |
|------|------|
| [[SubExecutorAgent]] | 遠端子執行器代理協定 |
| [[TransportAdapter]] | 傳輸抽象協定 |
