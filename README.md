# CSP Library

CSP Common Library 是一個模組化的 Python 工具集，專為能源管理系統與工業設備通訊設計。

## 特點

- **分層架構**：Core → Modbus → Equipment → Controller → Manager → Integration
- **Async-first**：所有設備 I/O 與管理器皆採用 asyncio
- **Event-driven**：設備事件系統（值變化、告警、連線狀態）
- **按需安裝**：Optional dependencies 避免引入不必要的套件
- **Frozen dataclass configs**：不可變設定物件，確保執行時安全

## 安裝

```bash
# 基本安裝
pip install csp0924_lib

# 按需安裝特定功能
pip install csp0924_lib[modbus]     # Modbus 通訊
pip install csp0924_lib[mongo]      # MongoDB 批次上傳
pip install csp0924_lib[redis]      # Redis 客戶端
pip install csp0924_lib[monitor]    # 系統監控 (psutil)
pip install csp0924_lib[cluster]    # 分散式叢集 (etcd)
pip install csp0924_lib[all]        # 所有功能
```

---

## 架構總覽

```
┌─────────────────────────────────────────────────────────┐
│                    Integration Layer                     │
│  DeviceRegistry · ContextBuilder · CommandRouter         │
│  GridControlLoop · SystemController                      │
├─────────────────────────────────────────────────────────┤
│              Manager Layer              │   Controller   │
│  DeviceManager · AlarmPersistence       │   Strategy     │
│  DataUpload · StateSync · Unified       │   Executor     │
│  WriteCommand                           │   Protection   │
├─────────────────────────────────────────┤   ModeManager  │
│              Equipment Layer            │   Cascading    │
│  AsyncModbusDevice · Points · Alarms    │                │
│  Transport · Transforms · Pipeline      │                │
├─────────────────────────────────────────┴────────────────┤
│                      Modbus Layer                        │
│  DataTypes · Codec · Clients (TCP/RTU/Shared)            │
├─────────────────────────────────────────────────────────┤
│                       Core Layer                         │
│  Logging · Lifecycle · Errors · Health                   │
└─────────────────────────────────────────────────────────┘

附加模組: Mongo · Redis · Cluster · Monitor · Notification · Modbus Server
```

---

## 快速入門

### 基本設備讀寫

```python
import asyncio
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig, UInt16, Float32
from csp_lib.equipment.core import ReadPoint, WritePoint, pipeline, ScaleTransform, RoundTransform
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig

# 1. Define points
read_points = [
    ReadPoint(name="voltage", address=0, data_type=Float32()),
    ReadPoint(
        name="temperature",
        address=2,
        data_type=UInt16(),
        pipeline=pipeline(ScaleTransform(0.1, -40), RoundTransform(1)),
    ),
]
write_points = [
    WritePoint(name="power_limit", address=100, data_type=UInt16()),
]

# 2. Create device
config = DeviceConfig(device_id="inverter_001", unit_id=1, read_interval=1.0)
client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100", port=502))
device = AsyncModbusDevice(
    config=config,
    client=client,
    always_points=read_points,
    write_points=write_points,
)

# 3. Use device
async def main():
    async with device:
        device.on("value_change", lambda p: print(f"{p.point_name}: {p.new_value}"))
        values = await device.read_all()
        print(f"Voltage: {values['voltage']}V")
        result = await device.write("power_limit", 5000)
        print(f"Write: {result.status}")

asyncio.run(main())
```

### 控制策略

```python
from csp_lib.controller import (
    PQModeConfig, PQModeStrategy,
    StrategyExecutor, StrategyContext,
)

config = PQModeConfig(p=100, q=50)
strategy = PQModeStrategy(config)

executor = StrategyExecutor(context_provider=lambda: StrategyContext())
await executor.set_strategy(strategy)
await executor.run()  # Periodic execution loop
```

### 完整系統整合

```python
from csp_lib.integration import (
    DeviceRegistry, GridControlLoop, GridControlLoopConfig,
    ContextMapping, CommandMapping, DataFeedMapping,
)
from csp_lib.controller import PQModeStrategy, PQModeConfig, SystemBase

# Register devices
registry = DeviceRegistry()
registry.register(meter, traits=["meter"])
registry.register(pcs, traits=["pcs"])

# Configure loop
config = GridControlLoopConfig(
    context_mappings=[
        ContextMapping(point_name="soc", context_field="soc", device_id="bms_001"),
        ContextMapping(point_name="power", context_field="extra.meter_power", trait="meter"),
    ],
    command_mappings=[
        CommandMapping(command_field="p_target", point_name="p_setpoint", trait="pcs"),
    ],
    system_base=SystemBase(p_base=1000, q_base=500),
)

# Run
loop = GridControlLoop(registry, config)
await loop.set_strategy(PQModeStrategy(PQModeConfig(p=200)))
async with loop:
    await asyncio.sleep(3600)  # Run for 1 hour
```

---

## Core 模組 (`csp_lib.core`)

### Logging

基於 loguru 的模組化日誌系統，支援依模組名稱獨立設定 log 等級。

```python
from csp_lib.core import get_logger, set_level, configure_logging

# Initialize logging
configure_logging(level="INFO")

# Get module-specific logger
logger = get_logger("csp_lib.mongo")
logger.info("Connected to MongoDB")

# Set level per module
set_level("DEBUG", module="csp_lib.mongo")
set_level("WARNING", module="csp_lib.redis")
```

### AsyncLifecycleMixin

標準的非同步生命週期管理基底類別，支援 `async with` 語法。

```python
from csp_lib.core import AsyncLifecycleMixin

class MyService(AsyncLifecycleMixin):
    async def _on_start(self) -> None:
        ...  # Startup logic

    async def _on_stop(self) -> None:
        ...  # Cleanup logic

async with MyService() as svc:
    ...  # Service is running
```

