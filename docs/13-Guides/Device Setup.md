---
tags:
  - type/guide
  - layer/equipment
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# 設備設定指南

本指南說明如何設定並操作一台 Modbus 設備，包括定義點位、建立客戶端、註冊事件與使用 context manager。

## 步驟總覽

1. 定義讀取/寫入點位
2. 建立設備配置
3. 建立 Modbus 客戶端
4. 建立設備實例
5. 註冊事件處理器
6. 使用 context manager 運行設備

---

## 1. 定義點位

使用 [[ReadPoint]] 與 [[WritePoint]] 定義設備的資料點位。

```python
from csp_lib.equipment.core import ReadPoint, WritePoint, pipeline
from csp_lib.equipment.core import ScaleTransform, RoundTransform, ClampTransform
from csp_lib.modbus import Float32, UInt16, FunctionCode

# 讀取點位
read_points = [
    ReadPoint(name="voltage", address=0, data_type=Float32()),
    ReadPoint(
        name="temperature",
        address=2,
        data_type=UInt16(),
        pipeline=pipeline(ScaleTransform(0.1, -40), RoundTransform(1)),
    ),
    ReadPoint(
        name="power",
        address=4,
        data_type=Float32(),
        function_code=FunctionCode.READ_INPUT_REGISTERS,
    ),
]

# 寫入點位（可搭配驗證器）
from csp_lib.equipment.core import RangeValidator

write_points = [
    WritePoint(
        name="power_limit",
        address=100,
        data_type=UInt16(),
        validator=RangeValidator(min_value=0, max_value=10000),
    ),
]
```

### 轉換管線

使用 [[ProcessingPipeline]] 串聯多個 [[ScaleTransform]]、[[RoundTransform]] 等轉換步驟：

```python
from csp_lib.equipment.core import pipeline, ScaleTransform, RoundTransform

temp_pipeline = pipeline(
    ScaleTransform(0.1, -40),  # value * 0.1 - 40
    RoundTransform(1),         # 四捨五入到 1 位小數
)
# 250 -> 25.0 -> -15.0 -> -15.0
```

---

## 2. 建立設備配置

使用 [[DeviceConfig]] 設定設備參數：

```python
from csp_lib.equipment.device import DeviceConfig

config = DeviceConfig(
    device_id="inverter_001",
    unit_id=1,
    address_offset=0,        # PLC 1-based 時設為 1
    read_interval=1.0,       # 讀取間隔（秒）
    reconnect_interval=5.0,  # 重連間隔（秒）
    disconnect_threshold=5,  # 連續失敗次數觸發斷線
    max_concurrent_reads=1,  # 最大併發讀取數（0=無限）
)
```

---

## 3. 建立 Modbus 客戶端

選擇適合的客戶端類別：

| 客戶端 | 使用時機 |
|--------|---------|
| [[PymodbusTcpClient]] | 一對一 TCP 連線 |
| [[PymodbusRtuClient]] | Serial port (RTU) 連線 |
| [[SharedPymodbusTcpClient]] | 多設備共用同一 TCP 連線 |

```python
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig

client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100", port=502))
```

---

## 4. 建立設備實例

使用 [[AsyncModbusDevice]] 建立設備：

```python
from csp_lib.equipment.device import AsyncModbusDevice

device = AsyncModbusDevice(
    config=config,
    client=client,
    always_points=read_points,
    rotating_points=[group_a, group_b],  # 可選：輪替讀取群組
    write_points=write_points,
    alarm_evaluators=[bitmask, threshold],  # 可選：告警評估器
)
```

---

## 5. 註冊事件處理器

使用 [[DeviceEventEmitter]] 的事件系統註冊回呼：

```python
# 值變化事件
device.on("value_change", lambda p: print(f"{p.point_name}: {p.new_value}"))

# 連線事件
device.on("connected", lambda p: print(f"已連線: {p.device_id}"))
device.on("disconnected", lambda p: print(f"已斷線: {p.device_id}"))

# 告警事件
device.on("alarm_triggered", lambda p: print(f"告警觸發: {p.alarm_code}"))
device.on("alarm_cleared", lambda p: print(f"告警解除: {p.alarm_code}"))

# 取消訂閱
cancel = device.on("read_complete", handler)
cancel()  # 呼叫返回值即可取消
```

完整事件列表請見 [[All Events]]。

---

## 6. 使用 Context Manager

推薦使用 `async with` 語法管理設備生命週期：

```python
async with device:
    # 自動執行 connect() + start()
    values = await device.read_all()
    print(f"Voltage: {values['voltage']}V")

    result = await device.write("power_limit", 5000, verify=True)
    print(f"Write: {result.status}")
# 自動執行 stop() + disconnect()
```

