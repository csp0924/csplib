from csp_lib.equipment.core.point import CompositeValidator, EnumValidator, RangeValidator


class TestRangeValidatorEdgeCases:
    def test_min_greater_than_max(self):
        """When min > max, validate always returns False"""
        v = RangeValidator(min_value=100, max_value=0)
        assert v.validate(50) is False
        assert v.validate(0) is False
        assert v.validate(100) is False

    def test_nan_input(self):
        """NaN comparisons: NaN < 0 is False, NaN > 100 is False -> passes"""
        v = RangeValidator(min_value=0, max_value=100)
        result = v.validate(float("nan"))
        # NaN < 0? False. NaN > 100? False. -> True (passes validation)
        assert result is True

    def test_none_input(self):
        v = RangeValidator(min_value=0, max_value=100)
        assert v.validate(None) is False

    def test_no_bounds(self):
        v = RangeValidator()
        assert v.validate(999999) is True
        assert v.validate(-999999) is True


class TestEnumValidatorEdgeCases:
    def test_empty_allowed_values(self):
        """Empty allowed_values: validate always returns False"""
        v = EnumValidator(allowed_values=())
        assert v.validate(0) is False
        assert v.validate("anything") is False

    def test_none_in_allowed(self):
        v = EnumValidator(allowed_values=(None, 0, 1))
        assert v.validate(None) is True


class TestCompositeValidatorEdgeCases:
    def test_empty_validators(self):
        """all([]) = True, everything passes"""
        v = CompositeValidator(validators=())
        assert v.validate(42) is True
        assert v.validate(None) is True

    def test_single_failing_validator(self):
        range_v = RangeValidator(min_value=0, max_value=10)
        v = CompositeValidator(validators=(range_v,))
        assert v.validate(5) is True
        assert v.validate(20) is False

    def test_error_message_combines(self):
        range_v = RangeValidator(min_value=0, max_value=10)
        v = CompositeValidator(validators=(range_v,))
        msg = v.get_error_message(20)
        assert "\u8d85\u51fa\u7bc4\u570d" in msg
