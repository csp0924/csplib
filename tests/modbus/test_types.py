# =============== Modbus Tests - Types ===============
#
# 資料類型單元測試

import pytest

from csp_lib.modbus import (
    ByteOrder,
    RegisterOrder,
    ModbusCodec,
    ModbusEncodeError,
    ModbusDecodeError,
    ModbusConfigError,
    # Numeric types
    Int16,
    UInt16,
    Int32,
    UInt32,
    Int64,
    UInt64,
    Float32,
    Float64,
    # Dynamic types
    DynamicInt,
    DynamicUInt,
    # String type
    ModbusString,
)

class TestInt16:
    """Int16 測試"""

    def test_register_count(self):
        assert Int16().register_count == 1

    def test_encode_positive(self):
        codec = ModbusCodec()
        assert codec.encode(Int16(), 1234) == [1234]

    def test_encode_negative(self):
        codec = ModbusCodec()
        result = codec.encode(Int16(), -1)
        assert result == [65535]  # 0xFFFF in two's complement

    def test_encode_min_max(self):
        codec = ModbusCodec()
        assert codec.encode(Int16(), -32768) == [32768]  # 0x8000
        assert codec.encode(Int16(), 32767) == [32767]  # 0x7FFF

    def test_encode_out_of_range(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError):
            codec.encode(Int16(), 32768)
        with pytest.raises(ModbusEncodeError):
            codec.encode(Int16(), -32769)

    def test_decode_positive(self):
        codec = ModbusCodec()
        assert codec.decode(Int16(), [1234]) == 1234

    def test_decode_negative(self):
        codec = ModbusCodec()
        assert codec.decode(Int16(), [65535]) == -1
        assert codec.decode(Int16(), [32768]) == -32768

    def test_roundtrip(self):
        codec = ModbusCodec()
        for value in [-32768, -1, 0, 1, 32767]:
            registers = codec.encode(Int16(), value)
            assert codec.decode(Int16(), registers) == value


class TestUInt16:
    """UInt16 測試"""

    def test_register_count(self):
        assert UInt16().register_count == 1

    def test_encode_decode(self):
        codec = ModbusCodec()
        for value in [0, 1, 32768, 65535]:
            registers = codec.encode(UInt16(), value)
            assert registers == [value]
            assert codec.decode(UInt16(), registers) == value

    def test_encode_out_of_range(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError):
            codec.encode(UInt16(), -1)
        with pytest.raises(ModbusEncodeError):
            codec.encode(UInt16(), 65536)


class TestInt32:
    """Int32 測試"""

    def test_register_count(self):
        assert Int32().register_count == 2

    def test_encode_positive(self):
        codec = ModbusCodec()  # BIG_ENDIAN, HIGH_FIRST
        result = codec.encode(Int32(), 0x12345678)
        assert result == [0x1234, 0x5678]

    def test_encode_negative(self):
        codec = ModbusCodec()
        result = codec.encode(Int32(), -1)
        assert result == [0xFFFF, 0xFFFF]

    def test_register_order_low_first(self):
        codec = ModbusCodec()
        result = codec.encode(Int32(), 0x12345678, register_order=RegisterOrder.LOW_FIRST)
        assert result == [0x5678, 0x1234]  # 順序反轉

    def test_roundtrip(self):
        codec = ModbusCodec()
        for value in [-2147483648, -1, 0, 1, 2147483647]:
            registers = codec.encode(Int32(), value)
            assert codec.decode(Int32(), registers) == value


class TestUInt32:
    """UInt32 測試"""

    def test_register_count(self):
        assert UInt32().register_count == 2

    def test_encode_decode(self):
        codec = ModbusCodec()
        for value in [0, 0x12345678, 0xFFFFFFFF]:
            registers = codec.encode(UInt32(), value)
            assert codec.decode(UInt32(), registers) == value

    def test_encode_out_of_range(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError):
            codec.encode(UInt32(), -1)
        with pytest.raises(ModbusEncodeError):
            codec.encode(UInt32(), 0x100000000)


class TestFloat32:
    """Float32 測試"""

    def test_register_count(self):
        assert Float32().register_count == 2

    def test_encode_decode(self):
        codec = ModbusCodec()
        for value in [0.0, 1.0, -1.0, 3.14159, 1e10]:
            registers = codec.encode(Float32(), value)
            decoded = codec.decode(Float32(), registers)
            assert abs(decoded - value) < 1e-5 or abs(decoded - value) / abs(value) < 1e-5

    def test_accepts_int(self):
        codec = ModbusCodec()
        registers = codec.encode(Float32(), 42)
        decoded = codec.decode(Float32(), registers)
        assert abs(decoded - 42.0) < 1e-5


