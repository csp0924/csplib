"""Integration test for ModbusGatewayServer — uses pymodbus TCP client to verify FC03/FC04/FC16.

Skipped entirely if pymodbus is not installed.
"""

from __future__ import annotations

import asyncio

import pytest

pymodbus = pytest.importorskip("pymodbus", reason="pymodbus not installed")

from pymodbus.client import AsyncModbusTcpClient  # noqa: E402

from csp_lib.modbus.types.numeric import Int32, UInt16  # noqa: E402
from csp_lib.modbus_gateway.config import (  # noqa: E402
    GatewayRegisterDef,
    GatewayServerConfig,
    RegisterType,
    WatchdogConfig,
    WriteRule,
)
from csp_lib.modbus_gateway.server import ModbusGatewayServer  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNIT_ID = 1
_PORT = 15502  # non-privileged port to avoid conflicts


def _server_config(port: int = _PORT) -> GatewayServerConfig:
    return GatewayServerConfig(
        host="127.0.0.1",
        port=port,
        unit_id=_UNIT_ID,
        watchdog=WatchdogConfig(enabled=False),
    )


def _hr_reg(name: str, address: int, data_type=None, **kw) -> GatewayRegisterDef:
    return GatewayRegisterDef(
        name=name,
        address=address,
        data_type=data_type or UInt16(),
        register_type=RegisterType.HOLDING,
        **kw,
    )


def _ir_reg(name: str, address: int, data_type=None, **kw) -> GatewayRegisterDef:
    return GatewayRegisterDef(
        name=name,
        address=address,
        data_type=data_type or UInt16(),
        register_type=RegisterType.INPUT,
        **kw,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def gateway_and_client():
    """Start a ModbusGatewayServer and yield (server, client)."""
    registers = [
        _hr_reg("p_command", 0, Int32(), initial_value=0),
        _hr_reg("mode", 10, UInt16(), initial_value=1),
        _ir_reg("soc", 0, UInt16(), scale=10, initial_value=50),
        _ir_reg("frequency", 2, UInt16(), scale=100, initial_value=60),
    ]
    write_rules = {
        "p_command": WriteRule(register_name="p_command", min_value=-5000, max_value=5000, clamp=True),
    }

    config = _server_config()
    server = ModbusGatewayServer(config, registers, write_rules=write_rules)

    await server.start()
    # Small delay to let the TCP listener start
    await asyncio.sleep(0.3)

    client = AsyncModbusTcpClient("127.0.0.1", port=_PORT)
    await client.connect()
    assert client.connected, "Modbus TCP client failed to connect"

    yield server, client

    client.close()
    await server.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestModbusGatewayIntegration:
    """End-to-end tests using a real pymodbus TCP client."""

    @pytest.mark.asyncio
    async def test_fc03_read_holding_registers(self, gateway_and_client) -> None:
        """FC03: Read holding register 'mode' — should return initial value 1."""
        server, client = gateway_and_client
        result = await client.read_holding_registers(address=10, count=1, device_id=_UNIT_ID)
        assert not result.isError(), f"FC03 failed: {result}"
        assert result.registers[0] == 1

    @pytest.mark.asyncio
    async def test_fc03_read_int32_holding_register(self, gateway_and_client) -> None:
        """FC03: Read Int32 holding register 'p_command' — should return initial value 0."""
        server, client = gateway_and_client
        result = await client.read_holding_registers(address=0, count=2, device_id=_UNIT_ID)
        assert not result.isError(), f"FC03 failed: {result}"
        # Int32 at address 0, initial_value=0 → both registers should be 0
        assert result.registers == [0, 0]

    @pytest.mark.asyncio
    async def test_fc04_read_input_registers(self, gateway_and_client) -> None:
        """FC04: Read input register 'soc' — physical=50, scale=10 → raw=500."""
        server, client = gateway_and_client
        result = await client.read_input_registers(address=0, count=1, device_id=_UNIT_ID)
        assert not result.isError(), f"FC04 failed: {result}"
        assert result.registers[0] == 500  # 50 * 10

    @pytest.mark.asyncio
    async def test_fc04_read_frequency(self, gateway_and_client) -> None:
        """FC04: Read input register 'frequency' — physical=60, scale=100 → raw=6000."""
        server, client = gateway_and_client
        result = await client.read_input_registers(address=2, count=1, device_id=_UNIT_ID)
        assert not result.isError(), f"FC04 failed: {result}"
        assert result.registers[0] == 6000  # 60 * 100

    @pytest.mark.asyncio
    async def test_fc16_write_holding_registers(self, gateway_and_client) -> None:
        """FC16: Write holding register 'mode' and verify via get_register."""
        server, client = gateway_and_client
        result = await client.write_registers(address=10, values=[42], device_id=_UNIT_ID)
        assert not result.isError(), f"FC16 failed: {result}"

        # Verify via programmatic API
        assert server.get_register("mode") == 42

    @pytest.mark.asyncio
    async def test_fc16_write_then_fc03_read(self, gateway_and_client) -> None:
        """FC16 write + FC03 read round-trip for 'mode'."""
        server, client = gateway_and_client
        await client.write_registers(address=10, values=[99], device_id=_UNIT_ID)
        result = await client.read_holding_registers(address=10, count=1, device_id=_UNIT_ID)
        assert not result.isError()
        assert result.registers[0] == 99

    @pytest.mark.asyncio
    async def test_write_rule_clamp(self, gateway_and_client) -> None:
        """WriteRule clamp: writing p_command > 5000 should clamp to 5000."""
        server, client = gateway_and_client
        # Encode a large Int32 value (e.g. 9999) and write via FC16
        from csp_lib.modbus import ModbusCodec

        codec = ModbusCodec()
        encoded = codec.encode(Int32(), 9999, server.config.byte_order, server.config.register_order)
        result = await client.write_registers(address=0, values=encoded, device_id=_UNIT_ID)
        assert not result.isError(), f"FC16 failed: {result}"

        # The write rule should clamp p_command to 5000
        assert server.get_register("p_command") == 5000

    @pytest.mark.asyncio
    async def test_set_register_then_fc03_read(self, gateway_and_client) -> None:
        """Programmatic set_register then FC03 read."""
        server, client = gateway_and_client
        server.set_register("mode", 7)
        result = await client.read_holding_registers(address=10, count=1, device_id=_UNIT_ID)
        assert not result.isError()
        assert result.registers[0] == 7

    @pytest.mark.asyncio
    async def test_set_input_register_then_fc04_read(self, gateway_and_client) -> None:
        """Programmatic set_register for input register then FC04 read."""
        server, client = gateway_and_client
        server.set_register("soc", 85)
        result = await client.read_input_registers(address=0, count=1, device_id=_UNIT_ID)
        assert not result.isError()
        assert result.registers[0] == 850  # 85 * 10
