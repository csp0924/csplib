"""
Example 04: GridControlLoop — 簡易控制迴圈

Demonstrates:
  - DeviceRegistry with trait-based device organization
  - ContextMapping: device values → StrategyContext
  - CommandMapping: Command → device writes
  - GridControlLoop: the simple orchestrator that wires everything together

Scenario:
  A small ESS site with:
    - 1 meter (reads grid voltage, frequency, active power)
    - 2 PCS units (writes P/Q setpoints)
    - 1 BMS (reads SOC)
  Running PQ mode at 50kW discharge.

Architecture:
  [Meter] ─read─→ ContextBuilder ──→ StrategyContext
  [BMS]   ─read─→                        │
                                  StrategyExecutor (PQ)
                                          │
                                       Command
                                          │
  [PCS×2] ←write─ CommandRouter ←────────┘
"""

import asyncio

from csp_lib.controller.core import SystemBase
from csp_lib.controller.strategies import PQModeConfig, PQModeStrategy
from csp_lib.integration import (
    CommandMapping,
    ContextMapping,
    DeviceRegistry,
    GridControlLoop,
    GridControlLoopConfig,
)

# ============================================================
# Step 1: Create Devices (in real code, use DeviceFactory)
# ============================================================
# For this example, we'll assume devices are already created.
# See example 01/02 for how to create real devices.


def create_mock_devices():
    """Create mock devices for demonstration. In production, use real AsyncModbusDevice."""
    from unittest.mock import AsyncMock, MagicMock, PropertyMock

    def make_device(device_id, values, responsive=True):
        dev = MagicMock()
        type(dev).device_id = PropertyMock(return_value=device_id)
        type(dev).is_connected = PropertyMock(return_value=True)
        type(dev).is_responsive = PropertyMock(return_value=responsive)
        type(dev).is_protected = PropertyMock(return_value=False)
        type(dev).latest_values = PropertyMock(return_value=values)
        dev.write = AsyncMock()
        dev.has_capability = lambda c: False
        return dev

    meter = make_device("meter_01", {"voltage": 380.0, "frequency": 60.0, "active_power": 20.0})
    pcs_1 = make_device("pcs_01", {"active_power": 0.0})
    pcs_2 = make_device("pcs_02", {"active_power": 0.0})
    bms = make_device("bms_01", {"soc": 75.0})

    return meter, pcs_1, pcs_2, bms


# ============================================================
# Step 2: Set Up Registry (設備註冊)
# ============================================================


def setup_registry():
    meter, pcs_1, pcs_2, bms = create_mock_devices()

    registry = DeviceRegistry()
    registry.register(meter, traits=["meter"])
    registry.register(pcs_1, traits=["pcs"])
    registry.register(pcs_2, traits=["pcs"])
    registry.register(bms, traits=["bms"])

    return registry


# ============================================================
# Step 3: Define Mappings (映射定義)
# ============================================================

# ContextMapping: which device values go into StrategyContext
context_mappings = [
    # BMS SOC → context.soc (average across all BMS devices)
    ContextMapping(point_name="soc", context_field="soc", trait="bms"),
    # Meter voltage → context.extra["voltage"] (average across all meters)
    ContextMapping(point_name="voltage", context_field="extra.voltage", trait="meter"),
    # Meter frequency → context.extra["frequency"]
    ContextMapping(point_name="frequency", context_field="extra.frequency", trait="meter"),
    # Meter active power → context.extra["meter_power"]
    ContextMapping(point_name="active_power", context_field="extra.meter_power", trait="meter"),
]

# CommandMapping: which Command fields get written to which devices
command_mappings = [
    # command.p_target → write to ALL PCS devices' "p_set" point
    CommandMapping(command_field="p_target", point_name="p_set", trait="pcs"),
    # command.q_target → write to ALL PCS devices' "q_set" point
    CommandMapping(command_field="q_target", point_name="q_set", trait="pcs"),
]

# Optional: transform for power splitting across multiple PCS units
# If you want to split 100kW evenly across 2 PCS:
# CommandMapping(
#     command_field="p_target",
#     point_name="p_set",
#     trait="pcs",
#     transform=lambda p: p / 2,  # 50kW each
# )

# ============================================================
# Step 4: Create and Run GridControlLoop
# ============================================================


async def main():
    registry = setup_registry()

    # Configure the control loop
    config = GridControlLoopConfig(
        context_mappings=context_mappings,
        command_mappings=command_mappings,
        system_base=SystemBase(p_base=200.0, q_base=100.0),  # 200kW / 100kVar rated
    )

    # Create the loop
    loop = GridControlLoop(registry, config)

    # Set the strategy
    strategy = PQModeStrategy(PQModeConfig(p=50.0, q=0.0))
    await loop.set_strategy(strategy)

    # Run with context manager
    async with loop:
        print(f"GridControlLoop running: {loop.is_running}")
        print(f"Strategy: {loop.executor.current_strategy}")

        # Let it run for a few cycles
        await asyncio.sleep(3)

        # Switch strategy mid-flight
        from csp_lib.controller.strategies import QVConfig, QVStrategy

        qv = QVStrategy(QVConfig(nominal_voltage=380.0, droop=5.0))
        await loop.set_strategy(qv)
        print(f"Switched to: {loop.executor.current_strategy}")

        await asyncio.sleep(3)

    # Verify writes happened
    pcs_01 = registry.get_device("pcs_01")
    pcs_02 = registry.get_device("pcs_02")
    print(f"\npcs_01 write calls: {pcs_01.write.call_count}")
    print(f"pcs_02 write calls: {pcs_02.write.call_count}")

    # Manual trigger (for TRIGGERED/HYBRID strategies):
    # loop.trigger()


if __name__ == "__main__":
    asyncio.run(main())
