# =============== Equipment Transport Tests - Reader ===============
#
# GroupReader 群組讀取器單元測試
#
# 測試覆蓋：
# - 解碼邏輯（從 PointGrouper 遷移）
# - I/O 讀取整合
# - address_offset 處理
# - 各 FunctionCode 讀取

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from csp_lib.core.errors import CommunicationError, ConfigurationError
from csp_lib.equipment.core.pipeline import pipeline
from csp_lib.equipment.core.point import ReadPoint
from csp_lib.equipment.core.transform import ClampTransform, RoundTransform, ScaleTransform
from csp_lib.equipment.transport.base import ReadGroup
from csp_lib.equipment.transport.reader import GroupReader
from csp_lib.modbus import Float32, FunctionCode, Int32, UInt16
from csp_lib.modbus.exceptions import ModbusError

# ======================== Mock Fixtures ========================


@pytest.fixture
def mock_client() -> AsyncMock:
    """建立 Mock Modbus 客戶端"""
    client = AsyncMock()
    client.read_coils = AsyncMock(return_value=[True, False, True])
    client.read_discrete_inputs = AsyncMock(return_value=[True, False])
    client.read_holding_registers = AsyncMock(return_value=[100, 200, 300])
    client.read_input_registers = AsyncMock(return_value=[400, 500])
    return client


@pytest.fixture
def reader(mock_client: AsyncMock) -> GroupReader:
    """建立 GroupReader"""
    return GroupReader(client=mock_client)


@pytest.fixture
def reader_with_offset(mock_client: AsyncMock) -> GroupReader:
    """建立帶 offset 的 GroupReader（PLC 1-based）"""
    return GroupReader(client=mock_client, address_offset=1)


# ======================== Decode Tests (遷移自 PointGrouper) ========================