### 錯誤階層

| 例外類別 | 說明 |
|---------|------|
| `DeviceError(device_id, message)` | 設備層基礎例外 |
| `DeviceConnectionError` | 連線/斷線失敗 |
| `CommunicationError` | 讀寫逾時/解碼錯誤 |
| `AlarmError(device_id, alarm_code, message)` | 告警觸發 |
| `ConfigurationError(message)` | 配置無效（非設備層級） |

### 健康檢查

```python
from csp_lib.core import HealthStatus, HealthReport, HealthCheckable

class MyComponent:
    def health(self) -> HealthReport:
        return HealthReport(
            status=HealthStatus.HEALTHY,
            component="my_component",
            message="All systems operational",
        )
```

| HealthStatus | 說明 |
|-------------|------|
| `HEALTHY` | 正常 |
| `DEGRADED` | 部分降級 |
| `UNHEALTHY` | 異常 |

---

## Modbus 模組 (`csp_lib.modbus`)

需安裝：`pip install csp0924_lib[modbus]`

### 資料型別

| 型別 | Register 數 | 說明 |
|------|-----------|------|
| `Int16` | 1 | 帶號 16-bit 整數 |
| `UInt16` | 1 | 無號 16-bit 整數 |
| `Int32` | 2 | 帶號 32-bit 整數 |
| `UInt32` | 2 | 無號 32-bit 整數 |
| `Int64` | 4 | 帶號 64-bit 整數 |
| `UInt64` | 4 | 無號 64-bit 整數 |
| `Float32` | 2 | 32-bit 浮點數 |
| `Float64` | 4 | 64-bit 浮點數 |
| `DynamicInt(n)` | n | 動態長度帶號整數 |
| `DynamicUInt(n)` | n | 動態長度無號整數 |
| `ModbusString(n)` | n | 字串 (n registers) |

```python
from csp_lib.modbus import Float32

data_type = Float32()
registers = data_type.encode(123.45)  # -> [0x42F6, 0xE666]
value = data_type.decode(registers)   # -> 123.45
```

### 列舉

| 列舉 | 值 |
|------|------|
| `ByteOrder` | `BIG_ENDIAN`, `LITTLE_ENDIAN` |
| `RegisterOrder` | `HIGH_FIRST`, `LOW_FIRST` |
| `Parity` | `NONE`, `EVEN`, `ODD` |
| `FunctionCode` | `READ_HOLDING_REGISTERS`, `READ_INPUT_REGISTERS`, `WRITE_SINGLE_REGISTER`, `WRITE_MULTIPLE_REGISTERS`, `READ_COILS`, `READ_DISCRETE_INPUTS` |

### 設定類別

```python
from csp_lib.modbus import ModbusTcpConfig, ModbusRtuConfig

# TCP
tcp_config = ModbusTcpConfig(host="192.168.1.100", port=502)

# RTU
rtu_config = ModbusRtuConfig(port="COM1", baudrate=9600)
```

### 客戶端

| 客戶端 | 說明 | 使用時機 |
|--------|------|---------|
| `PymodbusTcpClient` | TCP 客戶端 | 一對一設備連線 |
| `PymodbusRtuClient` | RTU 客戶端 | Serial port 連線 |
| `SharedPymodbusTcpClient` | 共享 TCP 客戶端 | 多設備共用同一 TCP 連線 |

```python
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig

client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100"))
await client.connect()
registers = await client.read_holding_registers(0, 2, unit=1)
await client.disconnect()
```

### Codec

```python
from csp_lib.modbus import ModbusCodec, Float32, ByteOrder, RegisterOrder

codec = ModbusCodec(byte_order=ByteOrder.BIG_ENDIAN, register_order=RegisterOrder.HIGH_FIRST)
encoded = codec.encode(Float32(), 123.45)
decoded = codec.decode(Float32(), encoded)
```

### 例外

| 例外 | 說明 |
|------|------|
| `ModbusError` | Modbus 基礎例外 |
| `ModbusEncodeError` | 編碼錯誤 |
| `ModbusDecodeError` | 解碼錯誤 |
| `ModbusConfigError` | 配置錯誤 |

---

## Equipment 模組 (`csp_lib.equipment`)

### 點位定義

```python
from csp_lib.equipment.core import ReadPoint, WritePoint, PointMetadata
from csp_lib.modbus import UInt16, Float32, FunctionCode

# Read point
ReadPoint(
    name="voltage",
    address=0,
    data_type=Float32(),
    function_code=FunctionCode.READ_HOLDING_REGISTERS,  # default
    pipeline=None,
    read_group="",
)

# Write point with validator
from csp_lib.equipment.core import RangeValidator

WritePoint(
    name="power_limit",
    address=100,
    data_type=UInt16(),
    function_code=FunctionCode.WRITE_MULTIPLE_REGISTERS,  # default
    validator=RangeValidator(min_value=0, max_value=10000),
)
```

### 驗證器

| 驗證器 | 說明 |
|--------|------|
| `RangeValidator(min_value, max_value)` | 範圍驗證 |
| `EnumValidator(allowed_values)` | 枚舉驗證 |
| `CompositeValidator(validators)` | 組合多個驗證器 |

### 資料轉換

