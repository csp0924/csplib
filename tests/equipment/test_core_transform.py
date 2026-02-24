# =============== Equipment Core Tests - Transform ===============
#
# 資料轉換步驟單元測試

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.equipment.core.transform import (
    BitExtractTransform,
    BoolTransform,
    ByteExtractTransform,
    ClampTransform,
    EnumMapTransform,
    InverseTransform,
    MultiFieldExtractTransform,
    PowerFactorTransform,
    RoundTransform,
    ScaleTransform,
    TransformStep,
)


class TestScaleTransform:
    """ScaleTransform 測試"""

    def test_default_no_change(self):
        transform = ScaleTransform()
        assert transform.apply(100) == 100.0

    def test_magnitude_only(self):
        transform = ScaleTransform(magnitude=0.1)
        assert transform.apply(1000) == 100.0

    def test_offset_only(self):
        transform = ScaleTransform(offset=-40)
        assert transform.apply(100) == 60.0

    def test_magnitude_and_offset(self):
        # 常見的溫度轉換: raw * 0.1 - 40
        transform = ScaleTransform(magnitude=0.1, offset=-40)
        assert transform.apply(650) == 25.0  # 650 * 0.1 - 40 = 25

    def test_negative_magnitude(self):
        transform = ScaleTransform(magnitude=-1)
        assert transform.apply(50) == -50.0

    def test_accepts_int_and_float(self):
        transform = ScaleTransform(magnitude=2)
        assert transform.apply(10) == 20.0
        assert transform.apply(10.5) == 21.0

    def test_returns_float(self):
        transform = ScaleTransform()
        result = transform.apply(10)
        assert isinstance(result, float)

    def test_invalid_type_raises(self):
        transform = ScaleTransform()
        with pytest.raises(TypeError, match="需要數值"):
            transform.apply("100")
        with pytest.raises(TypeError):
            transform.apply(None)
        with pytest.raises(TypeError):
            transform.apply([100])

    def test_immutable(self):
        transform = ScaleTransform(magnitude=0.1)
        with pytest.raises(FrozenInstanceError):
            transform.magnitude = 0.01


class TestRoundTransform:
    """RoundTransform 測試"""

    def test_default_2_decimals(self):
        transform = RoundTransform()
        assert transform.apply(3.14159) == 3.14

    def test_zero_decimals(self):
        transform = RoundTransform(decimals=0)
        assert transform.apply(3.7) == 4.0

    def test_negative_rounding(self):
        # Python round 支援負數 decimals
        transform = RoundTransform(decimals=-1)
        assert transform.apply(123.456) == 120.0

    def test_more_decimals(self):
        transform = RoundTransform(decimals=4)
        assert transform.apply(3.141592653) == 3.1416

    def test_integer_input(self):
        transform = RoundTransform(decimals=2)
        assert transform.apply(100) == 100.0

    def test_invalid_type_raises(self):
        transform = RoundTransform()
        with pytest.raises(TypeError, match="需要數值"):
            transform.apply("3.14")


class TestEnumMapTransform:
    """EnumMapTransform 測試"""

    def test_basic_mapping(self):
        transform = EnumMapTransform(mapping={0: "STOP", 1: "RUN", 2: "FAULT"})
        assert transform.apply(0) == "STOP"
        assert transform.apply(1) == "RUN"
        assert transform.apply(2) == "FAULT"

    def test_default_for_unknown(self):
        transform = EnumMapTransform(mapping={0: "OFF", 1: "ON"})
        assert transform.apply(99) == "UNKNOWN"

    def test_custom_default(self):
        transform = EnumMapTransform(mapping={0: "OFF", 1: "ON"}, default="UNDEFINED")
        assert transform.apply(99) == "UNDEFINED"

    def test_float_converted_to_int(self):
        transform = EnumMapTransform(mapping={0: "ZERO", 1: "ONE"})
        assert transform.apply(1.0) == "ONE"  # 會轉換成 int

    def test_unconvertible_returns_default_with_value(self):
        transform = EnumMapTransform(mapping={0: "ZERO"})
        result = transform.apply("invalid")
        assert "UNKNOWN" in result
        assert "invalid" in result

    def test_negative_keys(self):
        transform = EnumMapTransform(mapping={-1: "ERROR", 0: "OK", 1: "WARNING"})
        assert transform.apply(-1) == "ERROR"

    def test_hashable(self):
        """EnumMapTransform 應該是 hashable 的"""
        transform = EnumMapTransform(mapping={0: "A", 1: "B"})
        hash_value = hash(transform)
        assert isinstance(hash_value, int)


