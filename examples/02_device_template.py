"""
Example 02: Device Templates & Capabilities — 設備範本與能力系統

Demonstrates:
  - Defining reusable EquipmentTemplate for different device models
  - Using Capability and CapabilityBinding so the SAME capability works
    across devices with DIFFERENT register names
  - DeviceFactory for single and batch device creation
  - Runtime capability addition/removal

Scenario:
  Two PCS models from different manufacturers:
    - Sungrow SG110CX: heartbeat register = "watchdog", p_set = "p_ref"
    - Huawei SUN2000:   heartbeat register = "hb_reg",  p_set = "active_power_set"
  Both declare HEARTBEAT and ACTIVE_POWER_CONTROL capabilities.
  The controller uses capabilities to find devices, regardless of register names.
"""

from csp_lib.equipment.core import ReadPoint, WritePoint, pipeline, ScaleTransform
from csp_lib.equipment.core.point import RangeValidator
from csp_lib.equipment.device import DeviceConfig
from csp_lib.equipment.device.capability import (
    ACTIVE_POWER_CONTROL,
    HEARTBEAT,
    MEASURABLE,
    REACTIVE_POWER_CONTROL,
    SOC_READABLE,
    Capability,
    CapabilityBinding,
)
from csp_lib.equipment.template import DeviceFactory, EquipmentTemplate
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16

# ============================================================
# Step 1: Define Templates for Different PCS Models
# ============================================================

# --- Sungrow SG110CX ---
sungrow_template = EquipmentTemplate(
    model="Sungrow-SG110CX",
    always_points=(
        ReadPoint(name="active_power", address=5000, data_type=Float32(), pipeline=pipeline(ScaleTransform(0.1))),
        ReadPoint(name="soc", address=5034, data_type=UInt16(), pipeline=pipeline(ScaleTransform(0.1))),
    ),
    write_points=(
        WritePoint(name="p_ref", address=6000, data_type=Float32(), validator=RangeValidator(-110.0, 110.0)),
        WritePoint(name="q_ref", address=6002, data_type=Float32(), validator=RangeValidator(-60.0, 60.0)),
        WritePoint(name="watchdog", address=6100, data_type=UInt16()),
    ),
    capability_bindings=(
        # Sungrow calls its heartbeat register "watchdog"
        CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"}),
        # Sungrow calls its P setpoint "p_ref"
        CapabilityBinding(ACTIVE_POWER_CONTROL, {"p_setpoint": "p_ref", "p_measurement": "active_power"}),
        CapabilityBinding(REACTIVE_POWER_CONTROL, {"q_setpoint": "q_ref"}),
        CapabilityBinding(MEASURABLE, {"active_power": "active_power"}),
        CapabilityBinding(SOC_READABLE, {"soc": "soc"}),
    ),
    description="Sungrow 110kW hybrid inverter",
)

# --- Huawei SUN2000 ---
huawei_template = EquipmentTemplate(
    model="Huawei-SUN2000-100KTL",
    always_points=(
        ReadPoint(name="grid_power", address=32080, data_type=Float32()),
        ReadPoint(name="bat_soc", address=37004, data_type=UInt16(), pipeline=pipeline(ScaleTransform(0.1))),
    ),
    write_points=(
        WritePoint(name="active_power_set", address=47075, data_type=Float32(), validator=RangeValidator(-100.0, 100.0)),
        WritePoint(name="reactive_power_set", address=47077, data_type=Float32()),
        WritePoint(name="hb_reg", address=47000, data_type=UInt16()),
    ),
    capability_bindings=(
        # Huawei calls its heartbeat register "hb_reg"
        CapabilityBinding(HEARTBEAT, {"heartbeat": "hb_reg"}),
        # Huawei calls its P setpoint "active_power_set"
        CapabilityBinding(ACTIVE_POWER_CONTROL, {"p_setpoint": "active_power_set", "p_measurement": "grid_power"}),
        CapabilityBinding(REACTIVE_POWER_CONTROL, {"q_setpoint": "reactive_power_set"}),
        CapabilityBinding(MEASURABLE, {"active_power": "grid_power"}),
        CapabilityBinding(SOC_READABLE, {"soc": "bat_soc"}),
    ),
    description="Huawei 100kW string inverter",
)

# ============================================================
# Step 2: Create Devices with DeviceFactory
# ============================================================


