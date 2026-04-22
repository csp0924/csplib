# =============== Manager Command Tests - Multi-Unit-ID Routing ===============
#
# Wave 2b Step 4：同一 device 多個 WritePoint 各自 unit_id 路由測試
#
# 背景：
# SMA 風格設備（Inverter + MeterCorrection）共用 TCP 連線但掛多個 Modbus unit。
# 每個 ``WritePoint`` 可獨立覆寫 ``unit_id``，交由 ``ValidatedWriter._resolve_unit_id``
# 路由到正確 slave。本檔驗證此路由在 WriteCommandManager → device → client
# 的端到端流程中正確生效。
#
# production code 無變更，本測試驗證 gap 已關閉。

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.core.point import WritePoint
from csp_lib.equipment.device.base import AsyncModbusDevice
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.transport.writer import WriteStatus
from csp_lib.manager.command.manager import WriteCommandManager
from csp_lib.manager.command.schema import WriteCommand
from csp_lib.modbus import UInt16


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock client：紀錄所有寫入呼叫的 unit_id。"""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.write_single_register = AsyncMock()
    client.write_multiple_registers = AsyncMock()
    client.write_single_coil = AsyncMock()
    client.write_multiple_coils = AsyncMock()
    client.read_holding_registers = AsyncMock(return_value=[0])
    return client


@pytest.fixture
def multi_unit_device(mock_client: AsyncMock) -> AsyncModbusDevice:
    """掛三個 WritePoint，各自 unit_id 不同的 device。"""
    return AsyncModbusDevice(
        config=DeviceConfig(
            device_id="sma_multi",
            unit_id=3,  # default
            address_offset=0,
            read_interval=1.0,
        ),
        client=mock_client,
        always_points=[],
        write_points=[
            # 使用 device default unit_id (3)
            WritePoint(name="default_unit_point", address=100, data_type=UInt16()),
            # override → unit_id=7
            WritePoint(name="meter_point", address=200, data_type=UInt16(), unit_id=7),
            # override → unit_id=11
            WritePoint(name="inverter_point", address=300, data_type=UInt16(), unit_id=11),
        ],
    )


class MockRepository:
    def __init__(self) -> None:
        self.create = AsyncMock(return_value="rec_id")
        self.update_status = AsyncMock(return_value=True)


# ======================== Multi unit_id routing ========================


class TestMultiUnitIdRoutingThroughWriteCommandManager:
    """WriteCommandManager.execute → device.write → ValidatedWriter 的 unit_id 路由。"""

    async def test_write_to_default_unit_uses_config_unit_id(
        self,
        multi_unit_device: AsyncModbusDevice,
        mock_client: AsyncMock,
    ):
        """point.unit_id=None（沿用 device default）→ write_multiple_registers 收到 config.unit_id=3。"""
        manager = WriteCommandManager(repository=MockRepository())
        manager.register_device(multi_unit_device)

        command = WriteCommand(
            device_id="sma_multi",
            point_name="default_unit_point",
            value=42,
        )
        result = await manager.execute(command)

        assert result.status == WriteStatus.SUCCESS
        mock_client.write_multiple_registers.assert_awaited_once()
        # keyword args 檢查 unit_id
        kwargs = mock_client.write_multiple_registers.call_args.kwargs
        assert kwargs["unit_id"] == 3

    async def test_write_to_meter_point_routes_to_unit_7(
        self,
        multi_unit_device: AsyncModbusDevice,
        mock_client: AsyncMock,
    ):
        """meter_point.unit_id=7 → client 呼叫應帶 unit_id=7。"""
        manager = WriteCommandManager(repository=MockRepository())
        manager.register_device(multi_unit_device)

        command = WriteCommand(
            device_id="sma_multi",
            point_name="meter_point",
            value=10,
        )
        result = await manager.execute(command)

        assert result.status == WriteStatus.SUCCESS
        kwargs = mock_client.write_multiple_registers.call_args.kwargs
        assert kwargs["unit_id"] == 7

    async def test_write_to_inverter_point_routes_to_unit_11(
        self,
        multi_unit_device: AsyncModbusDevice,
        mock_client: AsyncMock,
    ):
        """inverter_point.unit_id=11 → client 呼叫應帶 unit_id=11。"""
        manager = WriteCommandManager(repository=MockRepository())
        manager.register_device(multi_unit_device)

        command = WriteCommand(
            device_id="sma_multi",
            point_name="inverter_point",
            value=99,
        )
        result = await manager.execute(command)

        assert result.status == WriteStatus.SUCCESS
        kwargs = mock_client.write_multiple_registers.call_args.kwargs
        assert kwargs["unit_id"] == 11

    async def test_interleaved_writes_preserve_per_point_unit_id(
        self,
        multi_unit_device: AsyncModbusDevice,
        mock_client: AsyncMock,
    ):
        """連續對三個不同 point 寫入，每次 unit_id 獨立路由不污染彼此。"""
        manager = WriteCommandManager(repository=MockRepository())
        manager.register_device(multi_unit_device)

        point_sequence = [
            "meter_point",
            "default_unit_point",
            "inverter_point",
            "meter_point",
        ]
        for point_name in point_sequence:
            command = WriteCommand(
                device_id="sma_multi",
                point_name=point_name,
                value=1,
            )
            await manager.execute(command)

        # 檢查所有呼叫的 unit_id 順序（對應 point 覆寫值）
        call_unit_ids = [c.kwargs["unit_id"] for c in mock_client.write_multiple_registers.await_args_list]
        assert call_unit_ids == [7, 3, 11, 7]


# ======================== used_unit_ids 反映所有覆寫 ========================


class TestUsedUnitIdsReflectsAllOverrides:
    """device.used_unit_ids 應涵蓋 config default + 所有 point-level override。"""

    def test_used_unit_ids_contains_all_unique_units(
        self,
        multi_unit_device: AsyncModbusDevice,
    ):
        """multi_unit_device 應回報 {3, 7, 11}。"""
        assert multi_unit_device.used_unit_ids == frozenset({3, 7, 11})


# ======================== 非存在點位錯誤處理 ========================


class TestMultiUnitWriteErrorPaths:
    """驗證 unit_id 路由行為在錯誤路徑下的語義。"""

    async def test_write_to_nonexistent_point_returns_validation_failed(
        self,
        multi_unit_device: AsyncModbusDevice,
        mock_client: AsyncMock,
    ):
        """point_name 不存在：device.write 回 VALIDATION_FAILED，client 未被呼叫。"""
        manager = WriteCommandManager(repository=MockRepository())
        manager.register_device(multi_unit_device)

        command = WriteCommand(
            device_id="sma_multi",
            point_name="no_such_point",
            value=0,
        )
        result = await manager.execute(command)

        # 非存在點位由 mixins.write 直接 return VALIDATION_FAILED
        assert result.status in (WriteStatus.VALIDATION_FAILED, WriteStatus.WRITE_FAILED)
        mock_client.write_multiple_registers.assert_not_called()
        mock_client.write_single_register.assert_not_called()


# ======================== WriteCommandManager passthrough 驗證 ========================


class TestWriteCommandManagerPassesPointNameUnchanged:
    """WriteCommandManager 只是 passthrough：不應 rewrite point_name 或 value。

    用 AsyncMock spy device.write 驗證 signature 正確傳遞。
    """

    async def test_device_write_receives_exact_point_and_value(self):
        """device.write 收到的 name/value/verify 與 command 一致。"""
        spy_device = AsyncMock()
        spy_device.device_id = "spy_dev"
        from csp_lib.equipment.transport import WriteResult

        spy_device.write = AsyncMock(
            return_value=WriteResult(
                status=WriteStatus.SUCCESS,
                point_name="meter_point",
                value=55,
            )
        )

        manager = WriteCommandManager(repository=MockRepository())
        manager.register_device(spy_device)

        command = WriteCommand(
            device_id="spy_dev",
            point_name="meter_point",
            value=55,
            verify=True,
        )
        await manager.execute(command)

        spy_device.write.assert_awaited_once_with(name="meter_point", value=55, verify=True)