class TestClampTransform:
    """ClampTransform 測試"""

    def test_within_range(self):
        transform = ClampTransform(min_value=0, max_value=100)
        assert transform.apply(50) == 50.0

    def test_below_min(self):
        transform = ClampTransform(min_value=0, max_value=100)
        assert transform.apply(-50) == 0.0

    def test_above_max(self):
        transform = ClampTransform(min_value=0, max_value=100)
        assert transform.apply(150) == 100.0

    def test_min_only(self):
        transform = ClampTransform(min_value=0)
        assert transform.apply(-100) == 0.0
        assert transform.apply(1000000) == 1000000.0

    def test_max_only(self):
        transform = ClampTransform(max_value=100)
        assert transform.apply(-1000000) == -1000000.0
        assert transform.apply(200) == 100.0

    def test_no_bounds(self):
        transform = ClampTransform()
        assert transform.apply(-1e10) == -1e10
        assert transform.apply(1e10) == 1e10

    def test_float_bounds(self):
        transform = ClampTransform(min_value=-0.5, max_value=0.5)
        assert transform.apply(0.3) == 0.3
        assert transform.apply(-0.8) == -0.5
        assert transform.apply(0.8) == 0.5

    def test_invalid_type_raises(self):
        transform = ClampTransform(min_value=0, max_value=100)
        with pytest.raises(TypeError, match="需要數值"):
            transform.apply("50")


class TestBoolTransform:
    """BoolTransform 測試"""

    def test_default_true_is_1(self):
        transform = BoolTransform()
        assert transform.apply(0) is False
        assert transform.apply(1) is True
        assert transform.apply(2) is False

    def test_custom_true_values(self):
        transform = BoolTransform(true_values=frozenset({1, 2, 3}))
        assert transform.apply(0) is False
        assert transform.apply(1) is True
        assert transform.apply(2) is True
        assert transform.apply(3) is True
        assert transform.apply(4) is False

    def test_bool_input_passthrough(self):
        transform = BoolTransform()
        assert transform.apply(True) is True
        assert transform.apply(False) is False

    def test_non_int_uses_bool(self):
        transform = BoolTransform()
        assert transform.apply("non-empty") is True
        assert transform.apply("") is False
        assert transform.apply([1, 2]) is True
        assert transform.apply([]) is False


class TestInverseTransform:
    """InverseTransform 測試"""

    def test_default_no_change(self):
        transform = InverseTransform()
        assert transform.apply(100) == 100.0

    def test_inverse_of_scale(self):
        # ScaleTransform: result = value * 0.1 - 40
        # InverseTransform: result = (value + 40) / 0.1
        transform = InverseTransform(magnitude=0.1, offset=-40)
        assert transform.apply(25.0) == 650.0  # (25 - (-40)) / 0.1 = 650

    def test_magnitude_only(self):
        transform = InverseTransform(magnitude=0.1)
        assert transform.apply(100) == 1000.0

    def test_offset_only(self):
        transform = InverseTransform(offset=-40)
        assert transform.apply(60) == 100.0  # (60 - (-40)) / 1 = 100

    def test_zero_magnitude_raises(self):
        transform = InverseTransform(magnitude=0)
        with pytest.raises(ValueError, match="magnitude 不可為 0"):
            transform.apply(100)

    def test_invalid_type_raises(self):
        transform = InverseTransform()
        with pytest.raises(TypeError, match="需要數值"):
            transform.apply("100")

    def test_roundtrip_with_scale(self):
        """驗證 ScaleTransform 和 InverseTransform 互為逆運算"""
        scale = ScaleTransform(magnitude=0.1, offset=-40)
        inverse = InverseTransform(magnitude=0.1, offset=-40)

        raw_value = 650
        scaled = scale.apply(raw_value)
        recovered = inverse.apply(scaled)
        assert abs(recovered - raw_value) < 1e-10


