from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from csp_lib.modbus.config import ModbusTcpConfig
from csp_lib.modbus.exceptions import ModbusError


class TestPymodbusTcpClient:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        with (
            patch("csp_lib.modbus.clients.client._ensure_pymodbus_imported"),
            patch("csp_lib.modbus.clients.client._AsyncModbusTcpClient") as MockTcpCls,
        ):
            mock_client = AsyncMock()
            mock_client.connected = False
            mock_client.connect = AsyncMock(return_value=True)
            MockTcpCls.return_value = mock_client

            from csp_lib.modbus.clients.client import PymodbusTcpClient

            config = ModbusTcpConfig(host="192.168.1.1")
            client = PymodbusTcpClient(config)
            client._client = mock_client  # bypass lazy init
            await client.connect()
            mock_client.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure_raises(self):
        from csp_lib.modbus.clients.client import PymodbusTcpClient

        config = ModbusTcpConfig(host="192.168.1.1")
        client = PymodbusTcpClient(config)
        mock_pymodbus = AsyncMock()
        mock_pymodbus.connected = False
        mock_pymodbus.connect = AsyncMock(return_value=False)
        client._client = mock_pymodbus
        with pytest.raises(ModbusError):
            await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self):
        from csp_lib.modbus.clients.client import PymodbusTcpClient

        config = ModbusTcpConfig(host="192.168.1.1")
        client = PymodbusTcpClient(config)
        # Should not raise when _client is None
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_read_success(self):
        from csp_lib.modbus.clients.client import PymodbusTcpClient

        config = ModbusTcpConfig(host="192.168.1.1")
        client = PymodbusTcpClient(config)
        mock_pymodbus = AsyncMock()
        mock_pymodbus.connected = True
        response = MagicMock()
        response.isError.return_value = False
        response.registers = [100, 200, 300]
        mock_pymodbus.read_holding_registers = AsyncMock(return_value=response)
        client._client = mock_pymodbus
        result = await client.read_holding_registers(0, 3)
        assert result == [100, 200, 300]

    @pytest.mark.asyncio
    async def test_read_error(self):
        from csp_lib.modbus.clients.client import PymodbusTcpClient

        config = ModbusTcpConfig(host="192.168.1.1")
        client = PymodbusTcpClient(config)
        mock_pymodbus = AsyncMock()
        response = MagicMock()
        response.isError.return_value = True
        mock_pymodbus.read_holding_registers = AsyncMock(return_value=response)
        client._client = mock_pymodbus
        with pytest.raises(ModbusError):
            await client.read_holding_registers(0, 3)

    @pytest.mark.asyncio
    async def test_write_success(self):
        from csp_lib.modbus.clients.client import PymodbusTcpClient

        config = ModbusTcpConfig(host="192.168.1.1")
        client = PymodbusTcpClient(config)
        mock_pymodbus = AsyncMock()
        response = MagicMock()
        response.isError.return_value = False
        mock_pymodbus.write_registers = AsyncMock(return_value=response)
        client._client = mock_pymodbus
        await client.write_multiple_registers(0, [100, 200])

    @pytest.mark.asyncio
    async def test_write_error(self):
        from csp_lib.modbus.clients.client import PymodbusTcpClient

        config = ModbusTcpConfig(host="192.168.1.1")
        client = PymodbusTcpClient(config)
        mock_pymodbus = AsyncMock()
        response = MagicMock()
        response.isError.return_value = True
        mock_pymodbus.write_registers = AsyncMock(return_value=response)
        client._client = mock_pymodbus
        with pytest.raises(ModbusError):
            await client.write_multiple_registers(0, [100, 200])

    @pytest.mark.asyncio
    async def test_is_connected_false_initially(self):
        from csp_lib.modbus.clients.client import PymodbusTcpClient

        config = ModbusTcpConfig(host="192.168.1.1")
        client = PymodbusTcpClient(config)
        assert await client.is_connected() is False
