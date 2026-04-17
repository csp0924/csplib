# =============== Modbus Tests - Register Helpers ===============
#
# 針對 `csp_lib/modbus/types/_register_helpers.py` 的單元測試
#
# 重現 BUG-001：`assemble_from_registers()` 與 `split_to_registers()`
# 在 register_count 不為 2 / 4 時的 fallback 路徑忽略 LOW_FIRST order。
#
# 修復前：register_count=6 時 LOW_FIRST 與 HIGH_FIRST 結果一致
# 修復後：register_count=6 時 LOW_FIRST 會 reverse registers

from __future__ import annotations

import struct

import pytest

from csp_lib.modbus.enums import ByteOrder, RegisterOrder
from csp_lib.modbus.types._register_helpers import assemble_from_registers, split_to_registers


class TestSplitToRegistersFallback:
    """split_to_registers 在 register_count=6 (fallback) 時應尊重 register_order"""

    def test_split_6_registers_low_first_should_reverse(self):
        """
        register_count=6, LOW_FIRST 應反轉 registers。

        packed = struct.pack(">HHHHHH", 1, 2, 3, 4, 5, 6)
        - HIGH_FIRST 預期：[1, 2, 3, 4, 5, 6]
        - LOW_FIRST  預期：[6, 5, 4, 3, 2, 1]

        修復前：fallback 未處理 LOW_FIRST，兩者會相同 → 此測試 FAIL
        """
        packed = struct.pack(">HHHHHH", 1, 2, 3, 4, 5, 6)

        result_high = split_to_registers(packed, 6, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result_low = split_to_registers(packed, 6, ByteOrder.BIG_ENDIAN, RegisterOrder.LOW_FIRST)

        assert result_high == [1, 2, 3, 4, 5, 6]
        assert result_low == [6, 5, 4, 3, 2, 1]

    def test_split_6_registers_order_differs(self):
        """register_count=6: LOW_FIRST 必須與 HIGH_FIRST 結果不同"""
        packed = struct.pack(">HHHHHH", 0xAAAA, 0xBBBB, 0xCCCC, 0xDDDD, 0xEEEE, 0xFFFF)

        result_high = split_to_registers(packed, 6, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result_low = split_to_registers(packed, 6, ByteOrder.BIG_ENDIAN, RegisterOrder.LOW_FIRST)

        assert result_high != result_low, "fallback 路徑未處理 LOW_FIRST"


class TestAssembleFromRegistersFallback:
    """assemble_from_registers 在 register_count=6 (fallback) 時應尊重 register_order"""

    def test_assemble_6_registers_low_first_should_reverse(self):
        """
        register_count=6, LOW_FIRST 應反轉 registers 再組合。

        registers = [1, 2, 3, 4, 5, 6]
        - HIGH_FIRST 預期：struct.pack(">HHHHHH", 1, 2, 3, 4, 5, 6)
        - LOW_FIRST  預期：struct.pack(">HHHHHH", 6, 5, 4, 3, 2, 1)

        修復前：fallback 未 reverse，兩者會相同 → 此測試 FAIL
        """
        regs = [1, 2, 3, 4, 5, 6]

        result_high = assemble_from_registers(regs, 6, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result_low = assemble_from_registers(regs, 6, ByteOrder.BIG_ENDIAN, RegisterOrder.LOW_FIRST)

        assert result_high == struct.pack(">HHHHHH", 1, 2, 3, 4, 5, 6)
        assert result_low == struct.pack(">HHHHHH", 6, 5, 4, 3, 2, 1)

    def test_assemble_6_registers_order_differs(self):
        """register_count=6: LOW_FIRST 必須與 HIGH_FIRST 結果不同"""
        regs = [0x1111, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666]

        result_high = assemble_from_registers(regs, 6, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result_low = assemble_from_registers(regs, 6, ByteOrder.BIG_ENDIAN, RegisterOrder.LOW_FIRST)

        assert result_high != result_low, "fallback 路徑未處理 LOW_FIRST"


class TestRoundTripFallback:
    """split / assemble round-trip 應保持 identity（即使在 fallback 路徑）"""

    @pytest.mark.parametrize("order", [RegisterOrder.HIGH_FIRST, RegisterOrder.LOW_FIRST])
    def test_roundtrip_6_registers(self, order: RegisterOrder):
        """
        對 register_count=6，assemble(split(x)) 應 = x。

        split 和 assemble 的 bug 會相互抵消（都缺 reverse），所以 round-trip
        依然通過。此測試作為輔助，確保修復後 round-trip 不被破壞。
        """
        original = struct.pack(">HHHHHH", 100, 200, 300, 400, 500, 600)
        regs = split_to_registers(original, 6, ByteOrder.BIG_ENDIAN, order)
        result = assemble_from_registers(regs, 6, ByteOrder.BIG_ENDIAN, order)
        assert result == original