class TestBitExtractTransform:
    """BitExtractTransform 測試"""

    def test_single_bit_returns_bool(self):
        transform = BitExtractTransform(bit_offset=0)
        assert transform.apply(0b0001) is True
        assert transform.apply(0b0000) is False

    def test_bit_offset(self):
        transform = BitExtractTransform(bit_offset=3)
        assert transform.apply(0b1000) is True  # Bit 3 = 1
        assert transform.apply(0b0111) is False  # Bit 3 = 0

    def test_multi_bit_returns_int(self):
        transform = BitExtractTransform(bit_offset=0, bit_length=4)
        result = transform.apply(0b11110101)
        assert result == 0b0101  # 低 4 位
        assert isinstance(result, int)

    def test_multi_bit_with_offset(self):
        transform = BitExtractTransform(bit_offset=4, bit_length=4)
        result = transform.apply(0b11110101)
        assert result == 0b1111  # Bit 4-7

    def test_8_bit_field(self):
        transform = BitExtractTransform(bit_offset=8, bit_length=8)
        result = transform.apply(0x12345678)
        assert result == 0x56  # Byte 1

    def test_mask_property(self):
        transform = BitExtractTransform(bit_offset=0, bit_length=4)
        assert transform.mask == 0b1111

        transform2 = BitExtractTransform(bit_offset=0, bit_length=8)
        assert transform2.mask == 0xFF

    def test_invalid_bit_offset_raises(self):
        with pytest.raises(ValueError, match="bit_offset 必須 >= 0"):
            BitExtractTransform(bit_offset=-1)

    def test_invalid_bit_length_raises(self):
        with pytest.raises(ValueError, match="bit_length 必須 >= 1"):
            BitExtractTransform(bit_offset=0, bit_length=0)

    def test_invalid_type_raises(self):
        transform = BitExtractTransform(bit_offset=0)
        with pytest.raises(TypeError, match="需要整數"):
            transform.apply(1.5)
        with pytest.raises(TypeError):
            transform.apply("0b1111")

    def test_large_integers(self):
        """測試 32/64-bit 整數"""
        transform = BitExtractTransform(bit_offset=32, bit_length=16)
        value = 0x123456789ABC
        result = transform.apply(value)
        assert result == 0x1234


class TestMultiFieldExtractTransform:
    """MultiFieldExtractTransform 測試"""

    def test_extract_multiple_bool_fields(self):
        transform = MultiFieldExtractTransform(
            fields=(
                ("is_running", 0, 1),
                ("has_fault", 1, 1),
                ("is_connected", 2, 1),
            )
        )
        result = transform.apply(0b101)  # Bit 0 = 1, Bit 1 = 0, Bit 2 = 1
        assert result == {
            "is_running": True,
            "has_fault": False,
            "is_connected": True,
        }

    def test_mixed_field_sizes(self):
        transform = MultiFieldExtractTransform(
            fields=(
                ("flag", 0, 1),  # Bit 0, bool
                ("mode", 8, 4),  # Bit 8-11, int
                ("status", 12, 4),  # Bit 12-15, int
            )
        )
        value = 0b1010_0011_0000_0001  # flag=1, mode=3, status=10
        result = transform.apply(value)
        assert result["flag"] is True
        assert result["mode"] == 0b0011
        assert result["status"] == 0b1010

    def test_field_names_property(self):
        transform = MultiFieldExtractTransform(fields=(("a", 0, 1), ("b", 1, 1), ("c", 8, 4)))
        assert transform.field_names == ("a", "b", "c")

    def test_empty_fields_raises(self):
        with pytest.raises(ValueError, match="fields 不可為空"):
            MultiFieldExtractTransform(fields=())

    def test_duplicate_names_raises(self):
        with pytest.raises(ValueError, match="欄位名稱必須唯一"):
            MultiFieldExtractTransform(fields=(("same", 0, 1), ("same", 1, 1)))

    def test_invalid_offset_raises(self):
        with pytest.raises(ValueError, match="bit_offset 必須 >= 0"):
            MultiFieldExtractTransform(fields=(("bad", -1, 1),))

    def test_invalid_length_raises(self):
        with pytest.raises(ValueError, match="bit_length 必須 >= 1"):
            MultiFieldExtractTransform(fields=(("bad", 0, 0),))

    def test_invalid_type_raises(self):
        transform = MultiFieldExtractTransform(fields=(("test", 0, 1),))
        with pytest.raises(TypeError, match="需要整數"):
            transform.apply(1.5)

    def test_large_value(self):
        """測試 64-bit 值"""
        transform = MultiFieldExtractTransform(
            fields=(
                ("low16", 0, 16),
                ("mid16", 16, 16),
                ("high32", 32, 32),
            )
        )
        value = 0x123456789ABCDEF0
        result = transform.apply(value)
        assert result["low16"] == 0xDEF0
        assert result["mid16"] == 0x9ABC
        assert result["high32"] == 0x12345678


