# =============== Equipment Core Tests - Point ===============
#
# 點位定義單元測試

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.equipment.core.point import (
    CompositeValidator,
    EnumValidator,
    PointDefinition,
    PointMetadata,
    RangeValidator,
    ReadPoint,
    ValueValidator,
    WritePoint,
)
from csp_lib.modbus import ByteOrder, Float32, FunctionCode, Int32, RegisterOrder, UInt16


class TestPointDefinition:
    """PointDefinition 測試"""

    def test_basic_creation(self):
        point = PointDefinition(
            name="test_point",
            address=100,
            data_type=UInt16(),
        )
        assert point.name == "test_point"
        assert point.address == 100
        assert isinstance(point.data_type, UInt16)
        assert point.function_code is None
        assert point.byte_order == ByteOrder.BIG_ENDIAN
        assert point.register_order == RegisterOrder.HIGH_FIRST

    def test_custom_byte_order(self):
        point = PointDefinition(
            name="test",
            address=0,
            data_type=Int32(),
            byte_order=ByteOrder.LITTLE_ENDIAN,
            register_order=RegisterOrder.LOW_FIRST,
        )
        assert point.byte_order == ByteOrder.LITTLE_ENDIAN
        assert point.register_order == RegisterOrder.LOW_FIRST

    def test_immutable(self):
        point = PointDefinition(name="test", address=0, data_type=UInt16())
        with pytest.raises(FrozenInstanceError):
            point.name = "changed"

    def test_hashable(self):
        point1 = PointDefinition(name="test", address=100, data_type=UInt16())
        point2 = PointDefinition(name="test", address=100, data_type=UInt16())
        # Frozen dataclass 預設使用 object id，所以不相等
        assert hash(point1) != hash(point2)


class TestPointMetadata:
    """PointMetadata 測試"""

    def test_defaults(self):
        meta = PointMetadata()
        assert meta.unit is None
        assert meta.description is None

    def test_with_values(self):
        meta = PointMetadata(unit="kW", description="Active Power")
        assert meta.unit == "kW"
        assert meta.description == "Active Power"

    def test_immutable(self):
        meta = PointMetadata(unit="V")
        with pytest.raises(FrozenInstanceError):
            meta.unit = "A"

    def test_value_map_default_none(self):
        meta = PointMetadata()
        assert meta.value_map is None

    def test_with_value_map(self):
        vmap = {0: "Stop", 1: "Run", 2: "Fault"}
        meta = PointMetadata(value_map=vmap)
        assert meta.value_map == {0: "Stop", 1: "Run", 2: "Fault"}

    def test_with_all_fields(self):
        meta = PointMetadata(unit="mode", description="Operating mode", value_map={0: "Off", 1: "On"})
        assert meta.unit == "mode"
        assert meta.description == "Operating mode"
        assert meta.value_map == {0: "Off", 1: "On"}

    def test_hashable_with_value_map(self):
        meta = PointMetadata(value_map={0: "Stop", 1: "Run"})
        assert isinstance(hash(meta), int)
        # Same content should produce same hash
        meta2 = PointMetadata(value_map={0: "Stop", 1: "Run"})
        assert hash(meta) == hash(meta2)

    def test_equal_with_value_map(self):
        meta1 = PointMetadata(unit="kW", value_map={0: "Off", 1: "On"})
        meta2 = PointMetadata(unit="kW", value_map={0: "Off", 1: "On"})
        assert meta1 == meta2
        meta3 = PointMetadata(unit="kW", value_map={0: "Off", 1: "On", 2: "Fault"})
        assert meta1 != meta3