def create_devices():
    # --- Single device creation ---
    sungrow_client = PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.100", port=502))
    sungrow_config = DeviceConfig(device_id="pcs_sungrow_01", unit_id=1, read_interval=1.0)

    sungrow_device = DeviceFactory.create(
        template=sungrow_template,
        config=sungrow_config,
        client=sungrow_client,
    )

    # --- Batch creation (3 Huawei units sharing same template) ---
    huawei_configs = [
        DeviceConfig(device_id="pcs_huawei_01", unit_id=1),
        DeviceConfig(device_id="pcs_huawei_02", unit_id=2),
        DeviceConfig(device_id="pcs_huawei_03", unit_id=3),
    ]

    huawei_devices = DeviceFactory.create_batch(
        template=huawei_template,
        instances=huawei_configs,
        client_factory=lambda cfg: PymodbusTcpClient(ModbusTcpConfig(host="192.168.1.200", port=502)),
    )

    return sungrow_device, huawei_devices


# ============================================================
# Step 3: Use Capabilities for Uniform Access
# ============================================================


def demonstrate_capabilities():
    sungrow_device, huawei_devices = create_devices()
    all_devices = [sungrow_device, *huawei_devices]

    # Check capabilities
    for dev in all_devices:
        print(f"\n{dev.device_id}:")
        print(f"  Has HEARTBEAT: {dev.has_capability(HEARTBEAT)}")
        print(f"  Has ACTIVE_POWER_CONTROL: {dev.has_capability(ACTIVE_POWER_CONTROL)}")

        # Resolve the ACTUAL point name — different per device model!
        hb_point = dev.resolve_point(HEARTBEAT, "heartbeat")
        p_point = dev.resolve_point(ACTIVE_POWER_CONTROL, "p_setpoint")
        print(f"  Heartbeat point: {hb_point}")  # "watchdog" or "hb_reg"
        print(f"  P setpoint point: {p_point}")  # "p_ref" or "active_power_set"


# ============================================================
# Step 4: Runtime Capability Changes
# ============================================================


def demonstrate_runtime_capabilities():
    sungrow_device, _ = create_devices()

    # Define a custom capability
    GRID_FORMING = Capability(
        name="grid_forming",
        write_slots=("vf_enable",),
        read_slots=("grid_status",),
        description="Grid-forming / island mode",
    )

    # Initially, device doesn't have grid_forming
    print(f"Has GRID_FORMING: {sungrow_device.has_capability(GRID_FORMING)}")  # False

    # Firmware update adds new capability — add at runtime
    # (normally the write/read points would also need to exist on the device)
    sungrow_device.add_capability(
        CapabilityBinding(GRID_FORMING, {"vf_enable": "island_cmd", "grid_status": "grid_relay_fb"})
    )
    print(f"Has GRID_FORMING: {sungrow_device.has_capability(GRID_FORMING)}")  # True

    # Remove capability
    sungrow_device.remove_capability(GRID_FORMING)
    print(f"Has GRID_FORMING: {sungrow_device.has_capability(GRID_FORMING)}")  # False


# ============================================================
# Step 5: Registry with Capability Queries
# ============================================================


def demonstrate_registry():
    from csp_lib.integration import DeviceRegistry

    sungrow_device, huawei_devices = create_devices()

    registry = DeviceRegistry()
    registry.register(sungrow_device, traits=["pcs", "hybrid"])
    for dev in huawei_devices:
        registry.register(dev, traits=["pcs", "string"])

    # Query by trait (traditional)
    all_pcs = registry.get_devices_by_trait("pcs")
    print(f"PCS devices: {[d.device_id for d in all_pcs]}")

    # Query by capability (new) — works across different device models
    heartbeat_devices = registry.get_devices_with_capability(HEARTBEAT)
    print(f"Heartbeat-capable: {[d.device_id for d in heartbeat_devices]}")

    # Resolve point names uniformly
    for dev in heartbeat_devices:
        point = dev.resolve_point(HEARTBEAT, "heartbeat")
        print(f"  {dev.device_id} → heartbeat point = '{point}'")
        # pcs_sungrow_01 → "watchdog"
        # pcs_huawei_01  → "hb_reg"
        # pcs_huawei_02  → "hb_reg"
        # pcs_huawei_03  → "hb_reg"


if __name__ == "__main__":
    demonstrate_capabilities()
    print("\n--- Runtime Capabilities ---")
    demonstrate_runtime_capabilities()
    print("\n--- Registry Queries ---")
    demonstrate_registry()
