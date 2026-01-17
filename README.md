# CSP Library

CSP Common Library 是一個模組化的 Python 工具集，專為能源管理系統與工業設備通訊設計。提供 Modbus 設備抽象、告警管理、資料處理等功能。

## 安裝

```bash
# 基本安裝
pip install csp_lib

# 按需安裝特定功能
pip install csp_lib[modbus]  # Modbus 通訊
pip install csp_lib[mongo]   # MongoDB 批次上傳
pip install csp_lib[all]     # 所有功能
```

## 快速入門

```python
import asyncio
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig, UInt16, Float32
from csp_lib.equipment import (
    AsyncModbusDevice,
    DeviceConfig,
    ReadPoint,
    WritePoint,
    pipeline,
    ScaleTransform,
    RoundTransform,
)

# 1. 定義點位
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

# 2. 建立設備
config = DeviceConfig(device_id="inverter_001", unit_id=1, read_interval=1.0)
client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100", port=502))
device = AsyncModbusDevice(
    config=config,
    client=client,
    always_points=read_points,
    write_points=write_points,
)

# 3. 使用設備
async def main():
    async with device:
        # 註冊事件
        device.on("value_change", lambda p: print(f"{p.point_name}: {p.new_value}"))

        # 讀取
        values = await device.read_all()
        print(f"Voltage: {values['voltage']}V")

        # 寫入
        result = await device.write("power_limit", 5000)
        print(f"Write: {result.status}")

asyncio.run(main())
```

---

## 核心模組：AsyncModbusDevice

`AsyncModbusDevice` 是程式庫的核心類別，提供完整的非同步 Modbus 設備抽象。

### 設計特點

- **定期讀取循環**：自動執行週期性資料讀取
- **告警狀態管理**：內建遲滯機制避免邊緣觸發
- **事件驅動通知**：支援值變化、連線狀態、告警等事件
- **動態點位排程**：支援固定讀取與輪流讀取模式
- **設備寫入管理**：驗證與寫後讀回確認

### 建構參數

```python
AsyncModbusDevice(
    config: DeviceConfig,                      # 設備設定
    client: AsyncModbusClientBase,             # Modbus 客戶端
    always_points: Sequence[ReadPoint] = (),   # 每次都讀取的點位
    rotating_points: Sequence[Sequence[ReadPoint]] = (),  # 輪流讀取的點位
    write_points: Sequence[WritePoint] = (),   # 可寫入點位
    alarm_evaluators: Sequence[AlarmEvaluator] = (),  # 告警評估器
)
```

### 生命週期管理

```python
# 方式一：Context Manager（推薦）
async with device:
    # 自動 connect + start，結束時 stop + disconnect
    ...

# 方式二：手動管理
await device.connect()   # 連線
await device.start()     # 啟動讀取循環
...
await device.stop()      # 停止讀取循環
await device.disconnect() # 斷線
```

### 狀態屬性

| 屬性 | 說明 |
|-----|------|
| `is_connected` | Socket 層級連線狀態 |
| `is_responsive` | 設備通訊回應狀態 |
| `is_healthy` | 健康狀態 (connected + responsive + 無保護告警) |
| `is_protected` | 是否有保護告警 |
| `is_running` | 讀取循環是否運行中 |
| `latest_values` | 最新讀取值字典 |
| `active_alarms` | 目前啟用的告警列表 |

### 讀寫操作

```python
# 讀取所有點位
values = await device.read_all()
# -> {"voltage": 220.5, "temperature": 25.3}

# 寫入（可選驗證讀回）
result = await device.write("power_limit", 5000, verify=True)
if result.status == WriteStatus.SUCCESS:
    print("寫入成功")
```

### 事件系統

支援的事件與對應 Payload：

| 事件名稱 | Payload | 說明 |
|---------|---------|-----|
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
# 註冊事件處理器
cancel = device.on("value_change", async_handler)
cancel()  # 取消訂閱
```

### 告警管理

```python
# 取得啟用中的告警
for alarm in device.active_alarms:
    print(f"{alarm.code}: {alarm.definition.name}")