| Transform | 說明 | 範例 |
|-----------|------|------|
| `ScaleTransform(magnitude, offset)` | 縮放: `value * magnitude + offset` | 溫度: `ScaleTransform(0.1, -40)` |
| `RoundTransform(decimals)` | 四捨五入 | `RoundTransform(1)` |
| `EnumMapTransform(mapping, default)` | 數值→枚舉映射 | `{0: "STOP", 1: "RUN"}` |
| `ClampTransform(min_val, max_val)` | 值域限制 | `ClampTransform(0, 100)` |
| `BoolTransform()` | 布林轉換 | `0→False, 非0→True` |
| `BitExtractTransform(bit_offset, bit_length)` | 位元欄位提取 | `BitExtractTransform(8, 4)` |
| `ByteExtractTransform(byte_index)` | 位元組提取 | — |
| `MultiFieldExtractTransform(fields)` | 多位元欄位提取 | — |
| `InverseTransform()` | 取反 | `value * -1` |
| `PowerFactorTransform()` | 功率因數轉換 | — |

### 處理管線

串聯多個轉換步驟：

```python
from csp_lib.equipment.core import pipeline, ScaleTransform, RoundTransform

temp_pipeline = pipeline(
    ScaleTransform(0.1, -40),
    RoundTransform(1),
)
# 250 -> (250 * 0.1 - 40) = -15.0 -> -15.0
```

### 告警系統

#### 定義

```python
from csp_lib.equipment.alarm import AlarmDefinition, AlarmLevel, HysteresisConfig

alarm = AlarmDefinition(
    code="OVER_TEMP",
    name="Temperature too high",
    level=AlarmLevel.WARNING,
    hysteresis=HysteresisConfig(
        activate_threshold=3,  # 3 consecutive triggers to activate
        clear_threshold=5,     # 5 consecutive clears to deactivate
    ),
)
```

| AlarmLevel | 說明 |
|-----------|------|
| `INFO` | 資訊 |
| `WARNING` | 警告 |
| `CRITICAL` | 嚴重 |
| `PROTECTION` | 保護 |

#### 評估器

```python
from csp_lib.equipment.alarm import (
    BitMaskAlarmEvaluator,
    ThresholdAlarmEvaluator,
    TableAlarmEvaluator,
    ThresholdCondition,
    Operator,
)

# Bitmask: each bit maps to an alarm
bitmask = BitMaskAlarmEvaluator(
    _point_name="fault_code",
    bit_alarms={
        0: AlarmDefinition("OV", "Over Voltage"),
        1: AlarmDefinition("UV", "Under Voltage"),
    },
)

# Threshold: value comparison
threshold = ThresholdAlarmEvaluator(
    _point_name="temperature",
    conditions=[
        ThresholdCondition(
            alarm=AlarmDefinition("HIGH_TEMP", "High Temperature"),
            operator=Operator.GT,
            value=45.0,
        ),
    ],
)

# Table: exact value matching
table = TableAlarmEvaluator(
    _point_name="status",
    table={
        3: AlarmDefinition("FAULT", "Device Fault"),
        4: AlarmDefinition("EMERGENCY", "Emergency Stop"),
    },
)
```

#### 狀態管理

`AlarmStateManager` 內部管理告警狀態，支援遲滯機制。由 `AsyncModbusDevice` 自動使用。

### 傳輸層

```python
from csp_lib.equipment.transport import PointGrouper, GroupReader, ReadScheduler, ValidatedWriter

# Group adjacent points to minimize requests
grouper = PointGrouper()
groups = grouper.group(points)

# Batch read
reader = GroupReader(client=client, address_offset=0)
data = await reader.read_many(groups)

# Validated write
writer = ValidatedWriter(client=client)
result = await writer.write(point, value, verify=True)

# Scheduler: always + rotating reads
scheduler = ReadScheduler(
    always_groups=grouper.group(core_points),
    rotating_groups=[
        grouper.group(sbms1_points),
        grouper.group(sbms2_points),
    ],
)
# Cycle 1: always + rotating[0]
# Cycle 2: always + rotating[1]
# Cycle 3: always + rotating[0] ...
groups = scheduler.get_next_groups()
```

### AsyncModbusDevice

`AsyncModbusDevice` 是程式庫的核心類別，提供完整的非同步 Modbus 設備抽象。

#### 建構參數

```python
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig

device = AsyncModbusDevice(
    config=DeviceConfig(
        device_id="inverter_001",
        unit_id=1,
        address_offset=0,        # PLC 1-based: set to 1
        read_interval=1.0,       # Read interval (seconds)
        reconnect_interval=5.0,  # Reconnect interval (seconds)
        disconnect_threshold=5,  # Consecutive failures before disconnect
        max_concurrent_reads=1,  # Max concurrent reads (0=unlimited)
    ),
    client=client,
    always_points=read_points,
    rotating_points=[group_a, group_b],
    write_points=write_points,
    alarm_evaluators=[bitmask, threshold],
)
```

#### 生命週期

```python
# Context Manager (recommended)
async with device:
    ...  # auto connect + start, auto stop + disconnect

# Manual
await device.connect()
await device.start()
...
await device.stop()
await device.disconnect()
```

#### 狀態屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `is_connected` | `bool` | Socket 層級連線狀態 |
| `is_responsive` | `bool` | 設備通訊回應狀態 |
| `is_healthy` | `bool` | 健康 (connected + responsive + 無保護告警) |
| `is_protected` | `bool` | 是否有保護告警 |
| `is_running` | `bool` | 讀取循環是否運行中 |
| `latest_values` | `dict` | 最新讀取值字典 |
| `active_alarms` | `list` | 目前啟用的告警列表 |
| `device_id` | `str` | 設備 ID |

#### 讀寫操作

```python
# Read all points
values = await device.read_all()
# -> {"voltage": 220.5, "temperature": 25.3}

# Write with optional verification
from csp_lib.equipment.transport import WriteStatus

result = await device.write("power_limit", 5000, verify=True)
if result.status == WriteStatus.SUCCESS:
    print("Success")
elif result.status == WriteStatus.VERIFICATION_FAILED:
    print(f"Readback mismatch: {result.error_message}")
```