class TestByteExtractTransform:
    """ByteExtractTransform 測試"""

    def test_extract_first_2_bytes(self):
        """從 [0x1234, 0x5678] 提取前 2 bytes"""
        transform = ByteExtractTransform(byte_offset=0, byte_length=2)
        result = transform.apply([0x1234, 0x5678])
        assert result == bytes([0x12, 0x34])

    def test_extract_with_offset(self):
        """從 [0x1234, 0x5678] 提取 byte_offset=2 開始的 2 bytes"""
        transform = ByteExtractTransform(byte_offset=2, byte_length=2)
        result = transform.apply([0x1234, 0x5678])
        assert result == bytes([0x56, 0x78])

    def test_extract_single_byte(self):
        """提取單一 byte"""
        transform = ByteExtractTransform(byte_offset=1, byte_length=1)
        result = transform.apply([0xABCD])
        assert result == bytes([0xCD])

    def test_extract_from_tuple(self):
        """支援 tuple 輸入"""
        transform = ByteExtractTransform(byte_offset=0, byte_length=2)
        result = transform.apply((0x1234,))
        assert result == bytes([0x12, 0x34])

    def test_extract_all_bytes(self):
        """提取所有 bytes"""
        transform = ByteExtractTransform(byte_offset=0, byte_length=4)
        result = transform.apply([0x1234, 0x5678])
        assert result == bytes([0x12, 0x34, 0x56, 0x78])

    def test_invalid_byte_offset_raises(self):
        with pytest.raises(ValueError, match="byte_offset 必須 >= 0"):
            ByteExtractTransform(byte_offset=-1)

    def test_invalid_byte_length_raises(self):
        with pytest.raises(ValueError, match="byte_length 必須 >= 1"):
            ByteExtractTransform(byte_offset=0, byte_length=0)

    def test_invalid_type_raises(self):
        transform = ByteExtractTransform(byte_offset=0, byte_length=1)
        with pytest.raises(TypeError, match="需要列表"):
            transform.apply(0x1234)
        with pytest.raises(TypeError, match="需要列表"):
            transform.apply("1234")

    def test_out_of_range_returns_empty(self):
        """offset 超出範圍時回傳空 bytes"""
        transform = ByteExtractTransform(byte_offset=10, byte_length=2)
        result = transform.apply([0x1234])
        assert result == b""


