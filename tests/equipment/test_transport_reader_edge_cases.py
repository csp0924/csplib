from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.core.errors import CommunicationError, ConfigurationError
from csp_lib.equipment.core.point import ReadPoint
from csp_lib.equipment.transport.base import ReadGroup
from csp_lib.equipment.transport.reader import GroupReader
from csp_lib.modbus import ByteOrder, FunctionCode, RegisterOrder, UInt16


def _make_point(name: str, address: int):
    return ReadPoint(
        name=name,
        address=address,
        data_type=UInt16(),
        function_code=FunctionCode.READ_HOLDING_REGISTERS,
        byte_order=ByteOrder.BIG_ENDIAN,
        register_order=RegisterOrder.HIGH_FIRST,
    )


def _make_group(start: int, count: int, points: tuple):
    return ReadGroup(
        function_code=FunctionCode.READ_HOLDING_REGISTERS,
        start_address=start,
        count=count,
        points=points,
    )


class TestGroupReaderEdgeCases:
    def test_max_concurrent_reads_zero_raises(self):
        client = MagicMock()
        with pytest.raises(ConfigurationError):
            GroupReader(client, max_concurrent_reads=0)

    def test_max_concurrent_reads_negative_raises(self):
        client = MagicMock()
        with pytest.raises(ConfigurationError):
            GroupReader(client, max_concurrent_reads=-1)

    @pytest.mark.asyncio
    async def test_read_many_empty_groups(self):
        client = AsyncMock()
        reader = GroupReader(client, max_concurrent_reads=1)
        result = await reader.read_many([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_decode_data_slice_too_short(self):
        """When raw data is shorter than expected for a point, raises CommunicationError"""
        client = AsyncMock()
        # Point at address 0, UInt16 needs 1 register, but we return empty data
        client.read_holding_registers = AsyncMock(return_value=[])
        point = _make_point("test_pt", 0)
        group = _make_group(0, 1, (point,))
        reader = GroupReader(client, max_concurrent_reads=1)
        with pytest.raises(CommunicationError):
            await reader.read(group)

    @pytest.mark.asyncio
    async def test_read_many_parallel_success(self):
        """Parallel read_many with max_concurrent_reads > 1"""
        client = AsyncMock()
        client.read_holding_registers = AsyncMock(return_value=[100])
        p1 = _make_point("a", 0)
        p2 = _make_point("b", 10)
        g1 = _make_group(0, 1, (p1,))
        g2 = _make_group(10, 1, (p2,))
        reader = GroupReader(client, max_concurrent_reads=3)
        result = await reader.read_many([g1, g2])
        assert result["a"] == 100
        assert result["b"] == 100

    @pytest.mark.asyncio
    async def test_read_many_gather_one_failure_propagates(self):
        """When one group fails in parallel mode, the error propagates"""
        client = AsyncMock()
        call_count = 0

        async def mock_read(address, count, unit_id):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("read failed")
            return [100]

        client.read_holding_registers = mock_read
        p1 = _make_point("a", 0)
        p2 = _make_point("b", 10)
        g1 = _make_group(0, 1, (p1,))
        g2 = _make_group(10, 1, (p2,))
        reader = GroupReader(client, max_concurrent_reads=3)
        with pytest.raises(Exception, match="read failed"):
            await reader.read_many([g1, g2])