#### 事件系統

| 事件名稱 | Payload | 說明 |
|---------|---------|------|
| `connected` | `ConnectedPayload` | 連線成功/恢復 |
| `disconnected` | `DisconnectPayload` | 斷線 |
| `read_complete` | `ReadCompletePayload` | 讀取完成 |
| `read_error` | `ReadErrorPayload` | 讀取錯誤 |
| `value_change` | `ValueChangePayload` | 值變化 |
| `write_complete` | `WriteCompletePayload` | 寫入成功 |
| `write_error` | `WriteErrorPayload` | 寫入失敗 |
| `alarm_triggered` | `DeviceAlarmPayload` | 告警觸發 |
| `alarm_cleared` | `DeviceAlarmPayload` | 告警解除 |

```python
# Register handler
cancel = device.on("value_change", async_handler)
cancel()  # Unsubscribe
```

### 聚合器

```python
from csp_lib.equipment.processing import (
    CoilToBitmaskAggregator,
    ComputedValueAggregator,
    AggregatorPipeline,
)
```

| 聚合器 | 說明 |
|--------|------|
| `CoilToBitmaskAggregator` | Coil 轉 Bitmask |
| `ComputedValueAggregator` | 計算衍生值 |
| `AggregatorPipeline` | 串聯多個聚合器 |

### 模擬

```python
from csp_lib.equipment.simulation import VirtualMeter, MeterReading, CurveRegistry
```

| 類別 | 說明 |
|------|------|
| `VirtualMeter` | 虛擬電表模擬器 |
| `MeterReading` | 電表讀數 |
| `CurveRegistry` | 測試曲線註冊表 |

---

## Controller 模組 (`csp_lib.controller`)

### 核心概念

#### Command

策略輸出的不可變命令：

```python
from csp_lib.controller import Command

cmd = Command(p_target=100.0, q_target=50.0)
cmd2 = cmd.with_p(200.0)  # Create new Command with P=200
# -> Command(P=200.0kW, Q=50.0kVar)
```

#### SystemBase

系統基準值，用於百分比與絕對值轉換：

```python
from csp_lib.controller import SystemBase

base = SystemBase(p_base=1000, q_base=500)
# p_kw = p_percent * p_base / 100
```

#### StrategyContext

策略執行時上下文，由 Executor 注入：

```python
from csp_lib.controller import StrategyContext

context = StrategyContext(
    last_command=Command(),
    soc=75.0,
    system_base=SystemBase(p_base=1000, q_base=500),
    current_time=None,  # Auto-injected by executor
    extra={"voltage": 380.0, "frequency": 60.0},
)

# Percent to kW/kVar conversion
p_kw = context.percent_to_kw(50)    # -> 500.0
q_kvar = context.percent_to_kvar(20) # -> 100.0
```

### Strategy 基底類別

所有策略繼承 `Strategy` 並實作：

```python
from csp_lib.controller import Strategy, ExecutionConfig, ExecutionMode

class MyStrategy(Strategy):
    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(p_target=100.0)

    async def on_activate(self) -> None:
        ...  # Optional: called when strategy is activated

    async def on_deactivate(self) -> None:
        ...  # Optional: called when strategy is deactivated
```

#### ExecutionMode

| 模式 | 說明 |
|------|------|
| `PERIODIC` | 固定週期執行 |
| `TRIGGERED` | 僅在外部觸發時執行 |
| `HYBRID` | 週期執行，但可被提前觸發 |

### 內建策略

| 策略 | 用途 | Config | 執行模式 |
|------|------|--------|---------|
| `PQModeStrategy` | 固定 P/Q 輸出 | `PQModeConfig(p, q)` | PERIODIC 1s |
| `PVSmoothStrategy` | PV 功率平滑 | `PVSmoothConfig(capacity, ramp_rate, pv_loss, min_history)` | PERIODIC 900s |
| `QVStrategy` | 電壓-無功功率控制 (Volt-VAR) | `QVConfig(nominal_voltage, v_set, droop, v_deadband, q_max_ratio)` | PERIODIC 1s |
| `FPStrategy` | 頻率-功率控制 (AFC) | `FPConfig(f_base, f1~f6, p1~p6)` | PERIODIC 1s |
| `IslandModeStrategy` | 離網模式 (Grid Forming) | `IslandModeConfig(sync_timeout)` | TRIGGERED |
| `BypassStrategy` | 直通模式 (維持 last_command) | — | PERIODIC 1s |
| `StopStrategy` | 停機 (P=0, Q=0) | — | PERIODIC 1s |
| `ScheduleStrategy` | 排程策略 (依時間執行) | — | PERIODIC 1s |

#### PQ 模式

```python
from csp_lib.controller import PQModeStrategy, PQModeConfig

strategy = PQModeStrategy(PQModeConfig(p=100, q=50))
strategy.update_config(PQModeConfig(p=200, q=0))
```

#### PV 平滑

```python
from csp_lib.controller import PVSmoothStrategy, PVSmoothConfig, PVDataService

pv_service = PVDataService(max_history=300)
strategy = PVSmoothStrategy(
    PVSmoothConfig(capacity=1000, ramp_rate=10, pv_loss=5),
    pv_service=pv_service,
)
# Feed data externally
pv_service.append(current_pv_power)
```

#### QV 控制

```python
from csp_lib.controller import QVStrategy, QVConfig

strategy = QVStrategy(QVConfig(
    nominal_voltage=380,
    v_set=100,     # Target voltage (%)
    droop=5,       # Droop coefficient (%)
    v_deadband=0,  # Deadband (%)
    q_max_ratio=0.5,
))
# Reads voltage from context.extra["voltage"]
```

