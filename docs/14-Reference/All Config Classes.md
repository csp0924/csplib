---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
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

### Controller 層

| 配置類別 | 說明 |
|----------|------|
| [[ExecutionConfig]] | 執行配置 (`mode`, `interval_seconds`) |
| [[PQModeConfig]] | PQ 模式配置 (`p`, `q`) |
| [[PVSmoothConfig]] | PV 平滑配置 (`capacity`, `ramp_rate`, `pv_loss`, `min_history`) |
| [[QVConfig]] | QV 控制配置 (`nominal_voltage`, `v_set`, `droop`, ...) |
| [[FPConfig]] | FP 控制配置 (`f_base`, `f1`~`f6`, `p1`~`p6`) |
| [[IslandModeConfig]] | 離網模式配置 (`sync_timeout`) |
| [[SOCProtectionConfig]] | SOC 保護配置 (`soc_high`, `soc_low`, `warning_band`) |
| [[CapacityConfig]] | 容量配置 (`s_max_kva`) |

### Manager 層

| 配置類別 | 說明 |
|----------|------|
| [[UnifiedConfig]] | 統一管理器配置 (`enable_alarm`, `enable_command`, ...) |

### Integration 層

| 配置類別 | 說明 |
|----------|------|
| [[GridControlLoopConfig]] | 控制迴圈配置 (`context_mappings`, `command_mappings`, ...) |
| [[SystemControllerConfig]] | 系統控制器配置 (`protection_rules`, `auto_stop_on_alarm`, ...) |

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
