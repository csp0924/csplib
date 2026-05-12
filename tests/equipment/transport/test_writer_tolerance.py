# =============== ValidatedWriter._values_equal 浮點容差測試 ===============
#
# Bug Fix Protocol #10 (a)-class:
#   _values_equal 原本使用 hard-coded 1e-6 absolute tolerance,
#   對工業設備典型 setpoint 量級 (kW / V / Hz·1e3, 1e3~1e7 範圍) 而言,
#   遠比設備內部 float32 儲存精度 (LSB ≈ value × 5.96e-8) 還緊,
#   導致 verify=True 的 round-trip 永遠 false-fail。
#
# 修正後採用 math.isclose(rel_tol=1e-6, abs_tol=1e-9):
#   - rel_tol=1e-6 給大數值合理相對精度 (1ppm)
#   - abs_tol=1e-9 給近零值安全絕對下限, 避免 0.0 vs 1e-12 假成功
#
# 本檔覆蓋:
#   - 大數量級 float32 round-trip (新行為, 修正前 FAIL)
#   - 近零值仍維持嚴格 (abs_tol floor)
#   - 完全相等
#   - 明顯不等 (應 FAIL)

from __future__ import annotations

import struct
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.core.point import WritePoint
from csp_lib.equipment.transport.writer import ValidatedWriter, WriteStatus
from csp_lib.modbus import Float32, FunctionCode

# ======================== 純函式行為 ========================


class TestValuesEqualToleranceUnit:
    """_values_equal 在不同量級下的容差行為"""

    def test_large_magnitude_float32_round_trip_should_pass(self):
        """工業 setpoint (1e6 量級) 經 float32 round-trip 後應視為相等。

        修正前: abs(delta) ≈ 0.06 >> 1e-6 → False (誤判)
        修正後: rel_tol=1e-6 容忍 ~1.23 的絕對誤差 → True
        """
        expected = 1_234_567.89
        actual = struct.unpack(">f", struct.pack(">f", expected))[0]
        # 雙浮點看到的 delta 約 0.06 ~ 0.12
        delta = abs(expected - actual)
        assert delta > 1e-3, f"sanity: float32 round-trip 應有可觀 delta, got {delta}"
        assert ValidatedWriter._values_equal(expected, actual), (
            f"1e6 量級 + float32 storage delta={delta} 應在 rel_tol=1e-6 內被視為相等"
        )

    def test_kw_range_setpoint_round_trip(self):
        """典型 kW 級 setpoint (~5000 kW) 經 float32 也應 pass。"""
        expected = 5234.567
        actual = struct.unpack(">f", struct.pack(">f", expected))[0]
        assert ValidatedWriter._values_equal(expected, actual)

    def test_near_zero_abs_tol_floor_holds(self):
        """近零值: abs_tol=1e-9 floor 防止 rel_tol 把 0 與 1e-12 視為相等以外的差距放過。"""
        # rel_tol 在 0 附近退化為 0, 必須依賴 abs_tol
        assert ValidatedWriter._values_equal(0.0, 1e-10)  # 在 1e-9 floor 內
        assert not ValidatedWriter._values_equal(0.0, 1e-6)  # 遠超 1e-9 floor

    def test_exact_equality_still_holds(self):
        """完全相等仍應為 True。"""
        assert ValidatedWriter._values_equal(1234.5678, 1234.5678)

    def test_clearly_unequal_still_fails(self):
        """量級相差過大或值明顯不同仍應 False。"""
        # rel_tol=1e-6: 1.0 vs 1.001 → 相對誤差 ~1e-3 >> 1e-6
        assert not ValidatedWriter._values_equal(1.0, 1.001)
        # 大值上, 1% 偏差也應 False
        assert not ValidatedWriter._values_equal(1_000_000.0, 1_010_000.0)


# ======================== 透過 ValidatedWriter.write(verify=True) 整合 ========================


class TestVerifyFloat32RoundTrip:
    """整合行為: 寫入工業 setpoint, device 端 float32 storage round-trip 應 verify 成功"""

    @pytest.fixture
    def mock_client_float32_storage(self) -> AsyncMock:
        """模擬 device 端用 float32 儲存的 Modbus 客戶端。

        write_multiple_registers 收到的暫存器, 我們解回 float, truncate 成 float32,
        再以 float32 編碼回兩個 16-bit word, 供 read_holding_registers 回吐。
        """
        client = AsyncMock()
        storage: dict[int, list[int]] = {}

        async def write_multi(address: int, values: list[int], unit_id: int = 1) -> None:
            # 收到的是 Float32 encode 後的 2 個 word (本就 float32 精度)
            storage[address] = list(values)

        async def read_holding(address: int, count: int, unit_id: int = 1) -> list[int]:
            return list(storage.get(address, [0] * count))[:count]

        client.write_multiple_registers = AsyncMock(side_effect=write_multi)
        client.read_holding_registers = AsyncMock(side_effect=read_holding)
        return client

    @pytest.mark.asyncio
    async def test_large_kw_setpoint_verify_passes(self, mock_client_float32_storage: AsyncMock):
        """寫入 1.23e6 量級 setpoint, verify=True 應 SUCCESS (修正前 VERIFICATION_FAILED)。"""
        writer = ValidatedWriter(client=mock_client_float32_storage)
        point = WritePoint(
            name="active_power_kw",
            address=100,
            data_type=Float32(),
            function_code=FunctionCode.WRITE_MULTIPLE_REGISTERS,
        )

        result = await writer.write(point, 1_234_567.89, verify=True)

        assert result.status == WriteStatus.SUCCESS, (
            f"大量級 setpoint 經 Float32 round-trip 應 verify 通過, got {result.status}: {result.error_message}"
        )

    @pytest.mark.asyncio
    async def test_voltage_setpoint_verify_passes(self, mock_client_float32_storage: AsyncMock):
        """電壓 setpoint (~22000 V) verify 應 SUCCESS。"""
        writer = ValidatedWriter(client=mock_client_float32_storage)
        point = WritePoint(
            name="voltage_v",
            address=200,
            data_type=Float32(),
            function_code=FunctionCode.WRITE_MULTIPLE_REGISTERS,
        )

        result = await writer.write(point, 22050.5, verify=True)

        assert result.status == WriteStatus.SUCCESS, (
            f"電壓 setpoint Float32 round-trip 應 verify 通過, got {result.status}: {result.error_message}"
        )