#### FP 控制 (AFC)

```python
from csp_lib.controller import FPStrategy, FPConfig

strategy = FPStrategy(FPConfig(
    f_base=60.0,
    f1=-0.5, f2=-0.25, f3=-0.02, f4=0.02, f5=0.25, f6=0.5,
    p1=100, p2=52, p3=9, p4=-9, p5=-52, p6=-100,
))
# Reads frequency from context.extra["frequency"]
# Outputs power percentage, converted to kW via system_base
```

#### 離網模式

```python
from csp_lib.controller import IslandModeStrategy, IslandModeConfig, RelayProtocol

strategy = IslandModeStrategy(
    relay=my_relay,  # Implements RelayProtocol
    config=IslandModeConfig(sync_timeout=60),
)
# on_activate: opens ACB (enters island mode)
# on_deactivate: waits for sync_ok, then closes ACB (returns to grid)
```

### StrategyExecutor

管理策略的執行生命週期：

```python
from csp_lib.controller import StrategyExecutor

executor = StrategyExecutor(
    context_provider=get_context,      # Callable returning StrategyContext
    on_command=handle_command,         # Optional async callback
)

await executor.set_strategy(strategy)  # Auto calls on_activate/on_deactivate
await executor.run()                   # Main execution loop
executor.trigger()                     # Manual trigger (TRIGGERED/HYBRID)
executor.stop()                        # Stop loop

# One-shot execution (for testing)
command = await executor.execute_once()
```

### ConfigMixin

所有 Config 類別都繼承 `ConfigMixin`，支援從字典建立：

```python
config = PQModeConfig.from_dict({"p": 100, "q": 50, "extra": "ignored"})
# Supports camelCase -> snake_case: {"rampRate": 10} -> ramp_rate=10
```

### 系統管理

#### ModeManager

模式註冊與優先權切換：

```python
from csp_lib.controller import ModeManager, ModePriority

manager = ModeManager(on_strategy_change=handle_change)

# Register modes
manager.register("schedule", schedule_strategy, ModePriority.SCHEDULE)  # 10
manager.register("manual", pq_strategy, ModePriority.MANUAL)           # 50
manager.register("protection", stop_strategy, ModePriority.PROTECTION) # 100

# Base mode
await manager.set_base_mode("schedule")

# Override stack (highest priority wins)
await manager.push_override("protection")
# -> effective strategy = stop_strategy
await manager.pop_override("protection")
# -> effective strategy = schedule_strategy

# Multi base mode
await manager.add_base_mode("pq")
await manager.add_base_mode("qv")
# -> effective_strategy returns None (use CascadingStrategy for multi-mode)
```

| ModePriority | 值 | 說明 |
|-------------|-----|------|
| `SCHEDULE` | 10 | 排程模式 |
| `MANUAL` | 50 | 手動模式 |
| `PROTECTION` | 100 | 保護模式 |

#### ProtectionGuard

保護規則鏈，鏈式套用所有規則：

```python
from csp_lib.controller import (
    ProtectionGuard, SOCProtection, SOCProtectionConfig,
    ReversePowerProtection, SystemAlarmProtection,
)

guard = ProtectionGuard(rules=[
    SOCProtection(SOCProtectionConfig(
        soc_high=95,      # Prohibit charging above 95%
        soc_low=5,        # Prohibit discharging below 5%
        warning_band=5,   # Gradual limiting in warning zone
    )),
    ReversePowerProtection(threshold=0),  # No reverse power
    SystemAlarmProtection(),               # Force P=0, Q=0 on system alarm
])

result = guard.apply(command, context)
# result.protected_command   - modified command
# result.was_modified        - whether command was changed
# result.triggered_rules     - list of triggered rule names
```

| 保護規則 | 說明 | 資料來源 |
|---------|------|---------|
| `SOCProtection` | SOC 高限禁充、低限禁放、警戒區漸進限制 | `context.soc` |
| `ReversePowerProtection` | 表後逆送保護 | `context.extra["meter_power"]` |
| `SystemAlarmProtection` | 系統告警強制停機 | `context.extra["system_alarm"]` |

#### CascadingStrategy

多策略級聯功率分配（delta-based clamping）：

```python
from csp_lib.controller import CascadingStrategy, CapacityConfig

cascading = CascadingStrategy(
    layers=[pq_strategy, qv_strategy],
    capacity=CapacityConfig(s_max_kva=1000),
)
# Layer 1 (PQ): P=600kW
# Layer 2 (QV): wants Q=900kVar
# S = sqrt(600^2 + 900^2) = 1082 > 1000
# -> Only scales QV's delta Q, preserves PQ's P
```

### PVDataService

PV 功率資料服務，為 PVSmooth 策略提供歷史資料：

```python
from csp_lib.controller import PVDataService

pv_service = PVDataService(max_history=300)
pv_service.append(500.0)        # Add data point
avg = pv_service.get_average()  # Get average
latest = pv_service.get_latest() # Get latest valid data
```

### GridControllerProtocol

控制器標準協議介面：

```python
from csp_lib.controller import GridControllerProtocol, GridControllerBase
```

---

## Manager 模組 (`csp_lib.manager`)

### DeviceEventSubscriber

所有 Manager 的基底類別，提供事件訂閱框架：

```python
from csp_lib.manager import DeviceEventSubscriber
```

### DeviceManager

設備讀取循環管理，支援 standalone 與 group 模式：

```python
from csp_lib.manager import DeviceManager, DeviceGroup

# Standalone
manager = DeviceManager(device)

# Group mode
group = DeviceGroup(devices=[device1, device2, device3])
manager = DeviceManager(group)

async with manager:
    ...  # Auto manages device lifecycle
```

