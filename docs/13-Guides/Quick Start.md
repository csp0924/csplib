---
tags:
  - type/guide
  - status/complete
created: 2026-02-17
---

# 快速入門

本指南包含三個程式碼範例，讓你快速上手 csp_lib 的核心功能。

## 安裝

```bash
# 基本安裝
pip install csp0924_lib

# 按需安裝
pip install csp0924_lib[modbus]     # Modbus 通訊
pip install csp0924_lib[mongo]      # MongoDB 批次上傳
pip install csp0924_lib[redis]      # Redis 客戶端
pip install csp0924_lib[all]        # 所有功能
```

---

## 基本設備讀寫

使用 [[AsyncModbusDevice]] 搭配 [[DeviceConfig]]、[[ReadPoint]]、[[WritePoint]] 進行 Modbus 設備的非同步讀寫操作。

```python
import asyncio
from csp_lib.modbus import PymodbusTcpClient, ModbusTcpConfig, UInt16, Float32
from csp_lib.equipment.core import ReadPoint, WritePoint, pipeline, ScaleTransform, RoundTransform
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig

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
        device.on("value_change", lambda p: print(f"{p.point_name}: {p.new_value}"))
        values = await device.read_all()
        print(f"Voltage: {values['voltage']}V")
        result = await device.write("power_limit", 5000)
        print(f"Write: {result.status}")

asyncio.run(main())
```

> [!tip] `async with device` 會自動執行 connect + start，結束時自動 stop + disconnect。

---

## 控制策略

使用 [[PQModeStrategy]] 搭配 [[StrategyExecutor]] 執行固定 P/Q 輸出策略。

```python
from csp_lib.controller import (
    PQModeConfig, PQModeStrategy,
    StrategyExecutor, StrategyContext,
)

config = PQModeConfig(p=100, q=50)
strategy = PQModeStrategy(config)

executor = StrategyExecutor(context_provider=lambda: StrategyContext())
await executor.set_strategy(strategy)
await executor.run()  # 週期性執行迴圈
```

---

## 完整系統整合

使用 [[GridControlLoop]] 搭配 [[DeviceRegistry]] 與映射 Schema，將設備與控制策略整合為完整控制迴圈。

```python
from csp_lib.integration import (
    DeviceRegistry, GridControlLoop, GridControlLoopConfig,
    ContextMapping, CommandMapping, DataFeedMapping,
)
from csp_lib.controller import PQModeStrategy, PQModeConfig, SystemBase

# 註冊設備
registry = DeviceRegistry()
registry.register(meter, traits=["meter"])
registry.register(pcs, traits=["pcs"])

# 設定控制迴圈
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

# 執行
loop = GridControlLoop(registry, config)
await loop.set_strategy(PQModeStrategy(PQModeConfig(p=200)))
async with loop:
    await asyncio.sleep(3600)  # 執行 1 小時
```

---

## 下一步

- [[Device Setup]] - 深入了解設備設定
- [[Control Strategy Setup]] - 探索所有控制策略
- [[Full System Integration]] - 完整系統整合教學