### 手動管理生命週期

```python
await device.connect()
await device.start()
# ... 使用設備 ...
await device.stop()
await device.disconnect()
```

---

## 設備狀態屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `is_connected` | `bool` | Socket 層級連線狀態 |
| `is_responsive` | `bool` | 設備通訊回應狀態 |
| `is_healthy` | `bool` | 健康（connected + responsive + 無保護告警） |
| `is_protected` | `bool` | 是否有保護告警 |
| `is_running` | `bool` | 讀取循環是否運行中 |
| `latest_values` | `dict` | 最新讀取值字典 |
| `active_alarms` | `list` | 目前啟用的告警列表 |

---

---

## CAN 設備設定

使用 [[AsyncCANDevice]] 與 CAN Bus 設備通訊，支援被動監聽、主動控制、請求-回應三種操作模式。

> [!note] 安裝需求
> 使用 CAN 功能需安裝 `csp0924_lib[can]`。

### 步驟總覽

1. 建立 CAN 客戶端
2. 定義 TX 信號（可選，用於主動控制）
3. 定義 RX 訊框（用於接收解析）
4. 建立設備並啟動

### 1. 建立 CAN 客戶端

```python
from csp_lib.can import CANBusConfig, PythonCANClient

can_config = CANBusConfig(interface="socketcan", channel="can0", bitrate=500000)
client = PythonCANClient(can_config)
```

### 2. 定義 TX 信號（主動控制）

```python
from csp_lib.equipment.processing.can_encoder import (
    CANSignalDefinition, FrameBufferConfig,
)
from csp_lib.equipment.transport.periodic_sender import PeriodicFrameConfig

# 發送訊框：CAN ID=0x200，包含 power_target 信號
tx_signals = [
    CANSignalDefinition(
        field=...,           # 信號欄位定義（位元偏移、長度、縮放比）
        can_id=0x200,
    ),
]
tx_buffer_configs = [FrameBufferConfig(can_id=0x200)]
tx_periodic_configs = [
    PeriodicFrameConfig(can_id=0x200, interval=0.1),  # 每 100ms 發送一次
]
```

### 3. 定義 RX 訊框（接收解析）

```python
from csp_lib.equipment.device.can_device import CANRxFrameDefinition
from csp_lib.equipment.processing.can_parser import CANFrameParser

# 被動監聽：設備週期性廣播的狀態訊框
bms_parser = CANFrameParser(source_name="raw", points=[...])

rx_defs = [
    # 被動監聽（is_periodic=True）
    CANRxFrameDefinition(can_id=0x100, parser=bms_parser, is_periodic=True),
    # 請求-回應（is_periodic=False）
    CANRxFrameDefinition(
        can_id=0x200,
        parser=query_parser,
        is_periodic=False,
        request_data=b"\x01\x02",
    ),
]
```

### 4. 建立設備

```python
from csp_lib.equipment.device import DeviceConfig
from csp_lib.equipment.device.can_device import AsyncCANDevice

config = DeviceConfig(device_id="pcs_can_001", read_interval=1.0)

device = AsyncCANDevice(
    config=config,
    client=client,
    # TX（可選）
    tx_signals=tx_signals,
    tx_buffer_configs=tx_buffer_configs,
    tx_periodic_configs=tx_periodic_configs,
    # RX
    rx_frame_definitions=rx_defs,
    rx_timeout=10.0,  # 超過 10 秒未收到訊框則標記為無回應
)
```

### 5. 使用設備

```python
async with device:
    # 被動接收：背景自動更新 latest_values
    device.on("value_change", lambda p: print(f"{p.point_name}: {p.new_value}"))

    # 寫入 CAN 信號（更新 frame buffer）
    result = await device.write("power_target", 5000)
    # 立即發送（不等待定期排程）
    result = await device.write("power_target", 5000, immediate=True)

    # 讀取最新值
    print(device.latest_values)
```

### CAN 設備狀態屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `is_connected` | `bool` | CAN Bus 連線狀態 |
| `is_responsive` | `bool` | 最近是否有收到 RX 訊框 |
| `is_running` | `bool` | 是否已啟動（等同 is_connected） |
| `latest_values` | `dict` | 最新解析值字典 |
| `active_alarms` | `list` | 目前啟用的告警列表 |

> [!warning] RX Timeout
> 若超過 `rx_timeout` 秒未收到任何訊框，`is_responsive` 會被標記為 `False`，並發射 `disconnected` 事件。

---

## 相關頁面

- [[Quick Start]] - 快速入門
- [[All Events]] - 所有設備事件
- [[Control Strategy Setup]] - 控制策略設定