class TestGroupReaderDecode:
    """GroupReader._decode 測試（從 PointGrouper.decode 遷移）"""

    @pytest.fixture
    def reader_for_decode(self, mock_client: AsyncMock) -> GroupReader:
        """用於 decode 測試的 reader"""
        return GroupReader(client=mock_client)

    def test_decode_single_uint16(self, reader_for_decode: GroupReader):
        """解碼單一 UInt16 點位"""
        point = ReadPoint(name="value", address=100, data_type=UInt16())
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=1,
            points=(point,),
        )
        raw_data = [0x1234]

        result = reader_for_decode._decode(group, raw_data)

        assert result == {"value": 0x1234}

    def test_decode_single_int32(self, reader_for_decode: GroupReader):
        """解碼單一 Int32 點位"""
        point = ReadPoint(name="value", address=100, data_type=Int32())
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=2,
            points=(point,),
        )
        raw_data = [0x0000, 0x0001]

        result = reader_for_decode._decode(group, raw_data)

        assert result == {"value": 1}

    def test_decode_single_float32(self, reader_for_decode: GroupReader):
        """解碼單一 Float32 點位"""
        point = ReadPoint(name="temp", address=100, data_type=Float32())
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=2,
            points=(point,),
        )
        # IEEE 754: 10.0 = 0x41200000
        raw_data = [0x4120, 0x0000]

        result = reader_for_decode._decode(group, raw_data)

        assert abs(result["temp"] - 10.0) < 0.001

    def test_decode_multiple_consecutive_points(self, reader_for_decode: GroupReader):
        """解碼多個連續點位"""
        p1 = ReadPoint(name="a", address=100, data_type=UInt16())
        p2 = ReadPoint(name="b", address=101, data_type=UInt16())
        p3 = ReadPoint(name="c", address=102, data_type=UInt16())
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=3,
            points=(p1, p2, p3),
        )
        raw_data = [0x0001, 0x0002, 0x0003]

        result = reader_for_decode._decode(group, raw_data)

        assert result == {"a": 1, "b": 2, "c": 3}

    def test_decode_points_with_gap(self, reader_for_decode: GroupReader):
        """解碼有間隙的點位"""
        p1 = ReadPoint(name="first", address=100, data_type=UInt16())
        p2 = ReadPoint(name="last", address=104, data_type=UInt16())
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=5,
            points=(p1, p2),
        )
        # 中間有填充
        raw_data = [0x0001, 0xFFFF, 0xFFFF, 0xFFFF, 0x0005]

        result = reader_for_decode._decode(group, raw_data)

        assert result == {"first": 1, "last": 5}

    def test_decode_mixed_types(self, reader_for_decode: GroupReader):
        """解碼混合資料類型"""
        p1 = ReadPoint(name="status", address=100, data_type=UInt16())
        p2 = ReadPoint(name="power", address=101, data_type=Int32())
        p3 = ReadPoint(name="temp", address=103, data_type=Float32())
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=5,
            points=(p1, p2, p3),
        )
        # status: 1 reg, power: 2 regs, temp: 2 regs
        raw_data = [0x0001, 0x0000, 0x0064, 0x4120, 0x0000]

        result = reader_for_decode._decode(group, raw_data)

        assert result["status"] == 1
        assert result["power"] == 100
        assert abs(result["temp"] - 10.0) < 0.001

    def test_decode_with_offset(self, reader_for_decode: GroupReader):
        """群組起始地址與點位地址有偏移"""
        point = ReadPoint(name="value", address=105, data_type=UInt16())
        group = ReadGroup(
            function_code=3,
            start_address=100,  # 群組從 100 開始
            count=10,
            points=(point,),
        )
        raw_data = [0, 0, 0, 0, 0, 0x1234, 0, 0, 0, 0]  # index 5 = address 105

        result = reader_for_decode._decode(group, raw_data)

        assert result == {"value": 0x1234}

    def test_decode_insufficient_data_raises(self, reader_for_decode: GroupReader):
        """資料不足應拋 CommunicationError"""
        point = ReadPoint(name="value", address=100, data_type=Int32())
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=2,
            points=(point,),
        )
        raw_data = [0x0001]  # 只有 1 個，需要 2 個

        with pytest.raises(CommunicationError, match="資料不足"):
            reader_for_decode._decode(group, raw_data)

    def test_decode_empty_group(self, reader_for_decode: GroupReader):
        """空群組返回空字典"""
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=10,
            points=(),
        )
        raw_data = [0] * 10

        result = reader_for_decode._decode(group, raw_data)

        assert result == {}

    def test_decode_with_pipeline_scale(self, reader_for_decode: GroupReader):
        """解碼後套用縮放管線"""
        temp_pipeline = pipeline(
            ScaleTransform(magnitude=0.1, offset=-40),
        )
        point = ReadPoint(
            name="temperature",
            address=100,
            data_type=UInt16(),
            pipeline=temp_pipeline,
        )
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=1,
            points=(point,),
        )
        raw_data = [650]  # 650 * 0.1 - 40 = 25.0

        result = reader_for_decode._decode(group, raw_data)

        assert result["temperature"] == 25.0

    def test_decode_with_pipeline_multi_step(self, reader_for_decode: GroupReader):
        """解碼後套用多步驟管線（縮放+四捨五入+限幅）"""
        soc_pipeline = pipeline(
            ScaleTransform(magnitude=0.01),  # /100
            RoundTransform(decimals=1),
            ClampTransform(min_value=0.0, max_value=100.0),
        )
        point = ReadPoint(
            name="soc",
            address=100,
            data_type=UInt16(),
            pipeline=soc_pipeline,
        )
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=1,
            points=(point,),
        )

        # 正常值
        result = reader_for_decode._decode(group, [5500])
        assert result["soc"] == 55.0

        # 超出上限
        result = reader_for_decode._decode(group, [15000])
        assert result["soc"] == 100.0

        # 超出下限
        result = reader_for_decode._decode(group, [0])
        assert result["soc"] == 0.0

    def test_decode_multiple_points_with_different_pipelines(self, reader_for_decode: GroupReader):
        """多個點位各自套用不同 pipeline"""
        temp_pipeline = pipeline(ScaleTransform(magnitude=0.1, offset=-40))
        power_pipeline = pipeline(ScaleTransform(magnitude=0.001))  # W -> kW

        p1 = ReadPoint(
            name="temperature",
            address=100,
            data_type=UInt16(),
            pipeline=temp_pipeline,
        )
        p2 = ReadPoint(
            name="power",
            address=101,
            data_type=UInt16(),
            pipeline=power_pipeline,
        )
        group = ReadGroup(
            function_code=3,
            start_address=100,
            count=2,
            points=(p1, p2),
        )
        raw_data = [650, 5000]  # temp: 25°C, power: 5kW

        result = reader_for_decode._decode(group, raw_data)

        assert result["temperature"] == 25.0
        assert result["power"] == 5.0


# ======================== Read I/O Tests ========================


