---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-05
version: ">=0.6.2"
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
