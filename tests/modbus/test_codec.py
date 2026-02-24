from unittest.mock import MagicMock

import pytest

from csp_lib.modbus import ByteOrder, Float32, Int32, ModbusCodec, RegisterOrder, UInt16
from csp_lib.modbus.exceptions import ModbusDecodeError, ModbusEncodeError


class TestModbusCodec:
    def test_encode_uint16(self):
        codec = ModbusCodec()
        result = codec.encode(UInt16(), 1000)
        assert result == [1000]

    def test_decode_uint16(self):
        codec = ModbusCodec()
        result = codec.decode(UInt16(), [1000])
        assert result == 1000

    def test_encode_float32(self):
        codec = ModbusCodec()
        regs = codec.encode(Float32(), 1.0)
        assert len(regs) == 2

    def test_decode_float32(self):
        codec = ModbusCodec()
        regs = codec.encode(Float32(), 3.14)
        result = codec.decode(Float32(), regs)
        assert abs(result - 3.14) < 0.01

    def test_roundtrip_int32(self):
        codec = ModbusCodec()
        regs = codec.encode(Int32(), -123456)
        result = codec.decode(Int32(), regs)
        assert result == -123456

    def test_encode_wraps_non_modbus_error(self):
        """Generic Exception from data_type.encode is wrapped as ModbusEncodeError"""
        dt = MagicMock()
        dt.encode.side_effect = RuntimeError("boom")
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError, match="編碼失敗"):
            codec.encode(dt, 42)

    def test_decode_wraps_non_modbus_error(self):
        """Generic Exception from data_type.decode is wrapped as ModbusDecodeError"""
        dt = MagicMock()
        dt.decode.side_effect = RuntimeError("boom")
        codec = ModbusCodec()
        with pytest.raises(ModbusDecodeError, match="解碼失敗"):
            codec.decode(dt, [0])

    def test_encode_passthrough_modbus_error(self):
        """ModbusEncodeError is re-raised directly without wrapping"""
        dt = MagicMock()
        dt.encode.side_effect = ModbusEncodeError("original error")
        codec = ModbusCodec()
        with pytest.raises(ModbusEncodeError, match="original error"):
            codec.encode(dt, 42)

    def test_decode_passthrough_modbus_error(self):
        """ModbusDecodeError is re-raised directly without wrapping"""
        dt = MagicMock()
        dt.decode.side_effect = ModbusDecodeError("original decode error")
        codec = ModbusCodec()
        with pytest.raises(ModbusDecodeError, match="original decode error"):
            codec.decode(dt, [0])

    def test_custom_byte_order(self):
        codec = ModbusCodec()
        regs = codec.encode(UInt16(), 256, byte_order=ByteOrder.LITTLE_ENDIAN)
        result = codec.decode(UInt16(), regs, byte_order=ByteOrder.LITTLE_ENDIAN)
        assert result == 256

    def test_custom_register_order(self):
        codec = ModbusCodec()
        regs_hf = codec.encode(Int32(), 100000, register_order=RegisterOrder.HIGH_FIRST)
        regs_lf = codec.encode(Int32(), 100000, register_order=RegisterOrder.LOW_FIRST)
        assert regs_hf != regs_lf  # different ordering
        assert codec.decode(Int32(), regs_hf, register_order=RegisterOrder.HIGH_FIRST) == 100000
        assert codec.decode(Int32(), regs_lf, register_order=RegisterOrder.LOW_FIRST) == 100000
