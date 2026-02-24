# =============== Equipment Processing Tests - Decoder ===============
#
# 解碼器/編碼器單元測試

import pytest

from csp_lib.equipment.processing.decoder import ModbusDecoder, ModbusEncoder
from csp_lib.modbus import ByteOrder, Float32, Int32, RegisterOrder, UInt16

# ======================== ModbusDecoder Tests ========================


class TestModbusDecoder:
    """ModbusDecoder 測試"""

    def test_decode_uint16(self):
        """解碼 UInt16"""
        decoder = ModbusDecoder(data_type=UInt16())
        result = decoder.apply([0x1234])
        assert result == 0x1234

    def test_decode_int32(self):
        """解碼 Int32"""
        decoder = ModbusDecoder(data_type=Int32())
        result = decoder.apply([0x0000, 0x0001])
        assert result == 1

    def test_decode_float32(self):
        """解碼 Float32"""
        decoder = ModbusDecoder(data_type=Float32())
        # IEEE 754: 0x41200000 = 10.0
        result = decoder.apply([0x4120, 0x0000])
        assert abs(result - 10.0) < 0.001

    def test_decode_with_byte_order(self):
        """指定位元組順序（使用 Int32，因為 UInt16 對 byte_order 無作用）"""
        # BIG_ENDIAN: 0x00010002 解讀為 high=0x0001, low=0x0002
        decoder_be = ModbusDecoder(
            data_type=Int32(),
            byte_order=ByteOrder.BIG_ENDIAN,
        )
        # LITTLE_ENDIAN: bytes 會被反向解讀
        decoder_le = ModbusDecoder(
            data_type=Int32(),
            byte_order=ByteOrder.LITTLE_ENDIAN,
        )
        # 同樣的暫存器值，不同 byte_order 應產生不同結果
        registers = [0x0001, 0x0002]
        result_be = decoder_be.apply(registers)
        result_le = decoder_le.apply(registers)
        assert result_be != result_le

    def test_decode_with_register_order(self):
        """指定暫存器順序"""
        decoder = ModbusDecoder(
            data_type=Int32(),
            register_order=RegisterOrder.LOW_FIRST,
        )
        result = decoder.apply([0x0001, 0x0000])
        assert result == 1

    def test_invalid_input_type(self):
        """非列表輸入應報錯"""
        decoder = ModbusDecoder(data_type=UInt16())
        with pytest.raises(TypeError, match="暫存器列表"):
            decoder.apply(0x1234)

    def test_invalid_register_count(self):
        """暫存器數量不對應報錯"""
        decoder = ModbusDecoder(data_type=Int32())
        with pytest.raises(ValueError, match="2 個暫存器"):
            decoder.apply([0x1234])

    def test_tuple_input(self):
        """tuple 輸入也可接受"""
        decoder = ModbusDecoder(data_type=UInt16())
        result = decoder.apply((0x1234,))
        assert result == 0x1234


# ======================== ModbusEncoder Tests ========================


class TestModbusEncoder:
    """ModbusEncoder 測試"""

    def test_encode_uint16(self):
        """編碼 UInt16"""
        encoder = ModbusEncoder(data_type=UInt16())
        result = encoder.apply(0x1234)
        assert result == [0x1234]

    def test_encode_int32(self):
        """編碼 Int32"""
        encoder = ModbusEncoder(data_type=Int32())
        result = encoder.apply(1)
        assert result == [0x0000, 0x0001]

    def test_encode_float32(self):
        """編碼 Float32"""
        encoder = ModbusEncoder(data_type=Float32())
        result = encoder.apply(10.0)
        # IEEE 754: 10.0 = 0x41200000
        assert result == [0x4120, 0x0000]

    def test_encode_with_byte_order(self):
        """指定位元組順序（使用 Int32，因為 UInt16 對 byte_order 無作用）"""
        encoder_be = ModbusEncoder(
            data_type=Int32(),
            byte_order=ByteOrder.BIG_ENDIAN,
        )
        encoder_le = ModbusEncoder(
            data_type=Int32(),
            byte_order=ByteOrder.LITTLE_ENDIAN,
        )
        # 同樣的值，不同 byte_order 應產生不同暫存器值
        value = 0x00010002
        result_be = encoder_be.apply(value)
        result_le = encoder_le.apply(value)
        assert result_be != result_le

    def test_encode_with_register_order(self):
        """指定暫存器順序"""
        encoder = ModbusEncoder(
            data_type=Int32(),
            register_order=RegisterOrder.LOW_FIRST,
        )
        result = encoder.apply(1)
        assert result == [0x0001, 0x0000]


# ======================== Round-trip Tests ========================


class TestDecoderEncoderRoundTrip:
    """解碼器/編碼器往返測試"""

    def test_uint16_roundtrip(self):
        """UInt16 往返"""
        decoder = ModbusDecoder(data_type=UInt16())
        encoder = ModbusEncoder(data_type=UInt16())

        original = 0xABCD
        encoded = encoder.apply(original)
        decoded = decoder.apply(encoded)
        assert decoded == original

    def test_int32_roundtrip(self):
        """Int32 往返"""
        decoder = ModbusDecoder(data_type=Int32())
        encoder = ModbusEncoder(data_type=Int32())

        original = -12345
        encoded = encoder.apply(original)
        decoded = decoder.apply(encoded)
        assert decoded == original

    def test_float32_roundtrip(self):
        """Float32 往返"""
        decoder = ModbusDecoder(data_type=Float32())
        encoder = ModbusEncoder(data_type=Float32())

        original = 3.14159
        encoded = encoder.apply(original)
        decoded = decoder.apply(encoded)
        assert abs(decoded - original) < 0.0001