class TestInt64:
    """Int64 測試"""

    def test_register_count(self):
        assert Int64().register_count == 4

    def test_encode_positive(self):
        codec = ModbusCodec()
        result = codec.encode(Int64(), 0x123456789ABCDEF0)
        assert len(result) == 4
        # HIGH_FIRST: [0x1234, 0x5678, 0x9ABC, 0xDEF0]
        assert result == [0x1234, 0x5678, 0x9ABC, 0xDEF0]

    def test_encode_negative(self):
        codec = ModbusCodec()
        result = codec.encode(Int64(), -1)
        assert result == [0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF]

    def test_register_order_low_first(self):
        codec = ModbusCodec()
        result = codec.encode(Int64(), 0x123456789ABCDEF0, register_order=RegisterOrder.LOW_FIRST)
        # LOW_FIRST: 順序反轉
        assert result == [0xDEF0, 0x9ABC, 0x5678, 0x1234]

    def test_roundtrip(self):
        codec = ModbusCodec()
        min_val = -9223372036854775808
        max_val = 9223372036854775807
        for value in [min_val, -1, 0, 1, max_val]:
            registers = codec.encode(Int64(), value)
            assert codec.decode(Int64(), registers) == value

    def test_encode_out_of_range(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError):
            codec.encode(Int64(), 9223372036854775808)
        with pytest.raises(ModbusEncodeError):
            codec.encode(Int64(), -9223372036854775809)


class TestUInt64:
    """UInt64 測試"""

    def test_register_count(self):
        assert UInt64().register_count == 4

    def test_encode_decode(self):
        codec = ModbusCodec()
        for value in [0, 0x123456789ABCDEF0, 0xFFFFFFFFFFFFFFFF]:
            registers = codec.encode(UInt64(), value)
            assert len(registers) == 4
            assert codec.decode(UInt64(), registers) == value

    def test_encode_out_of_range(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError):
            codec.encode(UInt64(), -1)
        with pytest.raises(ModbusEncodeError):
            codec.encode(UInt64(), 0x10000000000000000)


class TestFloat64:
    """Float64 測試"""

    def test_register_count(self):
        assert Float64().register_count == 4

    def test_encode_decode(self):
        codec = ModbusCodec()
        for value in [0.0, 1.0, -1.0, 3.141592653589793, 1e100, -1e-100]:
            registers = codec.encode(Float64(), value)
            assert len(registers) == 4
            decoded = codec.decode(Float64(), registers)
            if value == 0.0:
                assert decoded == 0.0
            else:
                assert abs(decoded - value) / abs(value) < 1e-14

    def test_accepts_int(self):
        codec = ModbusCodec()
        registers = codec.encode(Float64(), 42)
        decoded = codec.decode(Float64(), registers)
        assert decoded == 42.0

    def test_register_order_low_first(self):
        codec = ModbusCodec()
        value = 1.5
        regs_high = codec.encode(Float64(), value)
        regs_low = codec.encode(Float64(), value, register_order=RegisterOrder.LOW_FIRST)
        # LOW_FIRST 應該是反轉順序
        assert regs_low == list(reversed(regs_high))


class TestByteOrder:
    """ByteOrder 測試"""

    def test_int32_little_endian(self):
        codec = ModbusCodec()
        value = 0x12345678
        regs_be = codec.encode(Int32(), value, byte_order=ByteOrder.BIG_ENDIAN)
        regs_le = codec.encode(Int32(), value, byte_order=ByteOrder.LITTLE_ENDIAN)
        # 驗證兩種順序產生不同結果
        assert regs_be != regs_le
        # 驗證 roundtrip
        assert codec.decode(Int32(), regs_be, byte_order=ByteOrder.BIG_ENDIAN) == value
        assert codec.decode(Int32(), regs_le, byte_order=ByteOrder.LITTLE_ENDIAN) == value

    def test_float32_little_endian(self):
        codec = ModbusCodec()
        value = 3.14
        regs_be = codec.encode(Float32(), value, byte_order=ByteOrder.BIG_ENDIAN)
        regs_le = codec.encode(Float32(), value, byte_order=ByteOrder.LITTLE_ENDIAN)
        # 驗證 roundtrip
        decoded_be = codec.decode(Float32(), regs_be, byte_order=ByteOrder.BIG_ENDIAN)
        decoded_le = codec.decode(Float32(), regs_le, byte_order=ByteOrder.LITTLE_ENDIAN)
        assert abs(decoded_be - value) < 1e-5
        assert abs(decoded_le - value) < 1e-5