### AlarmPersistenceManager

告警持久化管理（MongoDB + Redis pub/sub）：

```python
from csp_lib.manager import AlarmPersistenceManager, MongoAlarmRepository

repo = MongoAlarmRepository(db)
manager = AlarmPersistenceManager(
    device=device,
    repository=repo,
    redis_client=redis,
    dispatcher=notification_dispatcher,  # Optional
)
```

| AlarmStatus | 說明 |
|------------|------|
| `ACTIVE` | 告警啟用中 |
| `RESOLVED` | 告警已解除 |

### WriteCommandManager

外部命令路由（Redis → 設備寫入）：

```python
from csp_lib.manager import WriteCommandManager, RedisCommandAdapter

adapter = RedisCommandAdapter(redis_client, channel="commands")
manager = WriteCommandManager(device=device, adapter=adapter)
```

### DataUploadManager

批次資料上傳至 MongoDB：

```python
from csp_lib.manager import DataUploadManager

manager = DataUploadManager(device=device, uploader=batch_uploader)
```

### StateSyncManager

Redis 即時狀態同步：

```python
from csp_lib.manager import StateSyncManager

manager = StateSyncManager(device=device, redis_client=redis)
```

### UnifiedDeviceManager

統一管理入口，整合所有 Manager：

```python
from csp_lib.manager import UnifiedDeviceManager, UnifiedConfig

config = UnifiedConfig(
    enable_alarm=True,
    enable_command=True,
    enable_data_upload=True,
    enable_state_sync=True,
)
unified = UnifiedDeviceManager(device=device, config=config, ...)
async with unified:
    ...
```

---

## Integration 模組 (`csp_lib.integration`)

橋接 Equipment 與 Controller 的整合層。

### DeviceRegistry

Trait-based 設備查詢索引：

```python
from csp_lib.integration import DeviceRegistry

registry = DeviceRegistry()
registry.register(device, traits=["pcs", "battery"])
registry.add_trait("inverter_001", "grid_forming")

# Query
device = registry.get("inverter_001")
pcs_devices = registry.get_by_trait("pcs")                    # All PCS devices
responsive = registry.get_by_trait("pcs", responsive_only=True) # Only responsive
```

### 映射 Schema

#### ContextMapping

設備值 → StrategyContext：

```python
from csp_lib.integration import ContextMapping, AggregateFunc

# Single device mode
ContextMapping(
    point_name="soc",
    context_field="soc",  # Maps to context.soc
    device_id="bms_001",
)

# Trait mode with aggregation
ContextMapping(
    point_name="power",
    context_field="extra.meter_power",  # Maps to context.extra["meter_power"]
    trait="meter",
    aggregate=AggregateFunc.SUM,
    default=0.0,
)
```

| AggregateFunc | 說明 |
|--------------|------|
| `AVERAGE` | 平均值 |
| `SUM` | 加總 |
| `MIN` | 最小值 |
| `MAX` | 最大值 |
| `FIRST` | 取第一台設備的值 |

#### CommandMapping

Command → 設備寫入：

```python
from csp_lib.integration import CommandMapping

CommandMapping(
    command_field="p_target",
    point_name="p_setpoint",
    trait="pcs",
    transform=lambda p: p / num_pcs,  # Split power evenly
)
```

#### DataFeedMapping

設備值 → PVDataService：

```python
from csp_lib.integration import DataFeedMapping

DataFeedMapping(
    point_name="pv_power",
    trait="solar",
)
```

### GridControlLoop

完整控制迴圈編排器，繼承 `AsyncLifecycleMixin`：

```python
from csp_lib.integration import GridControlLoop, GridControlLoopConfig

config = GridControlLoopConfig(
    context_mappings=[...],
    command_mappings=[...],
    system_base=SystemBase(p_base=1000, q_base=500),
    data_feed_mapping=DataFeedMapping(point_name="pv_power", trait="solar"),
    pv_max_history=300,
)

loop = GridControlLoop(registry, config)
await loop.set_strategy(strategy)

async with loop:
    # Auto runs: ContextBuilder → StrategyExecutor → CommandRouter
    await asyncio.sleep(3600)
```

### SystemController

進階系統控制器，整合 ModeManager + ProtectionGuard：

```python
from csp_lib.integration import SystemController, SystemControllerConfig
from csp_lib.controller import ModePriority, SOCProtection

config = SystemControllerConfig(
    context_mappings=[...],
    command_mappings=[...],
    system_base=SystemBase(p_base=1000, q_base=500),
    protection_rules=[SOCProtection(), ReversePowerProtection()],
    auto_stop_on_alarm=True,
    capacity_kva=1000,  # Enable CascadingStrategy for multi base mode
)

controller = SystemController(registry, config)

# Register modes
controller.register_mode("schedule", schedule_strategy, ModePriority.SCHEDULE)
controller.register_mode("manual", pq_strategy, ModePriority.MANUAL)

# Set mode
await controller.set_base_mode("schedule")

async with controller:
    # Full control loop with:
    #   ContextBuilder → StrategyContext (+ system_alarm injection)
    #   StrategyExecutor (strategy from ModeManager)
    #   Command → ProtectionGuard → CommandRouter
    await asyncio.sleep(3600)
```

內部流程：

```
ContextBuilder.build() → StrategyContext (inject system_alarm)
       ↓
StrategyExecutor (strategy decided by ModeManager)
       ↓
Command (raw) → ProtectionGuard.apply() → Command (protected)
       ↓
CommandRouter.route() → Device writes
```

---

## MongoDB 模組 (`csp_lib.mongo`)

需安裝：`pip install csp0924_lib[mongo]`

