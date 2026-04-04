"""
Example 13: AsyncCANDevice — CAN Bus 設備完整範例

Demonstrates:
  - PythonCANClient: python-can backed CAN client
  - AsyncCANDevice: async CAN device with TX/RX/alarm/capability support
  - Three operation modes:
      1. Passive listen (RX periodic frames from device)
      2. Active control (TX signals with periodic scheduler)
      3. Request-response (send request, wait for reply)
  - CANSignalDefinition + FrameBufferConfig: TX frame buffer setup
  - CANRxFrameDefinition + CANFrameParser: RX frame parsing
  - PeriodicFrameConfig: periodic TX scheduling
  - Event system: value_change, connected, disconnected
  - write(): update frame buffer signal (with optional immediate send)

Note:
  This example uses a mock CAN client so it can run without real hardware.
  To use with real hardware, replace MockCANClient with PythonCANClient.

Requirements:
  pip install csp0924_lib[can]
"""

import asyncio
from typing import Any, Callable

from csp_lib.can.config import CANFrame
from csp_lib.equipment.device import DeviceConfig
from csp_lib.equipment.device.can_device import AsyncCANDevice, CANRxFrameDefinition
from csp_lib.equipment.processing.can_parser import CANFrameParser

# ============================================================
# Mock CAN client (replaces PythonCANClient for demo)
# ============================================================


class MockCANClient:
    """
    Mock CAN client for demonstration.

    Simulates a CAN bus where:
    - connect() / disconnect() are no-ops
    - start_listener() / stop_listener() are no-ops
    - subscribe() registers handlers and allows simulate_rx()
    - send() prints the frame to stdout
    - request() returns a synthetic response frame
    """

    def __init__(self) -> None:
        self._handlers: dict[int, list[Callable[[CANFrame], Any]]] = {}
        self._connected = False

    async def connect(self) -> None:
        self._connected = True
        print("  [MockCAN] Connected to virtual CAN bus")

    async def disconnect(self) -> None:
        self._connected = False
        print("  [MockCAN] Disconnected from CAN bus")

    async def is_connected(self) -> bool:
        return self._connected

    async def start_listener(self) -> None:
        print("  [MockCAN] RX listener started")

    async def stop_listener(self) -> None:
        print("  [MockCAN] RX listener stopped")

    def subscribe(self, can_id: int, handler: Callable[[CANFrame], Any]) -> Callable[[], None]:
        self._handlers.setdefault(can_id, []).append(handler)

        def unsubscribe() -> None:
            self._handlers[can_id].remove(handler)

        return unsubscribe

    async def send(self, can_id: int, data: bytes) -> None:
        print(f"  [MockCAN] TX  CAN_ID=0x{can_id:03X}  data={data.hex().upper()}")

    async def request(self, can_id: int, data: bytes, response_id: int, timeout: float = 1.0) -> CANFrame:
        print(f"  [MockCAN] REQ CAN_ID=0x{can_id:03X}  data={data.hex().upper()}")
        # Return synthetic response frame (8 bytes, all zeros for demo)
        return CANFrame(can_id=response_id, data=b"\x00" * 8, timestamp=0.0)

    def simulate_rx(self, can_id: int, data: bytes) -> None:
        """Inject a simulated received CAN frame into subscribed handlers."""
        frame = CANFrame(can_id=can_id, data=data, timestamp=asyncio.get_event_loop().time())
        for handler in self._handlers.get(can_id, []):
            handler(frame)


# ============================================================
# Scenario A: Passive listen (RX periodic frames)
# ============================================================


async def demo_passive_listen():
    """
    Scenario A: Passive listen mode.

    The device subscribes to CAN ID 0x100 and passively receives BMS
    status frames. Each received frame is parsed and available in
    device.latest_values.

    In production, the BMS broadcasts this frame every 100ms autonomously.
    Here we simulate it with simulate_rx().
    """
    print("=" * 60)
    print("Scenario A: Passive Listen (BMS SOC/voltage frame)")
    print("=" * 60)

    client = MockCANClient()

    # Define RX parser for BMS frame (CAN ID=0x100)
    # Frame layout (simplified): bytes 0-1 = SOC (raw/10 = %), bytes 2-3 = voltage (raw/10 = V)
    bms_parser = CANFrameParser(
        source_name="raw",
        points=[],  # In production, add CANSignalPoint definitions here
    )

    config = DeviceConfig(device_id="bms_001", read_interval=1.0)

    device = AsyncCANDevice(
        config=config,
        client=client,
        rx_frame_definitions=[
            CANRxFrameDefinition(can_id=0x100, parser=bms_parser, is_periodic=True),
        ],
        rx_timeout=5.0,
    )

    # Register value_change event
    received_values = []

    def on_value_change(payload: Any) -> None:
        print(f"  [Event] value_change: {payload.point_name} = {payload.new_value}")
        received_values.append((payload.point_name, payload.new_value))

    async with device:
        device.on("value_change", on_value_change)
        device.on("connected", lambda p: print(f"  [Event] connected: {p.device_id}"))

        print(f"\n  Device: {device}")
        print(f"  is_connected={device.is_connected}, is_responsive={device.is_responsive}")

        # Simulate 3 BMS frames arriving from the CAN bus
        print("\n  Simulating BMS frames on CAN ID=0x100 ...")
        for i in range(3):
            # Synthetic frame: 8 bytes
            data = bytes([0x03, 0xE8 + i, 0x0E, 0xBA, 0x00, 0x00, 0x00, 0x00])
            client.simulate_rx(0x100, data)
            await asyncio.sleep(0.1)

        print(f"\n  latest_values: {device.latest_values}")
        print(f"  Value change events received: {len(received_values)}")