class TestDecodeErrors:
    """解碼錯誤測試"""

    def test_int16_insufficient_registers(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusDecodeError):
            codec.decode(Int16(), [])

    def test_int32_insufficient_registers(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusDecodeError):
            codec.decode(Int32(), [0x1234])  # 需要 2 個

    def test_int64_insufficient_registers(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusDecodeError):
            codec.decode(Int64(), [0x1234, 0x5678, 0x9ABC])  # 需要 4 個

    def test_float32_insufficient_registers(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusDecodeError):
            codec.decode(Float32(), [0x1234])  # 需要 2 個

    def test_float64_insufficient_registers(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusDecodeError):
            codec.decode(Float64(), [0x1234, 0x5678])  # 需要 4 個

    def test_dynamic_uint_insufficient_registers(self):
        codec = ModbusCodec()
        uint48 = DynamicUInt(48)
        with pytest.raises(ModbusDecodeError):
            codec.decode(uint48, [0x1234, 0x5678])  # 需要 3 個

    def test_string_insufficient_registers(self):
        codec = ModbusCodec()
        str_type = ModbusString(10)  # 需要 5 個暫存器
        with pytest.raises(ModbusDecodeError):
            codec.decode(str_type, [0x4865, 0x6C6C])  # 只有 2 個


class TestTypeErrors:
    """類型錯誤測試"""

    def test_int16_requires_int(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError):
            codec.encode(Int16(), "123")
        with pytest.raises(ModbusEncodeError):
            codec.encode(Int16(), 1.5)

    def test_uint32_requires_int(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError):
            codec.encode(UInt32(), [1, 2, 3])
        with pytest.raises(ModbusEncodeError):
            codec.encode(UInt32(), None)

    def test_float32_requires_numeric(self):
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError):
            codec.encode(Float32(), "3.14")
        with pytest.raises(ModbusEncodeError):
            codec.encode(Float32(), [1.0])

    def test_dynamic_int_requires_int(self):
        codec = ModbusCodec()
        int48 = DynamicInt(48)
        with pytest.raises(ModbusEncodeError):
            codec.encode(int48, "123456")

    def test_string_requires_str(self):
        codec = ModbusCodec()
        str_type = ModbusString(10)
        with pytest.raises(ModbusEncodeError):
            codec.encode(str_type, 12345)


class TestDynamicUInt:
    """DynamicUInt 測試"""

    def test_uint48_register_count(self):
        uint48 = DynamicUInt(48)
        assert uint48.register_count == 3

    def test_uint48_encode_decode(self):
        codec = ModbusCodec()
        uint48 = DynamicUInt(48)
        
        value = 0x123456789ABC
        registers = codec.encode(uint48, value)
        assert len(registers) == 3
        
        decoded = codec.decode(uint48, registers)
        assert decoded == value

    def test_invalid_bit_width(self):
        with pytest.raises(ModbusConfigError):
            DynamicUInt(24)  # Not a multiple of 16
        with pytest.raises(ModbusConfigError):
            DynamicUInt(17)  # Not a multiple of 16

    def test_uint64(self):
        codec = ModbusCodec()
        uint64 = DynamicUInt(64)
        assert uint64.register_count == 4
        
        value = 0x123456789ABCDEF0
        registers = codec.encode(uint64, value)
        decoded = codec.decode(uint64, registers)
        assert decoded == value


class TestDynamicInt:
    """DynamicInt 測試"""

    def test_int48_negative(self):
        codec = ModbusCodec()
        int48 = DynamicInt(48)
        
        value = -1
        registers = codec.encode(int48, value)
        decoded = codec.decode(int48, registers)
        assert decoded == value

    def test_int48_roundtrip(self):
        codec = ModbusCodec()
        int48 = DynamicInt(48)
        
        max_val = (1 << 47) - 1
        min_val = -(1 << 47)
        
        for value in [min_val, -1, 0, 1, max_val]:
            registers = codec.encode(int48, value)
            decoded = codec.decode(int48, registers)
            assert decoded == value


class TestModbusString:
    """ModbusString 測試"""

    def test_register_count(self):
        assert ModbusString(10).register_count == 5  # ceil(10/2)
        assert ModbusString(11).register_count == 6  # ceil(11/2)

    def test_encode_decode_ascii(self):
        codec = ModbusCodec()
        str_type = ModbusString(16)
        
        value = "Hello"
        registers = codec.encode(str_type, value)
        decoded = codec.decode(str_type, registers)
        assert decoded == value

    def test_encode_decode_utf8(self):
        codec = ModbusCodec()
        str_type = ModbusString(32, encoding="utf-8")
        
        value = "Hello 世界"
        registers = codec.encode(str_type, value)
        decoded = codec.decode(str_type, registers)
        assert decoded == value

    def test_max_length_exceeded(self):
        codec = ModbusCodec()
        str_type = ModbusString(5)
        
        with pytest.raises(ModbusEncodeError):
            codec.encode(str_type, "123456")  # 6 chars > 5 max

