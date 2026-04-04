---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: ">=0.4.2"
---

# 所有列舉

使用 Dataview 動態查詢所有標記為 `type/enum` 的頁面。

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/enum")
SORT file.name ASC
```

---

## 快速參考

### Modbus 層

| 列舉 | 值 |
|------|------|
| [[ByteOrder]] | `BIG_ENDIAN`, `LITTLE_ENDIAN` |
| [[RegisterOrder]] | `HIGH_FIRST`, `LOW_FIRST` |
| [[Parity]] | `NONE`, `EVEN`, `ODD` |
| [[FunctionCode]] | `READ_HOLDING_REGISTERS`, `READ_INPUT_REGISTERS`, `WRITE_SINGLE_REGISTER`, `WRITE_MULTIPLE_REGISTERS`, `READ_COILS`, `READ_DISCRETE_INPUTS` |

### Equipment 層

| 列舉 | 值 |
|------|------|
| [[AlarmLevel]] | `INFO`, `WARNING`, `CRITICAL`, `PROTECTION` |
| [[WriteStatus]] | `SUCCESS`, `VERIFICATION_FAILED`, ... |

### Controller 層

| 列舉 | 值 |
|------|------|
| [[ExecutionMode]] | `PERIODIC`, `TRIGGERED`, `HYBRID` |
| [[ModePriority]] | `SCHEDULE` (10), `MANUAL` (50), `PROTECTION` (100) |
| [[SwitchSource]] | `MANUAL`, `SCHEDULE`, `EVENT`, `INTERNAL` |

### Manager 層

| 列舉 | 值 |
|------|------|
| [[AlarmStatus]] | `ACTIVE`, `RESOLVED` |

### Integration 層

| 列舉 | 值 |
|------|------|
| [[AggregateFunc]] | `AVERAGE`, `SUM`, `MIN`, `MAX`, `FIRST` |
| [[HeartbeatMode]] | `TOGGLE`, `INCREMENT`, `CONSTANT` |

### Core 層

| 列舉 | 值 |
|------|------|
| [[HealthStatus]] | `HEALTHY`, `DEGRADED`, `UNHEALTHY` |
| [[CircuitState]] | `CLOSED`, `OPEN`, `HALF_OPEN` |

### CAN 層（v0.4.2）

（CAN 層目前無獨立 Enum，以 dataclass 配置為主）

### Modbus 層（Queue 相關，v0.4.2）

| 列舉 | 值 |
|------|------|
| [[RequestPriority]] | `HIGH`, `NORMAL`, `LOW`（具體值依實作） |
| [[CircuitBreakerState]] | （Modbus 客戶端斷路器狀態，與 Core CircuitState 分離） |