class TestReadPoint:
    """ReadPoint 測試"""

    def test_default_function_code(self):
        """預設 function_code 應為 READ_HOLDING_REGISTERS"""
        point = ReadPoint(name="test", address=100, data_type=UInt16())
        assert point.function_code == FunctionCode.READ_HOLDING_REGISTERS

    def test_explicit_function_code(self):
        """可以指定其他 function_code"""
        point = ReadPoint(
            name="test",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.READ_INPUT_REGISTERS,
        )
        assert point.function_code == FunctionCode.READ_INPUT_REGISTERS

    def test_with_pipeline(self):
        """可以附加 pipeline（此處只測試 None）"""
        point = ReadPoint(name="test", address=0, data_type=UInt16(), pipeline=None)
        assert point.pipeline is None

    def test_with_read_group(self):
        """可以指定 read_group"""
        point = ReadPoint(name="test", address=0, data_type=UInt16(), read_group="status")
        assert point.read_group == "status"

    def test_with_metadata(self):
        """可以附加 metadata"""
        meta = PointMetadata(unit="A", description="Current")
        point = ReadPoint(name="current", address=0, data_type=Float32(), metadata=meta)
        assert point.metadata is not None
        assert point.metadata.unit == "A"

    def test_with_metadata_value_map(self):
        """ReadPoint with value_map metadata"""
        meta = PointMetadata(unit="mode", value_map={0: "Stop", 1: "Run", 2: "Fault"})
        point = ReadPoint(name="mode", address=0, data_type=UInt16(), metadata=meta)
        assert point.metadata.value_map == {0: "Stop", 1: "Run", 2: "Fault"}

    def test_inherits_from_point_definition(self):
        point = ReadPoint(
            name="test",
            address=200,
            data_type=Int32(),
            byte_order=ByteOrder.LITTLE_ENDIAN,
        )
        assert isinstance(point, PointDefinition)
        assert point.address == 200
        assert point.byte_order == ByteOrder.LITTLE_ENDIAN


class TestWritePoint:
    """WritePoint 測試"""

    def test_default_function_code(self):
        """預設 function_code 應為 WRITE_MULTIPLE_REGISTERS"""
        point = WritePoint(name="test", address=100, data_type=UInt16())
        assert point.function_code == FunctionCode.WRITE_MULTIPLE_REGISTERS

    def test_explicit_function_code(self):
        """可以指定其他 function_code"""
        point = WritePoint(
            name="test",
            address=100,
            data_type=UInt16(),
            function_code=FunctionCode.WRITE_SINGLE_REGISTER,
        )
        assert point.function_code == FunctionCode.WRITE_SINGLE_REGISTER

    def test_with_validator(self):
        """可以附加 validator"""
        validator = RangeValidator(min_value=0, max_value=100)
        point = WritePoint(name="power_setpoint", address=0, data_type=UInt16(), validator=validator)
        assert point.validator is not None
        assert point.validator.validate(50) is True
        assert point.validator.validate(150) is False

    def test_with_metadata(self):
        """WritePoint can have metadata"""
        meta = PointMetadata(unit="kW", description="Power setpoint")
        point = WritePoint(name="power", address=100, data_type=UInt16(), metadata=meta)
        assert point.metadata is not None
        assert point.metadata.unit == "kW"
        assert point.metadata.description == "Power setpoint"

    def test_with_metadata_value_map(self):
        """WritePoint metadata with value_map"""
        meta = PointMetadata(value_map={0: "Stop", 1: "Run"})
        point = WritePoint(name="cmd", address=100, data_type=UInt16(), metadata=meta)
        assert point.metadata.value_map == {0: "Stop", 1: "Run"}

    def test_metadata_default_none(self):
        """WritePoint metadata defaults to None"""
        point = WritePoint(name="test", address=100, data_type=UInt16())
        assert point.metadata is None

    def test_with_validator_and_metadata(self):
        """validator and metadata coexist"""
        validator = RangeValidator(min_value=0, max_value=1)
        meta = PointMetadata(value_map={0: "Off", 1: "On"})
        point = WritePoint(name="switch", address=100, data_type=UInt16(), validator=validator, metadata=meta)
        assert point.validator.validate(0) is True
        assert point.validator.validate(2) is False
        assert point.metadata.value_map == {0: "Off", 1: "On"}

    def test_inherits_from_point_definition(self):
        point = WritePoint(name="test", address=300, data_type=Float32())
        assert isinstance(point, PointDefinition)
        assert point.address == 300


class TestRangeValidator:
    """RangeValidator 測試"""

    def test_within_range(self):
        validator = RangeValidator(min_value=0, max_value=100)
        assert validator.validate(0) is True
        assert validator.validate(50) is True
        assert validator.validate(100) is True

    def test_outside_range(self):
        validator = RangeValidator(min_value=0, max_value=100)
        assert validator.validate(-1) is False
        assert validator.validate(101) is False

    def test_min_only(self):
        validator = RangeValidator(min_value=0)
        assert validator.validate(-1) is False
        assert validator.validate(0) is True
        assert validator.validate(1000000) is True

    def test_max_only(self):
        validator = RangeValidator(max_value=100)
        assert validator.validate(-1000000) is True
        assert validator.validate(100) is True
        assert validator.validate(101) is False

    def test_no_bounds(self):
        validator = RangeValidator()
        assert validator.validate(-1e10) is True
        assert validator.validate(1e10) is True

    def test_invalid_type(self):
        validator = RangeValidator(min_value=0, max_value=100)
        assert validator.validate("50") is False
        assert validator.validate(None) is False
        assert validator.validate([50]) is False

    def test_float_values(self):
        validator = RangeValidator(min_value=0.0, max_value=1.0)
        assert validator.validate(0.5) is True
        assert validator.validate(1.1) is False

    def test_error_message(self):
        validator = RangeValidator(min_value=0, max_value=100)
        msg = validator.get_error_message(150)
        assert "150" in msg
        assert "0" in msg
        assert "100" in msg


