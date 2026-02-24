# =============== Modbus Tests - Enums ===============
#
# 列舉模組單元測試

from csp_lib.modbus import (
    ByteOrder,
    FunctionCode,
    Parity,
    RegisterOrder,
)


class TestByteOrderEnum:
    """ByteOrder 列舉測試"""

    def test_big_endian_value(self):
        assert ByteOrder.BIG_ENDIAN.value == ">"

    def test_little_endian_value(self):
        assert ByteOrder.LITTLE_ENDIAN.value == "<"

    def test_all_members(self):
        assert len(ByteOrder) == 2


class TestRegisterOrderEnum:
    """RegisterOrder 列舉測試"""

    def test_high_first_value(self):
        assert RegisterOrder.HIGH_FIRST.value == "high"

    def test_low_first_value(self):
        assert RegisterOrder.LOW_FIRST.value == "low"

    def test_all_members(self):
        assert len(RegisterOrder) == 2


class TestParityEnum:
    """Parity 列舉測試"""

    def test_none_value(self):
        assert Parity.NONE.value == "N"

    def test_even_value(self):
        assert Parity.EVEN.value == "E"

    def test_odd_value(self):
        assert Parity.ODD.value == "O"

    def test_all_members(self):
        assert len(Parity) == 3


class TestFunctionCodeEnum:
    """FunctionCode 列舉測試"""

    def test_read_coils(self):
        assert FunctionCode.READ_COILS == 0x01

    def test_read_discrete_inputs(self):
        assert FunctionCode.READ_DISCRETE_INPUTS == 0x02

    def test_read_holding_registers(self):
        assert FunctionCode.READ_HOLDING_REGISTERS == 0x03

    def test_read_input_registers(self):
        assert FunctionCode.READ_INPUT_REGISTERS == 0x04

    def test_write_single_coil(self):
        assert FunctionCode.WRITE_SINGLE_COIL == 0x05

    def test_write_single_register(self):
        assert FunctionCode.WRITE_SINGLE_REGISTER == 0x06

    def test_write_multiple_coils(self):
        assert FunctionCode.WRITE_MULTIPLE_COILS == 0x0F

    def test_write_multiple_registers(self):
        assert FunctionCode.WRITE_MULTIPLE_REGISTERS == 0x10

    def test_all_members(self):
        assert len(FunctionCode) == 8

    def test_is_int(self):
        # FunctionCode 繼承 IntEnum，可直接用於整數運算
        assert FunctionCode.READ_HOLDING_REGISTERS + 1 == 4