# 手動清除告警
await device.clear_alarm("OVER_TEMP")
```

---

## Device 相關模組

### DeviceConfig

設備設定類別：

```python
from csp_lib.equipment import DeviceConfig

config = DeviceConfig(
    device_id="inverter_001",   # 設備唯一識別碼
    unit_id=1,                   # Modbus 設備位址 (0-255)
    address_offset=0,            # 位址偏移 (PLC 1-based 時設為 1)
    read_interval=1.0,           # 讀取間隔（秒）
    disconnect_threshold=5,      # 連續失敗次數閾值
    max_concurrent_reads=1,      # 最大並行讀取數
)
```

### 事件定義 (events.py)

`DeviceEventEmitter` 使用 `asyncio.Queue` 進行非阻塞事件處理：

- `emit(event, payload)`: 非阻塞發送
- `emit_await(event, payload)`: 等待處理完成

---

## Core 模組

### 點位定義 (point.py)

```python
from csp_lib.equipment import ReadPoint, WritePoint, RangeValidator
from csp_lib.modbus import UInt16, Float32, FunctionCode

# 讀取點位
ReadPoint(
    name="voltage",
    address=0,
    data_type=Float32(),
    function_code=FunctionCode.READ_HOLDING_REGISTERS,  # 預設值
    pipeline=None,        # 資料處理管線
    read_group="",        # 讀取分組名稱
)

# 寫入點位
WritePoint(
    name="power_limit",
    address=100,
    data_type=UInt16(),
    function_code=FunctionCode.WRITE_MULTIPLE_REGISTERS,  # 預設值
    validator=RangeValidator(min_value=0, max_value=10000),
)
```

#### 內建驗證器

- `RangeValidator(min_value, max_value)`: 範圍驗證
- `EnumValidator(allowed_values)`: 枚舉驗證
- `CompositeValidator(validators)`: 組合驗證

### 資料轉換 (transform.py)

```python
from csp_lib.equipment import (
    ScaleTransform,        # 縮放: value * magnitude + offset
    RoundTransform,        # 四捨五入
    EnumMapTransform,      # 數值 → 枚舉映射
    ClampTransform,        # 值域限制
    BoolTransform,         # 布林轉換
    BitExtractTransform,   # 位元欄位提取
    ByteExtractTransform,  # 位元組提取
    MultiFieldExtractTransform,  # 多位元欄位提取
)

# 範例：溫度轉換 (raw * 0.1 - 40)
temp_transform = ScaleTransform(magnitude=0.1, offset=-40)

# 範例：狀態映射
status_transform = EnumMapTransform(
    mapping={0: "STOP", 1: "RUN", 2: "FAULT"},
    default="UNKNOWN",
)

# 範例：位元欄位提取
bit_transform = BitExtractTransform(bit_offset=8, bit_length=4)
```

### 處理管線 (pipeline.py)

串聯多個轉換步驟：

```python
from csp_lib.equipment import pipeline, ScaleTransform, RoundTransform

temp_pipeline = pipeline(
    ScaleTransform(0.1, -40),
    RoundTransform(1),
)
# 250 -> (250 * 0.1 - 40) = -15.0 -> -15.0
```

---

## Transport 模組

### 點位分組 (base.py)

`PointGrouper` 自動合併相鄰點位以減少請求次數：

```python
from csp_lib.equipment.transport import PointGrouper, ReadGroup

grouper = PointGrouper()
groups: list[ReadGroup] = grouper.group(points)
# 相鄰點位會被合併成單一 ReadGroup
```

### 群組讀取 (reader.py)

```python
from csp_lib.equipment.transport import GroupReader

reader = GroupReader(client=client, address_offset=0)
data = await reader.read_many(groups)
# -> {"voltage": 220.5, "current": 10.2, ...}
```

### 驗證寫入 (writer.py)

```python
from csp_lib.equipment.transport import ValidatedWriter, WriteStatus