class TestEnumValidator:
    """EnumValidator 測試"""

    def test_allowed_values(self):
        validator = EnumValidator(allowed_values=(0, 1, 2))
        assert validator.validate(0) is True
        assert validator.validate(1) is True
        assert validator.validate(2) is True

    def test_disallowed_values(self):
        validator = EnumValidator(allowed_values=(0, 1, 2))
        assert validator.validate(3) is False
        assert validator.validate(-1) is False

    def test_string_values(self):
        validator = EnumValidator(allowed_values=("START", "STOP", "PAUSE"))
        assert validator.validate("START") is True
        assert validator.validate("INVALID") is False

    def test_mixed_types(self):
        validator = EnumValidator(allowed_values=(0, 1, "AUTO"))
        assert validator.validate(0) is True
        assert validator.validate("AUTO") is True

    def test_immutable(self):
        validator = EnumValidator(allowed_values=(1, 2, 3))
        with pytest.raises(FrozenInstanceError):
            validator.allowed_values = (4, 5, 6)

    def test_error_message(self):
        validator = EnumValidator(allowed_values=(0, 1))
        msg = validator.get_error_message(99)
        assert "99" in msg
        assert "(0, 1)" in msg


class TestCompositeValidator:
    """CompositeValidator 測試"""

    def test_all_pass(self):
        validator = CompositeValidator(
            validators=(
                RangeValidator(min_value=0, max_value=100),
                EnumValidator(allowed_values=(0, 25, 50, 75, 100)),
            )
        )
        assert validator.validate(50) is True
        assert validator.validate(0) is True
        assert validator.validate(100) is True

    def test_one_fails(self):
        validator = CompositeValidator(
            validators=(
                RangeValidator(min_value=0, max_value=100),
                EnumValidator(allowed_values=(0, 25, 50, 75, 100)),
            )
        )
        # 30 在範圍內但不在允許列表中
        assert validator.validate(30) is False

    def test_all_fail(self):
        validator = CompositeValidator(
            validators=(
                RangeValidator(min_value=0, max_value=100),
                EnumValidator(allowed_values=(0, 25, 50, 75, 100)),
            )
        )
        # 150 超出範圍且不在列表中
        assert validator.validate(150) is False

    def test_empty_validators(self):
        validator = CompositeValidator(validators=())
        assert validator.validate(999) is True  # 沒有驗證器 = 全部通過

    def test_error_message_combines_all(self):
        validator = CompositeValidator(
            validators=(
                RangeValidator(min_value=0, max_value=100),
                EnumValidator(allowed_values=(50,)),
            )
        )
        msg = validator.get_error_message(150)
        # 應該包含兩個錯誤
        assert "150" in msg


class TestValueValidatorProtocol:
    """ValueValidator Protocol 測試"""

    def test_range_validator_satisfies_protocol(self):
        validator: ValueValidator = RangeValidator(min_value=0, max_value=100)
        assert hasattr(validator, "validate")
        assert hasattr(validator, "get_error_message")

    def test_enum_validator_satisfies_protocol(self):
        validator: ValueValidator = EnumValidator(allowed_values=(1, 2, 3))
        assert hasattr(validator, "validate")
        assert hasattr(validator, "get_error_message")

    def test_composite_validator_satisfies_protocol(self):
        validator: ValueValidator = CompositeValidator(validators=())
        assert hasattr(validator, "validate")
        assert hasattr(validator, "get_error_message")

    def test_custom_validator(self):
        """自定義驗證器也可以滿足 Protocol"""

        class EvenValidator:
            def validate(self, value):
                return isinstance(value, int) and value % 2 == 0

            def get_error_message(self, value):
                return f"{value} 必須是偶數"

        validator: ValueValidator = EvenValidator()
        assert validator.validate(2) is True
        assert validator.validate(3) is False
        assert "偶數" in validator.get_error_message(3)