### MongoConfig

```python
from csp_lib.mongo import MongoConfig, create_mongo_client

# Standalone
config = MongoConfig(host="localhost", port=27017)

# Standalone + X.509
config = MongoConfig(
    host="mongo.example.com",
    port=27017,
    tls=True,
    tls_cert_key_file="/path/to/client.pem",
    tls_ca_file="/path/to/ca.crt",
    auth_mechanism="MONGODB-X509",
)

# Replica Set
config = MongoConfig(
    replica_hosts=("rs1:27017", "rs2:27017", "rs3:27017"),
    replica_set="myReplicaSet",
    username="user",
    password="password",
)

client = create_mongo_client(config)
db = client["my_database"]
```

| 參數 | 預設 | 說明 |
|------|------|------|
| `host` | `"localhost"` | 主機位址 (Standalone) |
| `port` | `27017` | 連接埠 (Standalone) |
| `replica_hosts` | `None` | 副本集主機列表 |
| `replica_set` | `None` | 副本集名稱 |
| `username` / `password` | `None` | 驗證資訊 |
| `auth_source` | `"admin"` | 驗證資料庫 |
| `auth_mechanism` | `None` | 驗證機制 (e.g. `"MONGODB-X509"`) |
| `tls` | `False` | 啟用 TLS |
| `tls_cert_key_file` | `None` | 客戶端憑證 |
| `tls_ca_file` | `None` | CA 憑證 |
| `direct_connection` | `True` | 直連模式 |

### MongoBatchUploader

批次上傳機制：

```python
from csp_lib.mongo import MongoBatchUploader, UploaderConfig

config = UploaderConfig(
    flush_interval=5,           # Flush every 5 seconds
    batch_size_threshold=100,   # Or when 100 docs accumulated
    max_queue_size=10000,       # Queue limit
    max_retry_count=3,          # Max retries per batch
)

uploader = MongoBatchUploader(db=db, config=config)
async with uploader:
    await uploader.enqueue("collection_name", {"key": "value"})
```

---

## Redis 模組 (`csp_lib.redis`)

需安裝：`pip install csp0924_lib[redis]`

### RedisConfig

```python
from csp_lib.redis import RedisConfig, TLSConfig

# Standalone
config = RedisConfig(host="localhost", port=6379, password="secret")

# Sentinel
config = RedisConfig(
    sentinels=(("sentinel1", 26379), ("sentinel2", 26379)),
    sentinel_master="mymaster",
    password="redis_password",
    sentinel_password="sentinel_password",
)

# TLS
config = RedisConfig(
    host="redis.example.com",
    tls_config=TLSConfig(
        ca_certs="/path/to/ca.crt",
        certfile="/path/to/client.crt",  # For mTLS
        keyfile="/path/to/client.key",
    ),
)
```

### RedisClient

```python
from csp_lib.redis import RedisClient

client = RedisClient(config)
await client.connect()

# Hash operations
await client.hset("device:001", "voltage", "220.5")
value = await client.hget("device:001", "voltage")
all_fields = await client.hgetall("device:001")

# String operations
await client.set("key", "value", ex=60)
value = await client.get("key")

# Pub/Sub
await client.publish("channel", "message")
async for message in client.subscribe("channel"):
    print(message)

# Key operations
await client.delete("key")
await client.expire("key", 300)
exists = await client.exists("key")

await client.disconnect()
```

---

## Cluster 模組 (`csp_lib.cluster`)

需安裝：`pip install csp0924_lib[cluster]`

分散式高可用控制，透過 etcd leader election 實現多實例 HA。

### 配置

```python
from csp_lib.cluster import ClusterConfig, EtcdConfig

config = ClusterConfig(
    instance_id="node-01",
    etcd=EtcdConfig(
        endpoints=["etcd1:2379", "etcd2:2379"],
        username="root",
        password="secret",
    ),
    namespace="production",
    election_key="/csp/cluster/election",
    lease_ttl=10,
    state_publish_interval=1.0,
    state_ttl=30,
    failover_grace_period=2.0,
    device_ids=["pcs_001", "bms_001"],
)
```

### 核心元件

| 元件 | 說明 |
|------|------|
| `LeaderElector` | etcd lease-based leader election |
| `ClusterStatePublisher` | Leader 將設備狀態發佈到 Redis |
| `ClusterStateSubscriber` | Follower 從 Redis 訂閱設備狀態 |
| `VirtualContextBuilder` | 從 Redis 資料建構 StrategyContext |
| `ClusterController` | 中央編排器 (Leader/Follower 自動切換) |

### Leader/Follower 流程

```
Leader:
  LocalDevice.read() → Redis.publish(state)
  ContextBuilder(local) → StrategyExecutor → CommandRouter → Device.write()

Follower:
  Redis.subscribe(state) → VirtualContextBuilder
  VirtualContextBuilder → StrategyExecutor → (no write, shadow mode)

Failover:
  Leader down → etcd lease expires → new election
  New leader: grace period → start controlling
```

### Redis Key Schema

```
cluster:{namespace}:state          # Cluster state hash
cluster:{namespace}:device:{id}    # Device state hash
channel:cluster:{namespace}:state  # State change pub/sub channel
```

### 使用範例

```python
from csp_lib.cluster import ClusterController

controller = ClusterController(
    config=cluster_config,
    redis_client=redis,
    registry=registry,
    control_loop_config=loop_config,
)

async with controller:
    # Automatically handles:
    # - etcd leader election
    # - Leader: local device control + state publishing
    # - Follower: state subscription + shadow execution
    # - Failover with grace period
    await asyncio.Event().wait()
```

---

## Monitor 模組 (`csp_lib.monitor`)

需安裝：`pip install csp0924_lib[monitor]`

