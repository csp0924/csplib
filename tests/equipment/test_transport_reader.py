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


class TestGroupReaderUnitIdResolution:
    """GroupReader: group.unit_id 覆寫 default，fallback 語義"""

    @pytest.mark.asyncio
    async def test_uses_group_unit_id_when_set(self, mock_client: AsyncMock):
        reader = GroupReader(client=mock_client, unit_id=1)
        group = ReadGroup(function_code=3, start_address=0, count=1, unit_id=7)
        await reader.read(group)
        call = mock_client.read_holding_registers.call_args
        # client.read_holding_registers(address, count, unit_id)
        assert call.args[2] == 7

    @pytest.mark.asyncio
    async def test_falls_back_to_default_when_group_unit_id_none(self, mock_client: AsyncMock):
        reader = GroupReader(client=mock_client, unit_id=4)
        group = ReadGroup(function_code=3, start_address=0, count=1)
        await reader.read(group)
        assert mock_client.read_holding_registers.call_args.args[2] == 4

    @pytest.mark.asyncio
    async def test_fallback_applies_to_all_function_codes(self, mock_client: AsyncMock):
        reader = GroupReader(client=mock_client, unit_id=2)
        for fc, mock_fn_name in [
            (FunctionCode.READ_COILS, "read_coils"),
            (FunctionCode.READ_DISCRETE_INPUTS, "read_discrete_inputs"),
            (FunctionCode.READ_INPUT_REGISTERS, "read_input_registers"),
        ]:
            mock_fn = getattr(mock_client, mock_fn_name)
            mock_fn.reset_mock()
            group = ReadGroup(function_code=fc, start_address=0, count=1, unit_id=9)
            await reader.read(group)
            assert mock_fn.call_args.args[2] == 9


async def _wait_for(pred, timeout: float = 2.0, interval: float = 0.01) -> None:
    """Poll until pred() is true or timeout — 參考 lesson async-test-state-race"""
    import asyncio

    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


class TestGroupReaderPerUnitSemaphore:
    """GroupReader: per-unit_id semaphore 保證同 uid 請求串列、跨 uid 並行"""

    @pytest.mark.asyncio
    async def test_same_unit_id_requests_are_serialized(self, mock_client: AsyncMock):
        import asyncio

        in_flight = 0
        max_seen = 0
        event = asyncio.Event()

        async def blocking_read(address, count, unit_id):
            nonlocal in_flight, max_seen
            in_flight += 1
            max_seen = max(max_seen, in_flight)
            await event.wait()
            in_flight -= 1
            return [0] * count

        mock_client.read_holding_registers = AsyncMock(side_effect=blocking_read)

        reader = GroupReader(client=mock_client, max_concurrent_reads=4)
        g = ReadGroup(function_code=3, start_address=0, count=1, unit_id=5)
        tasks = [asyncio.create_task(reader.read(g)) for _ in range(3)]

        # 等第一個 task 進入 blocking_read
        await _wait_for(lambda: in_flight == 1)
        # 放一小段時間讓剩餘 tasks 有機會跑到 per-unit semaphore 的 acquire；
        # 若 production 未序列化，max_seen 會在此期間跳到 > 1
        for _ in range(5):
            await asyncio.sleep(0.01)
        assert in_flight == 1
        assert mock_client.read_holding_registers.call_count == 1

        event.set()
        await asyncio.gather(*tasks, return_exceptions=False)
        # 同一 unit_id 不論發送幾次，in-flight 最多 1
        assert max_seen == 1

    @pytest.mark.asyncio
    async def test_different_unit_ids_can_run_concurrently(self, mock_client: AsyncMock):
        import asyncio

        in_flight = 0
        max_seen = 0
        event = asyncio.Event()

        async def blocking_read(address, count, unit_id):
            nonlocal in_flight, max_seen
            in_flight += 1
            max_seen = max(max_seen, in_flight)
            await event.wait()
            in_flight -= 1
            return [0] * count

        mock_client.read_holding_registers = AsyncMock(side_effect=blocking_read)

        reader = GroupReader(client=mock_client, max_concurrent_reads=4)
        tasks = [
            asyncio.create_task(reader.read(ReadGroup(function_code=3, start_address=0, count=1, unit_id=uid)))
            for uid in (1, 2, 3)
        ]

        # 不同 unit_id 共 3 個 semaphore，應可全部並行（max_concurrent_reads=4 不限制）
        await _wait_for(lambda: in_flight == 3)
        assert max_seen == 3

        event.set()
        await asyncio.gather(*tasks)
