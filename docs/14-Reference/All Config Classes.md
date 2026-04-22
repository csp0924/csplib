---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-23
version: ">=0.10.0"

---

# 所有配置類別

使用 Dataview 動態查詢所有標記為 `type/config` 的頁面。

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/config")
SORT file.name ASC
```

---

## 快速參考

### Core 層

| 配置類別 | 說明 |
|----------|------|
| [[Logging\|FileSinkConfig]] | 檔案 Sink 配置（`path`, `rotation`, `retention`, `compression`）（v0.7.0） |

### Modbus 層

| 配置類別 | 說明 |
|----------|------|
| [[ModbusTcpConfig]] | TCP 連線配置 (`host`, `port`) |
| [[ModbusRtuConfig]] | RTU 連線配置 (`port`, `baudrate`) |

### Equipment 層

| 配置類別 | 說明 |
|----------|------|
| [[DeviceConfig]] | 設備配置 (`device_id`, `unit_id`, `read_interval`, ...) |
| [[HysteresisConfig]] | 告警遲滯配置 (`activate_threshold`, `clear_threshold`) |
| [[DOActionConfig]] | DO 動作配置（v0.5.0） |

### Controller 層

| 配置類別 | 說明 |
|----------|------|
| [[ExecutionConfig]] | 執行配置 (`mode`, `interval_seconds`) |
| [[PQModeConfig]] | PQ 模式配置 (`p`, `q`) |
| [[PVSmoothConfig]] | PV 平滑配置 (`capacity`, `ramp_rate`, `pv_loss`, `min_history`) |
| [[QVConfig]] | QV 控制配置 (`nominal_voltage`, `v_set`, `droop`, ...) |
| [[FPConfig]] | FP 控制配置 (`f_base`, `f1`~`f6`, `p1`~`p6`) |
| [[DroopConfig]] | Droop 控制配置（v0.5.0） |
| [[IslandModeConfig]] | 離網模式配置 (`sync_timeout`) |
| [[SOCProtectionConfig]] | SOC 保護配置 (`soc_high`, `soc_low`, `warning_band`) |
| [[CapacityConfig]] | 容量配置 (`s_max_kva`) |
| [[FFCalibrationConfig]] | FF 表格校準配置（v0.5.1） |
| [[PowerCompensatorConfig]] | 功率補償器配置（v0.5.1） |
| [[LoadSheddingConfig]] | 負載卸載配置（v0.4.2） |

### Manager 層

| 配置類別 | 說明 |
|----------|------|
| [[UnifiedConfig]] | 統一管理器配置 (`alarm_repository`, `command_repository`, `batch_uploader`, ...) |
| [[AlarmPersistenceConfig]] | 告警持久化配置 |
| [[CommandAdapterConfig]] | 命令適配器配置 |
| [[StateSyncConfig]] | 狀態同步配置（v0.10.0 新增 `key_prefix` / `channel_prefix` 支援多站隔離） |
| [[ScheduleServiceConfig]] | 排程服務配置（v0.4.2） |
| [[ManagerDescribable\|UnifiedManagerStatus]] | `UnifiedDeviceManager.describe()` 的回傳快照（v0.10.0） |

### Integration 層

| 配置類別 | 說明 |
|----------|------|
| [[GridControlLoopConfig]] | 控制迴圈配置 (`context_mappings`, `command_mappings`, ...) |
| [[SystemControllerConfig]] | 系統控制器配置 (`protection_rules`, `auto_stop_on_alarm`, ...) |
| [[CapabilityRequirement]] | 能力需求定義（v0.5.0） |
| [[DistributedConfig]] | 分散式控制配置（v0.4.2） |

### Storage 層

| 配置類別 | 說明 |
|----------|------|
| [[MongoConfig]] | MongoDB 連線配置 (`host`, `port`, `replica_hosts`, ...) |
| [[UploaderConfig]] | 批次上傳配置 (`flush_interval`, `batch_size_threshold`, ...) |
| [[RedisConfig]] | Redis 連線配置 (`host`, `port`, `sentinels`, ...) |
| [[TLSConfig]] | TLS 連線配置 (`ca_certs`, `certfile`, `keyfile`) |

### Cluster 層

| 配置類別 | 說明 |
|----------|------|
| [[ClusterConfig]] | 叢集配置 (`instance_id`, `namespace`, `lease_ttl`, ...) |
| [[EtcdConfig]] | etcd 連線配置 (`endpoints`, `username`, `password`) |

### Modbus Gateway 層（v0.6.0）

| 配置類別 | 說明 |
|----------|------|
| [[GatewayServerConfig]] | 閘道伺服器配置 (`host`, `port`, `register_defs`, ...) |
| [[GatewayRegisterDef]] | 閘道暫存器定義 |
| [[WatchdogConfig]] | 通訊看門狗配置 |
| [[WriteRule]] | 寫入規則定義 |

### Modbus Server 層（v0.5.2）

| 配置類別 | 說明 |
|----------|------|
| [[ServerConfig]] | 模擬伺服器配置 |
| [[SimulatedDeviceConfig]] | 模擬設備配置 |
| [[SimulatedPoint]] | 模擬點位配置 |
| [[PCSSimConfig]] | PCS 模擬配置 |
| [[PowerMeterSimConfig]] | 電錶模擬配置 |
| [[SolarSimConfig]] | 太陽能模擬配置 |
| [[GeneratorSimConfig]] | 發電機模擬配置 |
| [[LoadSimConfig]] | 負載模擬配置 |
| [[MicrogridConfig]] | 微電網模擬配置 |
| [[AlarmPointConfig]] | 告警點位配置 |
| [[DeviceLinkConfig]] | 設備到電表的功率路由配置（v0.6.2） |
| [[MeterAggregationConfig]] | 電表聚合樹配置（v0.6.2） |
| [[BMSSimulator]] | BMS 模擬器配置（BMSSimConfig，v0.6.2） |

### Statistics 層（v0.6.0）

| 配置類別 | 說明 |
|----------|------|
| [[StatisticsConfig]] | 統計配置 |
| [[MetricDefinition]] | 指標定義 |
| [[PowerSumDefinition]] | 功率加總定義 |
| [[DeviceMeterType]] | 設備計量型別 |

### GUI 層（v0.5.2）

| 配置類別 | 說明 |
|----------|------|
| [[GUIConfig]] | Web GUI 配置 |