### 配置

```python
from csp_lib.monitor import MonitorConfig, MetricThresholds

config = MonitorConfig(
    interval_seconds=5.0,
    thresholds=MetricThresholds(
        cpu_percent=90.0,
        ram_percent=85.0,
        disk_percent=95.0,
    ),
    enable_cpu=True,
    enable_ram=True,
    enable_disk=True,
    enable_network=True,
    enable_module_health=True,
    redis_key_prefix="system",
    metrics_ttl=30,
    hysteresis_activate=3,
    hysteresis_clear=3,
    disk_paths=("/",),
)
```

### 核心元件

| 元件 | 說明 |
|------|------|
| `SystemMetricsCollector` | 收集 CPU/RAM/Disk/Network 指標 |
| `SystemMetrics` | 系統指標資料結構 |
| `SystemAlarmEvaluator` | 依閾值產生系統告警 |
| `ModuleHealthCollector` | 模組健康檢查 |
| `RedisMonitorPublisher` | 將指標發佈到 Redis |
| `SystemMonitor` | 主要監控器（整合以上元件） |

### 使用範例

```python
from csp_lib.monitor import SystemMonitor

monitor = SystemMonitor(
    config=config,
    redis_client=redis,
    health_modules=[device1, device2],  # HealthCheckable objects
)

async with monitor:
    await asyncio.Event().wait()
```

---

## Notification 模組 (`csp_lib.notification`)

### 核心元件

```python
from csp_lib.notification import (
    Notification,
    NotificationEvent,
    NotificationChannel,
    NotificationDispatcher,
)
```

| 元件 | 說明 |
|------|------|
| `Notification` | 通知資料（title, body, level, device_id, alarm_key, event, occurred_at） |
| `NotificationEvent` | `TRIGGERED` / `RESOLVED` |
| `NotificationChannel` | 通知通道 ABC |
| `NotificationDispatcher` | 多通道分發器 |

### 實作自訂通道

```python
from csp_lib.notification import NotificationChannel, Notification

class LineChannel(NotificationChannel):
    @property
    def name(self) -> str:
        return "line"

    async def send(self, notification: Notification) -> None:
        # Send via LINE Notify API
        ...

class TelegramChannel(NotificationChannel):
    @property
    def name(self) -> str:
        return "telegram"

    async def send(self, notification: Notification) -> None:
        # Send via Telegram Bot API
        ...

# Use with dispatcher
dispatcher = NotificationDispatcher(channels=[LineChannel(), TelegramChannel()])

# Integrate with AlarmPersistenceManager
alarm_manager = AlarmPersistenceManager(
    device=device,
    repository=repo,
    redis_client=redis,
    dispatcher=dispatcher,
)
```

---

## Modbus Server 模組 (`csp_lib.modbus_server`)

模擬測試用 Modbus TCP 伺服器，用於整合測試與控制機制驗證。

### 配置

```python
from csp_lib.modbus_server import (
    SimulatedPoint, SimulatedDeviceConfig, ServerConfig,
    AlarmPointConfig, AlarmResetMode, ControllabilityMode,
)
from csp_lib.modbus import Float32, UInt16

# Define simulated points
points = (
    SimulatedPoint(name="power", address=0, data_type=Float32(), writable=True),
    SimulatedPoint(name="status", address=2, data_type=UInt16(), initial_value=1),
)

# Device config
device_config = SimulatedDeviceConfig(
    device_id="sim_pcs",
    unit_id=1,
    points=points,
    update_interval=1.0,
)

# Server config
server_config = ServerConfig(host="0.0.0.0", port=5020)
```

### 內建模擬器

| 模擬器 | 說明 |
|--------|------|
| `SolarSimulator` | 太陽能發電模擬（日照曲線） |
| `GeneratorSimulator` | 發電機模擬 |
| `LoadSimulator` | 負載模擬 |
| `PCSSimulator` | 儲能系統 PCS 模擬 |
| `PowerMeterSimulator` | 電表模擬 |

### 行為模組

| 行為 | 說明 |
|------|------|
| `AlarmBehavior` | 告警觸發/重置模擬 |
| `NoiseBehavior` | 隨機雜訊 |
| `RampBehavior` | 線性漸變 |
| `CurveBehavior` | 曲線跟隨 |

### MicrogridSimulator

功率平衡協調器：

```python
from csp_lib.modbus_server import MicrogridSimulator, MicrogridConfig

microgrid = MicrogridSimulator(MicrogridConfig(...))
```

### SimulationServer

完整伺服器：

```python
from csp_lib.modbus_server import SimulationServer

server = SimulationServer(
    config=server_config,
    simulators=[solar_sim, pcs_sim, meter_sim],
)

async with server:
    await asyncio.Event().wait()
```

---

## 建置與開發

### 開發環境設定

```bash
# Install with dev dependencies
uv sync --all-groups --all-extras
```

### 測試

```bash
uv run pytest tests/ -v                           # Run all tests
uv run pytest tests/equipment/test_core_point.py   # Single test file
uv run pytest -k "test_scale_transform"            # Pattern matching
```

### Linting / Formatting

```bash
uv run ruff check .          # Lint
uv run ruff check --fix .    # Lint with auto-fix
uv run ruff format .         # Format
uv run mypy csp_lib/         # Type check
```

### Cython 建置

詳見 [BUILDING.md](BUILDING.md)。

```bash
python build_wheel.py              # Build Cython-compiled wheel
python build_wheel.py clean        # Clean build artifacts
SKIP_CYTHON=1 pip install -e .     # Editable install without Cython
```

---

## 版本

目前版本：`0.3.3`

詳見 [CHANGELOG.md](CHANGELOG.md)。
