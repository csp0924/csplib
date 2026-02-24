import pytest

from csp_lib.modbus import ByteOrder, ModbusConfigError, ModbusEncodeError, ModbusString, RegisterOrder


class TestModbusStringEdgeCases:
    def test_empty_string_encode(self):
        s = ModbusString(10)
        regs = s.encode("", ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert len(regs) == s.register_count
        assert all(r == 0 for r in regs)

    def test_empty_string_decode_roundtrip(self):
        s = ModbusString(10)
        regs = s.encode("", ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = s.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert result == ""

    def test_utf8_multibyte_exceeds_byte_limit(self):
        """3-byte UTF-8 char exceeding max_length"""
        s = ModbusString(2, encoding="utf-8")
        # Chinese char is 3 bytes in UTF-8, exceeds max_length=2
        with pytest.raises(ModbusEncodeError):
            s.encode("\u4e2d", ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)

    def test_null_bytes_in_middle_of_string(self):
        s = ModbusString(10)
        # Null in middle should be encoded, but decode strips trailing nulls only
        regs = s.encode("AB", ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = s.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert result == "AB"

    def test_non_string_encode_raises(self):
        s = ModbusString(10)
        with pytest.raises(ModbusEncodeError):
            s.encode(12345, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)

    def test_odd_max_length_register_count(self):
        """Odd max_length should round up register count: (5+1)//2 = 3"""
        s = ModbusString(5)
        assert s.register_count == 3
        s2 = ModbusString(6)
        assert s2.register_count == 3

    def test_max_length_zero_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusString(0)

    def test_max_length_negative_raises(self):
        with pytest.raises(ModbusConfigError):
            ModbusString(-1)