class TestPowerFactorTransform:
    """PowerFactorTransform 測試"""

    def test_q1_lagging(self):
        """Q1: 0 < x < 1 → PF = x, lagging"""
        transform = PowerFactorTransform()
        assert transform.apply(0.85) == 0.85

    def test_q2_leading(self):
        """Q2: -2 < x < -1 → PF = -2 - x, leading"""
        transform = PowerFactorTransform()
        result = transform.apply(-1.15)
        assert abs(result - (-0.85)) < 1e-10

    def test_q3_lagging(self):
        """Q3: -1 < x < 0 → PF = x, lagging"""
        transform = PowerFactorTransform()
        assert transform.apply(-0.85) == -0.85

    def test_q4_leading(self):
        """Q4: 1 < x < 2 → PF = 2 - x, leading"""
        transform = PowerFactorTransform()
        result = transform.apply(1.15)
        assert abs(result - 0.85) < 1e-10

    def test_unity_positive(self):
        """Unity: |x| = 1 → PF = x"""
        transform = PowerFactorTransform()
        assert transform.apply(1.0) == 1.0

    def test_unity_negative(self):
        """Unity: |x| = 1 → PF = x"""
        transform = PowerFactorTransform()
        assert transform.apply(-1.0) == -1.0

    def test_include_status_q1(self):
        """include_status=True 回傳 dict"""
        transform = PowerFactorTransform(include_status=True)
        result = transform.apply(0.85)
        assert result == {"pf": 0.85, "status": "lagging"}

    def test_include_status_q2(self):
        transform = PowerFactorTransform(include_status=True)
        result = transform.apply(-1.15)
        assert result["status"] == "leading"
        assert abs(result["pf"] - (-0.85)) < 1e-10

    def test_include_status_q4(self):
        transform = PowerFactorTransform(include_status=True)
        result = transform.apply(1.15)
        assert result["status"] == "leading"
        assert abs(result["pf"] - 0.85) < 1e-10

    def test_include_status_unity(self):
        transform = PowerFactorTransform(include_status=True)
        result = transform.apply(1.0)
        assert result == {"pf": 1.0, "status": "unity"}

    def test_accepts_int(self):
        """接受整數輸入"""
        transform = PowerFactorTransform()
        assert transform.apply(0) == 0.0

    def test_invalid_type_raises(self):
        transform = PowerFactorTransform()
        with pytest.raises(TypeError, match="需要數值"):
            transform.apply("0.85")
        with pytest.raises(TypeError, match="需要數值"):
            transform.apply(None)


class TestTransformStepProtocol:
    """TransformStep Protocol 測試"""

    def test_all_transforms_satisfy_protocol(self):
        transforms = [
            ScaleTransform(),
            RoundTransform(),
            EnumMapTransform(mapping={0: "A"}),
            ClampTransform(),
            BoolTransform(),
            InverseTransform(),
            BitExtractTransform(bit_offset=0),
            ByteExtractTransform(byte_offset=0),
            PowerFactorTransform(),
            MultiFieldExtractTransform(fields=(("x", 0, 1),)),
        ]
        for t in transforms:
            assert hasattr(t, "apply")
            assert callable(t.apply)

    def test_custom_transform(self):
        """自定義 transform 也可以滿足 Protocol"""

        class SquareTransform:
            def apply(self, value):
                return value**2

        transform: TransformStep = SquareTransform()
        assert transform.apply(5) == 25


class TestTransformChaining:
    """測試 Transform 串接使用"""

    def test_scale_then_round(self):
        """模擬實際 pipeline: 先縮放再四捨五入"""
        transforms = [
            ScaleTransform(magnitude=0.1),
            RoundTransform(decimals=1),
        ]
        value = 1234
        for t in transforms:
            value = t.apply(value)
        assert value == 123.4

    def test_scale_round_clamp(self):
        """模擬 pipeline: 縮放 → 四捨五入 → 限制範圍"""
        transforms = [
            ScaleTransform(magnitude=0.1, offset=-40),
            RoundTransform(decimals=1),
            ClampTransform(min_value=-20, max_value=60),
        ]
        # 800 → 80 * 0.1 - 40 = 40 → clamp → 40
        value = 800
        for t in transforms:
            value = t.apply(value)
        assert value == 40.0

        # 1200 → 120 * 0.1 - 40 = 80 → clamp to 60
        value = 1200
        for t in transforms:
            value = t.apply(value)
        assert value == 60.0

    def test_bit_extract_then_bool(self):
        """提取位元後轉換為布林"""
        extract = BitExtractTransform(bit_offset=4, bit_length=4)
        bool_tf = BoolTransform(true_values=frozenset({1, 2, 3}))

        result = extract.apply(0b0010_0000)  # Bit 4-7 = 2
        assert result == 2
        assert bool_tf.apply(result) is True
