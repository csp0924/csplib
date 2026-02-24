"""
Example 05: SystemController — 生產級系統控制器

Demonstrates:
  - SystemController: full orchestrator with mode management + protection
  - ModeManager: priority-based strategy switching (base/override)
  - ProtectionGuard: SOC protection, reverse power protection, system alarm
  - HeartbeatService: watchdog writes with auto-pause on bypass mode
  - Bypass mode: stops all commands AND heartbeat
  - CascadingStrategy: multi-strategy power allocation (PQ + QV)
  - Auto-stop on alarm

Scenario:
  A 1MW ESS site with full production controls:
    - PQ mode as base strategy
    - QV mode added as second base (cascading)
    - SOC protection to prevent over-charge/discharge
    - Reverse power protection to prevent grid export
    - Heartbeat to keep PCS alive
    - Manual bypass for maintenance
    - Auto-stop when device alarms trigger

Architecture:
  ContextBuilder.build() → StrategyContext (+ system_alarm flag)
       ↓
  StrategyExecutor (strategy chosen by ModeManager)
       ↓
  Command → ProtectionGuard.apply() → protected Command
       ↓
  CommandRouter.route() → device writes
       ↓
  HeartbeatService (parallel) → watchdog writes
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from csp_lib.controller.core import SystemBase
from csp_lib.controller.strategies import (
    BypassStrategy,
    PQModeConfig,
    PQModeStrategy,
    QVConfig,
    QVStrategy,
    StopStrategy,
)
from csp_lib.controller.system import ModePriority, SOCProtection, SOCProtectionConfig
from csp_lib.core.health import HealthStatus
from csp_lib.integration import (
    CommandMapping,
    ContextMapping,
    DeviceRegistry,
    HeartbeatMapping,
    HeartbeatMode,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.integration.schema import HeartbeatMapping


# ============================================================
# Step 1: Setup (same pattern as example 04)
# ============================================================


def make_device(device_id, values, responsive=True, protected=False):
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=not protected)
    type(dev).latest_values = PropertyMock(return_value=values)
    type(dev).active_alarms = PropertyMock(return_value=[])
    dev.write = AsyncMock()
    dev.has_capability = lambda c: False

    def health():
        from csp_lib.core.health import HealthReport

        return HealthReport(
            status=HealthStatus.HEALTHY if not protected else HealthStatus.DEGRADED,
            component=f"device:{device_id}",
            details={},
        )

    dev.health = health
    return dev


def setup():
    meter = make_device("meter_01", {"voltage": 380.0, "frequency": 60.0, "active_power": 30.0})
    pcs_1 = make_device("pcs_01", {})
    pcs_2 = make_device("pcs_02", {})
    bms = make_device("bms_01", {"soc": 80.0})

    registry = DeviceRegistry()
    registry.register(meter, traits=["meter"])
    registry.register(pcs_1, traits=["pcs"])
    registry.register(pcs_2, traits=["pcs"])
    registry.register(bms, traits=["bms"])
    return registry


# ============================================================
# Step 2: Configure SystemController
# ============================================================


async def main():
    registry = setup()

    config = SystemControllerConfig(
        # --- Context Mappings (same as GridControlLoop) ---
        context_mappings=[
            ContextMapping(point_name="soc", context_field="soc", trait="bms"),
            ContextMapping(point_name="voltage", context_field="extra.voltage", trait="meter"),
            ContextMapping(point_name="frequency", context_field="extra.frequency", trait="meter"),
            ContextMapping(point_name="active_power", context_field="extra.meter_power", trait="meter"),
        ],
        # --- Command Mappings ---
        command_mappings=[
            CommandMapping(command_field="p_target", point_name="p_set", trait="pcs"),
            CommandMapping(command_field="q_target", point_name="q_set", trait="pcs"),
        ],
        # --- System Base ---
        system_base=SystemBase(p_base=1000.0, q_base=500.0),
        # --- Protection Rules ---
        protection_rules=[
            SOCProtection(SOCProtectionConfig(soc_high=95.0, soc_low=5.0, warning_band=5.0)),
            # ReversePowerProtection(...),  # Uncomment for reverse power protection
            # SystemAlarmProtection(),       # Uncomment for system alarm protection
        ],
        # --- Alarm Handling ---
        auto_stop_on_alarm=True,  # Push StopStrategy when any device alarms
        alarm_mode="system_wide",  # "system_wide" or "per_device"
        # --- Heartbeat (NEW) ---
        heartbeat_mappings=[
            HeartbeatMapping(point_name="heartbeat", trait="pcs", mode=HeartbeatMode.TOGGLE),
        ],
        heartbeat_interval=1.0,
        # --- Cascading ---
        capacity_kva=1000.0,  # Max apparent power for cascading (kVA)
    )

    controller = SystemController(registry, config)

    # ========================================================
    # Step 3: Register Modes (註冊模式)
    # ========================================================

    # Base modes (priority 10 = SCHEDULE tier)
    controller.register_mode("pq", PQModeStrategy(PQModeConfig(p=500.0, q=0.0)), ModePriority.SCHEDULE)
    controller.register_mode("qv", QVStrategy(QVConfig(nominal_voltage=380.0, droop=5.0)), ModePriority.SCHEDULE)

    # Override modes (higher priority)
    controller.register_mode("bypass", BypassStrategy(), ModePriority.MANUAL)  # priority 50
    controller.register_mode("emergency_stop", StopStrategy(), ModePriority.PROTECTION)  # priority 100

    # Set initial base mode
    await controller.set_base_mode("pq")

    # ========================================================
    # Step 4: Run the Controller
    # ========================================================

    async with controller:
        print(f"Controller running: {controller.is_running}")
        print(f"Current mode: {controller.effective_mode_name}")
        print(f"Heartbeat running: {controller.heartbeat.is_running}")

        # Let PQ mode run for a few cycles
        await asyncio.sleep(2)

        # ---- Add QV as second base mode → CascadingStrategy ----
        print("\n--- Adding QV as second base mode (cascading) ---")
        await controller.add_base_mode("qv")
        print(f"Mode: {controller.effective_mode_name}")
        # Now PQ + QV run together, constrained by 1000 kVA capacity
        await asyncio.sleep(2)

        # ---- Push bypass override → stops commands + heartbeat ----
        print("\n--- Entering bypass mode (maintenance) ---")
        await controller.push_override("bypass")
        print(f"Mode: {controller.effective_mode_name}")
        print(f"Heartbeat paused: {controller.heartbeat.is_paused}")
        # Commands stop, heartbeat stops → PCS enters safe mode
        await asyncio.sleep(2)

        # ---- Pop bypass → resumes normal operation ----
        print("\n--- Exiting bypass mode ---")
        await controller.pop_override("bypass")
        print(f"Mode: {controller.effective_mode_name}")
        print(f"Heartbeat paused: {controller.heartbeat.is_paused}")
        await asyncio.sleep(2)

        # ---- Check protection status ----
        result = controller.protection_status
        if result:
            print(f"\nProtection result: triggered_rules={result.triggered_rules}")
            print(f"  Original command: {result.original_command}")
            print(f"  Protected command: {result.protected_command}")

        # ---- Health check ----
        health = controller.health()
        print(f"\nSystem health: {health.status.name}")
        for child in health.children:
            print(f"  {child.component}: {child.status.name}")

    print("\nController stopped.")


# ============================================================
# Mode Priority Cheat Sheet:
#
#   ModePriority.SCHEDULE   = 10   (normal operation)
#   ModePriority.MANUAL     = 50   (operator override)
#   ModePriority.PROTECTION = 100  (safety override)
#   Auto-stop               = 101  (highest, auto-managed)
#
# The HIGHEST priority override always wins.
# When no overrides: base mode(s) run.
# Multiple base modes → CascadingStrategy (if capacity_kva is set).
# ============================================================


if __name__ == "__main__":
    asyncio.run(main())
