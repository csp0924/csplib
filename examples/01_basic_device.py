"""
Example 01: Basic Device — 基礎設備讀寫

Demonstrates:
  - Defining ReadPoint / WritePoint with transforms and validators
  - Creating an AsyncModbusDevice with DeviceConfig
  - Connecting, reading, writing, and handling events
  - Alarm setup with BitMask and Threshold evaluators

This example uses a simulated inverter (PCS) that has:
  - Read: active_power (kW), soc (%), fault_code (bitmask)
  - Write: p_set (kW), q_set (kVar)
  - Alarms: fault_code bitmask, SOC threshold
"""

import asyncio

from csp_lib.equipment.alarm import (
    AlarmDefinition,
    AlarmEvaluator,
    AlarmLevel,
    BitMaskEvaluator,
    ThresholdEvaluator,
)
from csp_lib.equipment.core import (
    ReadPoint,
    RoundTransform,
    ScaleTransform,
    WritePoint,
    pipeline,
)
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16

# ============================================================
# Step 1: Define Read Points (設備讀取點位)
# ============================================================

# Active power: register 5000, Float32, scale ×0.1 then round to 1 decimal
active_power = ReadPoint(
    name="active_power",
    address=5000,
    data_type=Float32(),
    pipeline=pipeline(ScaleTransform(0.1), RoundTransform(1)),
    metadata=PointMetadata(unit="kW", description="Active power output"),
)

# Battery SOC: register 5034, UInt16, scale ×0.1 to get percentage
soc = ReadPoint(
    name="soc",
    address=5034,
    data_type=UInt16(),
    pipeline=pipeline(ScaleTransform(0.1)),
    metadata=PointMetadata(unit="%", description="Battery state of charge"),
)

# Fault code: register 5100, UInt16, raw bitmask
fault_code = ReadPoint(
    name="fault_code",
    address=5100,
    data_type=UInt16(),
    metadata=PointMetadata(
        description="Fault code bitmask",
        value_map={0: "Normal", 1: "Over-temperature", 2: "Over-current", 4: "DC fault"},
    ),
)

# ============================================================
# Step 2: Define Write Points (設備寫入點位)
# ============================================================

# Active power setpoint: register 6000, Float32, range -100 ~ 100 kW
p_set = WritePoint(
    name="p_set",
    address=6000,
    data_type=Float32(),
    validator=RangeValidator(min_value=-100.0, max_value=100.0),
    metadata=PointMetadata(unit="kW", description="Active power setpoint"),
)

# Reactive power setpoint: register 6002, Float32, range -50 ~ 50 kVar
q_set = WritePoint(
    name="q_set",
    address=6002,
    data_type=Float32(),
    validator=RangeValidator(min_value=-50.0, max_value=50.0),
    metadata=PointMetadata(unit="kVar", description="Reactive power setpoint"),
)

# ============================================================
# Step 3: Define Alarms (告警定義)
# ============================================================

# Bitmask alarm: check fault_code register bits
fault_evaluator = BitMaskEvaluator(
    point_name="fault_code",
    alarms=[
        AlarmDefinition(code="OVER_TEMP", level=AlarmLevel.WARNING, bit=0, description="Over-temperature"),
        AlarmDefinition(code="OVER_CURR", level=AlarmLevel.FAULT, bit=1, description="Over-current"),
        AlarmDefinition(code="DC_FAULT", level=AlarmLevel.PROTECTION, bit=2, description="DC bus fault"),
    ],
)

# Threshold alarm: SOC too low
soc_evaluator = ThresholdEvaluator(
    point_name="soc",
    alarms=[
        AlarmDefinition(code="SOC_LOW", level=AlarmLevel.WARNING, description="SOC below 10%"),
    ],
    low_threshold=10.0,
)

# ============================================================
# Step 4: Create Device (建立設備)
# ============================================================


async def main():
    # Modbus TCP client
    client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100", port=502))

    # Device configuration
    config = DeviceConfig(
        device_id="pcs_01",
        unit_id=1,
        address_offset=0,  # Some PLCs use 1-based addressing (offset=1)
        read_interval=1.0,  # Read every 1 second
        disconnect_threshold=5,  # Mark as unresponsive after 5 consecutive failures
    )

    # Create device
    device = AsyncModbusDevice(
        config=config,
        client=client,
        always_points=[active_power, soc, fault_code],
        write_points=[p_set, q_set],
        alarm_evaluators=[fault_evaluator, soc_evaluator],
    )

    # ========================================================
    # Step 5: Register Event Handlers (註冊事件處理器)
    # ========================================================

    async def on_value_change(payload):
        print(f"[{payload.device_id}] {payload.point_name}: {payload.old_value} → {payload.new_value}")

    async def on_alarm_triggered(payload):
        event = payload.alarm_event
        print(f"[ALARM] {payload.device_id}: {event.alarm.code} ({event.alarm.level.name})")

    async def on_alarm_cleared(payload):
        event = payload.alarm_event
        print(f"[CLEAR] {payload.device_id}: {event.alarm.code}")

    async def on_disconnected(payload):
        print(f"[DISCONNECT] {payload.device_id}: {payload.reason} (failures={payload.consecutive_failures})")

    # Register handlers (returns cancel function)
    cancel_vc = device.on("value_change", on_value_change)
    cancel_alarm = device.on("alarm_triggered", on_alarm_triggered)
    cancel_clear = device.on("alarm_cleared", on_alarm_cleared)
    cancel_dc = device.on("disconnected", on_disconnected)

    # ========================================================
    # Step 6: Run Device (啟動設備)
    # ========================================================

    # Option A: Context manager (recommended)
    async with device:
        # Device is connected and read loop is running.
        # latest_values is updated every read_interval.

        print(f"Connected: {device.is_connected}")
        print(f"Responsive: {device.is_responsive}")
        print(f"Latest values: {device.latest_values}")

        # Write a power setpoint
        result = await device.write("p_set", 50.0, verify=True)
        print(f"Write result: {result.status.value}")

        # Let it run for 10 seconds
        await asyncio.sleep(10)

    # After exiting: device is stopped and disconnected.

    # Option B: Manual lifecycle (for advanced control)
    # await device.connect()
    # await device.start()
    # ...
    # await device.stop()
    # await device.disconnect()

    # Cleanup: cancel event handlers
    cancel_vc()
    cancel_alarm()
    cancel_clear()
    cancel_dc()


if __name__ == "__main__":
    asyncio.run(main())