class TestGroupReaderRead:
    """GroupReader.read 整合測試"""

    @pytest.mark.asyncio
    async def test_read_holding_registers(self, reader: GroupReader, mock_client: AsyncMock):
        """讀取 Holding Registers (FC=3)"""
        point = ReadPoint(name="value", address=100, data_type=UInt16())
        group = ReadGroup(function_code=3, start_address=100, count=1, points=(point,))
        mock_client.read_holding_registers.return_value = [500]

        result = await reader.read(group)

        assert result == {"value": 500}
        mock_client.read_holding_registers.assert_called_once_with(100, 1, 1)

    @pytest.mark.asyncio
    async def test_read_input_registers(self, reader: GroupReader, mock_client: AsyncMock):
        """讀取 Input Registers (FC=4)"""
        point = ReadPoint(
            name="sensor",
            address=200,
            data_type=UInt16(),
            function_code=FunctionCode.READ_INPUT_REGISTERS,
        )
        group = ReadGroup(function_code=4, start_address=200, count=1, points=(point,))
        mock_client.read_input_registers.return_value = [1234]

        result = await reader.read(group)

        assert result == {"sensor": 1234}
        mock_client.read_input_registers.assert_called_once_with(200, 1, 1)

    @pytest.mark.asyncio
    async def test_read_coils(self, reader: GroupReader, mock_client: AsyncMock):
        """讀取 Coils (FC=1)"""
        point = ReadPoint(
            name="switch",
            address=0,
            data_type=UInt16(),
            function_code=FunctionCode.READ_COILS,
        )
        group = ReadGroup(function_code=1, start_address=0, count=1, points=(point,))
        mock_client.read_coils.return_value = [True]

        result = await reader.read(group)

        assert result == {"switch": True}
        mock_client.read_coils.assert_called_once_with(0, 1, 1)

    @pytest.mark.asyncio
    async def test_read_discrete_inputs(self, reader: GroupReader, mock_client: AsyncMock):
        """讀取 Discrete Inputs (FC=2)"""
        point = ReadPoint(
            name="alarm",
            address=10,
            data_type=UInt16(),
            function_code=FunctionCode.READ_DISCRETE_INPUTS,
        )
        group = ReadGroup(function_code=2, start_address=10, count=1, points=(point,))
        mock_client.read_discrete_inputs.return_value = [False]

        result = await reader.read(group)

        assert result == {"alarm": False}
        mock_client.read_discrete_inputs.assert_called_once_with(10, 1, 1)

    @pytest.mark.asyncio
    async def test_read_unsupported_function_code_raises(self, reader: GroupReader):
        """不支援的 FunctionCode 應拋 ConfigurationError"""
        group = ReadGroup(function_code=99, start_address=0, count=1, points=())

        with pytest.raises(ConfigurationError, match="不支援"):
            await reader.read(group)


# ======================== Address Offset Tests ========================


class TestGroupReaderAddressOffset:
    """address_offset 測試"""

    @pytest.mark.asyncio
    async def test_offset_applied_to_read(self, reader_with_offset: GroupReader, mock_client: AsyncMock):
        """讀取時應套用 address_offset"""
        point = ReadPoint(name="value", address=100, data_type=UInt16())
        group = ReadGroup(function_code=3, start_address=100, count=1, points=(point,))
        mock_client.read_holding_registers.return_value = [500]

        await reader_with_offset.read(group)

        # 100 + 1 = 101
        mock_client.read_holding_registers.assert_called_once_with(101, 1, 1)


# ======================== Read Many Tests ========================


class TestGroupReaderReadMany:
    """GroupReader.read_many 測試"""

    @pytest.mark.asyncio
    async def test_read_many_groups(self, reader: GroupReader, mock_client: AsyncMock):
        """讀取多個群組並合併結果"""
        p1 = ReadPoint(name="a", address=100, data_type=UInt16())
        p2 = ReadPoint(name="b", address=200, data_type=UInt16())

        group1 = ReadGroup(function_code=3, start_address=100, count=1, points=(p1,))
        group2 = ReadGroup(function_code=3, start_address=200, count=1, points=(p2,))

        mock_client.read_holding_registers.side_effect = [[100], [200]]

        result = await reader.read_many([group1, group2])

        assert result == {"a": 100, "b": 200}
        assert mock_client.read_holding_registers.call_count == 2

    @pytest.mark.asyncio
    async def test_read_many_empty_list(self, reader: GroupReader):
        """空群組列表回傳空字典"""
        result = await reader.read_many([])

        assert result == {}

    @pytest.mark.asyncio
    async def test_read_many_merges_overlapping_keys(self, reader: GroupReader, mock_client: AsyncMock):
        """後面群組的值會覆蓋前面（相同 key）"""
        p1 = ReadPoint(name="value", address=100, data_type=UInt16())
        p2 = ReadPoint(name="value", address=200, data_type=UInt16())

        group1 = ReadGroup(function_code=3, start_address=100, count=1, points=(p1,))
        group2 = ReadGroup(function_code=3, start_address=200, count=1, points=(p2,))

        mock_client.read_holding_registers.side_effect = [[111], [222]]

        result = await reader.read_many([group1, group2])

        # 後者覆蓋前者
        assert result == {"value": 222}


# ======================== Exception Propagation Tests ========================


class TestGroupReaderExceptions:
    """異常處理測試"""

    @pytest.mark.asyncio
    async def test_modbus_error_wrapped_as_communication_error(self, reader: GroupReader, mock_client: AsyncMock):
        """ModbusError 應被包裝為 CommunicationError"""
        group = ReadGroup(function_code=3, start_address=0, count=1, points=())
        mock_client.read_holding_registers.side_effect = ModbusError("連線逾時")

        with pytest.raises(CommunicationError, match="連線逾時") as exc_info:
            await reader.read(group)

        # 確認 exception chaining
        assert isinstance(exc_info.value.__cause__, ModbusError)

    def test_init_invalid_max_concurrent_reads(self, mock_client: AsyncMock):
        """max_concurrent_reads < 1 應拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="max_concurrent_reads"):
            GroupReader(client=mock_client, max_concurrent_reads=0)
