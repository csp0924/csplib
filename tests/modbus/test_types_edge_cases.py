import math

from csp_lib.modbus import ByteOrder, Float32, Float64, RegisterOrder


class TestFloat32EdgeCases:
    def test_encode_nan(self):
        """NaN can be encoded without error - silent data corruption risk"""
        f = Float32()
        regs = f.encode(float("nan"), ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert len(regs) == 2

    def test_decode_nan_roundtrip(self):
        """NaN roundtrips through encode/decode"""
        f = Float32()
        regs = f.encode(float("nan"), ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = f.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert math.isnan(result)

    def test_encode_positive_inf(self):
        f = Float32()
        regs = f.encode(float("inf"), ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = f.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert math.isinf(result) and result > 0

    def test_encode_negative_inf(self):
        f = Float32()
        regs = f.encode(float("-inf"), ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = f.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert math.isinf(result) and result < 0

    def test_encode_subnormal(self):
        """Very small near-zero float (subnormal)"""
        f = Float32()
        tiny = 1.4e-45  # smallest positive subnormal for float32
        regs = f.encode(tiny, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = f.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert result >= 0  # subnormal may lose precision

    def test_encode_max_finite(self):
        f = Float32()
        max_val = 3.4028235e38
        regs = f.encode(max_val, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = f.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert not math.isinf(result)
        assert abs(result - max_val) / max_val < 1e-6


class TestFloat64EdgeCases:
    def test_encode_nan(self):
        f = Float64()
        regs = f.encode(float("nan"), ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert len(regs) == 4

    def test_decode_nan_roundtrip(self):
        f = Float64()
        regs = f.encode(float("nan"), ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = f.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert math.isnan(result)

    def test_encode_inf(self):
        f = Float64()
        regs = f.encode(float("inf"), ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        result = f.decode(regs, ByteOrder.BIG_ENDIAN, RegisterOrder.HIGH_FIRST)
        assert math.isinf(result)