writer = ValidatedWriter(client=client)
result = await writer.write(point, value, verify=True)

if result.status == WriteStatus.SUCCESS:
    print("成功")
elif result.status == WriteStatus.VALIDATION_FAILED:
    print(f"驗證失敗: {result.error_message}")
elif result.status == WriteStatus.VERIFICATION_FAILED:
    print(f"讀回不匹配: {result.error_message}")
```

### 讀取排程 (scheduler.py)

支援固定讀取與輪流讀取模式：

```python
from csp_lib.equipment.transport import ReadScheduler

scheduler = ReadScheduler(
    always_groups=grouper.group(core_points),      # 每次都讀
    rotating_groups=[
        grouper.group(sbms1_points),
        grouper.group(sbms2_points),
        grouper.group(sbms3_points),
    ],
)

# 第1次: always + rotating[0]
# 第2次: always + rotating[1]
# 第3次: always + rotating[2]
# 第4次: always + rotating[0] (循環)
groups = scheduler.get_next_groups()
```

---

## Alarm 模組

### 告警定義 (definition.py)

```python
from csp_lib.equipment.alarm import (
    AlarmDefinition,
    AlarmLevel,
    HysteresisConfig,
)

alarm = AlarmDefinition(
    code="OVER_TEMP",
    name="溫度過高",
    level=AlarmLevel.WARNING,
    hysteresis=HysteresisConfig(
        activate_threshold=3,  # 連續 3 次觸發才啟用
        clear_threshold=5,     # 連續 5 次解除才清除
    ),
)
```

### 告警評估器 (evaluator.py)

```python
from csp_lib.equipment.alarm import (
    BitMaskAlarmEvaluator,
    ThresholdAlarmEvaluator,
    TableAlarmEvaluator,
    ThresholdCondition,
    Operator,
)

# 位元遮罩告警
bitmask_eval = BitMaskAlarmEvaluator(
    _point_name="fault_code",
    bit_alarms={
        0: AlarmDefinition("OV", "過壓"),
        1: AlarmDefinition("UV", "欠壓"),
        2: AlarmDefinition("OC", "過流"),
    },
)

# 閾值告警
threshold_eval = ThresholdAlarmEvaluator(
    _point_name="temperature",
    conditions=[
        ThresholdCondition(
            alarm=AlarmDefinition("HIGH_TEMP", "溫度過高"),
            operator=Operator.GT,
            value=45.0,
        ),
    ],
)

# 查表告警
table_eval = TableAlarmEvaluator(
    _point_name="status",
    table={
        3: AlarmDefinition("FAULT", "設備故障"),
        4: AlarmDefinition("EMERGENCY", "緊急停機"),
    },
)
```

### 狀態管理 (state.py)

`AlarmStateManager` 內部管理告警狀態，支援遲滯機制。由 `AsyncModbusDevice` 自動使用。

---

## Modbus 模組

### 資料類型

```python
from csp_lib.modbus import (
    # 整數
    Int16, UInt16,
    Int32, UInt32,
    Int64, UInt64,
    # 浮點數
    Float32, Float64,
    # 動態長度
    DynamicInt, DynamicUInt,
    # 字串
    ModbusString,
)

# 使用範例
data_type = Float32()
registers = data_type.encode(123.45)  # -> [0x42F6, 0xE666]
value = data_type.decode(registers)   # -> 123.45
```

### 客戶端

```python
from csp_lib.modbus import (
    PymodbusTcpClient,
    PymodbusRtuClient,
    SharedPymodbusTcpClient,
    ModbusTcpConfig,
    ModbusRtuConfig,
)

# TCP
tcp_client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100", port=502))

# RTU
rtu_client = PymodbusRtuClient(ModbusRtuConfig(port="COM1", baudrate=9600))

# 共享 TCP（多設備共用同一連線）
shared_client = SharedPymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100"))
```

---

## 架構圖

![csp_lib](./.github/equipment.png)

---

## 版本

目前版本：`0.3.0`