# ============================================================
# Scenario B: Active control (TX periodic signals)
# ============================================================


async def demo_active_control():
    """
    Scenario B: Active control mode with periodic TX.

    The device maintains a frame buffer for CAN ID=0x200 and
    sends it periodically (every 100ms). Calling write() updates
    the signal value in the buffer; the scheduler sends the frame
    automatically on the next cycle.

    Calling write(..., immediate=True) sends the frame immediately
    without waiting for the next scheduled cycle.
    """
    print("\n" + "=" * 60)
    print("Scenario B: Active Control (PCS power target TX)")
    print("=" * 60)

    client = MockCANClient()
    config = DeviceConfig(device_id="pcs_001", read_interval=1.0)

    # Use a simple device with no TX signals configured (for API demonstration).
    # In production, you would pass tx_signals=[CANSignalDefinition(...)],
    # tx_buffer_configs=[FrameBufferConfig(can_id=0x200)], and
    # tx_periodic_configs=[PeriodicFrameConfig(can_id=0x200, interval=0.1)]
    device = AsyncCANDevice(
        config=config,
        client=client,
        # TX signals omitted — demonstrates write() API behavior when not configured
    )

    async with device:
        print(f"\n  Device: {device}")

        # write() — update signal in frame buffer
        # Without TX signals configured, write() returns VALIDATION_FAILED
        # This demonstrates the write() API signature
        result = await device.write("power_target", 5000)
        print(f"\n  write('power_target', 5000): status={result.status}")
        print("  (VALIDATION_FAILED because no TX signals configured in this demo)")
        print("  In production with tx_signals configured: status=SUCCESS")

        # Demonstrate immediate write
        result = await device.write("power_target", 5000, immediate=True)
        print(f"  write(..., immediate=True): status={result.status}")

        await asyncio.sleep(0.5)


# ============================================================
# Scenario C: Request-Response
# ============================================================


async def demo_request_response():
    """
    Scenario C: Request-Response mode.

    Some CAN devices (e.g., BMS with query protocol) don't broadcast
    status automatically. Instead, the controller sends a request frame
    and waits for the device to reply.

    CANRxFrameDefinition with is_periodic=False + request_data triggers
    this mode. read_once() sends the request and waits for the response.
    """
    print("\n" + "=" * 60)
    print("Scenario C: Request-Response (query battery status)")
    print("=" * 60)

    client = MockCANClient()

    query_parser = CANFrameParser(source_name="raw", points=[])

    config = DeviceConfig(device_id="bms_query_001", read_interval=2.0)

    device = AsyncCANDevice(
        config=config,
        client=client,
        rx_frame_definitions=[
            # Request-response: send 0x01 0x02 to CAN ID=0x300, expect reply on same ID
            CANRxFrameDefinition(
                can_id=0x300,
                parser=query_parser,
                is_periodic=False,
                request_data=b"\x01\x02",  # Query command
            ),
        ],
        rx_timeout=5.0,
    )

    async with device:
        print(f"\n  Device: {device}")
        print("\n  Calling read_once() → triggers request-response cycle ...")
        values = await device.read_once()
        print(f"  Response received. latest_values: {values}")


# ============================================================
# Scenario D: CAN device with capabilities + registry
# ============================================================


async def demo_can_device_with_registry():
    """
    Scenario D: CAN device registered in DeviceRegistry with capabilities.

    AsyncCANDevice supports the same capability system as AsyncModbusDevice.
    This allows SystemController to route commands to CAN devices via
    capability-based command mappings, enabling mixed Modbus/CAN fleets.
    """
    print("\n" + "=" * 60)
    print("Scenario D: AsyncCANDevice in DeviceRegistry")
    print("=" * 60)

    from csp_lib.equipment.device.capability import Capability, CapabilityBinding
    from csp_lib.integration import DeviceRegistry

    client = MockCANClient()
    config = DeviceConfig(device_id="can_pcs_001", read_interval=1.0)

    # Define capability
    POWER_WRITE = Capability("power_writable", write_slots=("p_target", "q_target"))

    device = AsyncCANDevice(
        config=config,
        client=client,
        capability_bindings=[
            CapabilityBinding(
                capability=POWER_WRITE,
                point_map={"p_target": "power_target", "q_target": "reactive_target"},
            ),
        ],
    )

    # Register in DeviceRegistry (same as Modbus devices)
    registry = DeviceRegistry()
    registry.register(device, traits=["pcs", "can"], metadata={"rated_p": 500.0})

    print(f"\n  Device capabilities: {list(device.capabilities.keys())}")
    print(f"  has_capability('power_writable'): {device.has_capability('power_writable')}")

    retrieved = registry.get("can_pcs_001")
    print(f"  Retrieved from registry: {retrieved.device_id}")
    print(f"  Devices with 'pcs' trait: {[d.device_id for d in registry.get_by_trait('pcs')]}")
    print(f"  Devices with 'can' trait: {[d.device_id for d in registry.get_by_trait('can')]}")


# ============================================================
# Run all scenarios
# ============================================================


async def main():
    await demo_passive_listen()
    await demo_active_control()
    await demo_request_response()
    await demo_can_device_with_registry()

    print("\n" + "=" * 60)
    print("AsyncCANDevice Example Complete")
    print("=" * 60)
    print("\nKey takeaways:")
    print("  - Use is_periodic=True for devices that broadcast autonomously")
    print("  - Use is_periodic=False + request_data for query-response protocols")
    print("  - write(..., immediate=True) bypasses periodic scheduler")
    print("  - AsyncCANDevice supports capability system like AsyncModbusDevice")
    print("  - Register CAN devices in DeviceRegistry alongside Modbus devices")


if __name__ == "__main__":
    asyncio.run(main())
