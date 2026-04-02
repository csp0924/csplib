"""Tests for WriteRule.apply() — clamping, rejection, and boundary behavior."""

import pytest

from csp_lib.modbus_gateway.config import WriteRule


class TestWriteRuleClamp:
    """WriteRule with clamp=True should clamp out-of-range values."""

    def test_clamp_below_min(self):
        rule = WriteRule(register_name="power", min_value=-1000, max_value=1000, clamp=True)
        value, rejected = rule.apply("power", -1500)
        assert value == pytest.approx(-1000)
        assert rejected is False

    def test_clamp_above_max(self):
        rule = WriteRule(register_name="power", min_value=-1000, max_value=1000, clamp=True)
        value, rejected = rule.apply("power", 2000)
        assert value == pytest.approx(1000)
        assert rejected is False

    def test_clamp_within_range_passes_through(self):
        rule = WriteRule(register_name="power", min_value=-1000, max_value=1000, clamp=True)
        value, rejected = rule.apply("power", 500)
        assert value == pytest.approx(500)
        assert rejected is False

    def test_clamp_at_exact_boundary(self):
        """Values exactly at min/max should pass through without modification."""
        rule = WriteRule(register_name="power", min_value=0, max_value=100, clamp=True)
        val_min, rej_min = rule.apply("power", 0)
        val_max, rej_max = rule.apply("power", 100)
        assert val_min == pytest.approx(0)
        assert rej_min is False
        assert val_max == pytest.approx(100)
        assert rej_max is False


class TestWriteRuleReject:
    """WriteRule with clamp=False should reject out-of-range values."""

    def test_reject_below_min(self):
        rule = WriteRule(register_name="power", min_value=0, max_value=1000, clamp=False)
        value, rejected = rule.apply("power", -1)
        assert rejected is True
        # Original value returned unchanged when rejected
        assert value == pytest.approx(-1)

    def test_reject_above_max(self):
        rule = WriteRule(register_name="power", min_value=0, max_value=1000, clamp=False)
        value, rejected = rule.apply("power", 1001)
        assert rejected is True
        assert value == pytest.approx(1001)

    def test_reject_within_range_passes(self):
        rule = WriteRule(register_name="power", min_value=0, max_value=1000, clamp=False)
        value, rejected = rule.apply("power", 500)
        assert rejected is False
        assert value == pytest.approx(500)


class TestWriteRulePartialBounds:
    """WriteRule with only min or only max set."""

    def test_only_min_allows_high_values(self):
        rule = WriteRule(register_name="freq", min_value=0, clamp=False)
        value, rejected = rule.apply("freq", 999999)
        assert rejected is False
        assert value == pytest.approx(999999)

    def test_only_min_rejects_below(self):
        rule = WriteRule(register_name="freq", min_value=0, clamp=False)
        value, rejected = rule.apply("freq", -0.1)
        assert rejected is True

    def test_only_max_allows_low_values(self):
        rule = WriteRule(register_name="power", max_value=1000, clamp=True)
        value, rejected = rule.apply("power", -99999)
        assert rejected is False
        assert value == pytest.approx(-99999)

    def test_only_max_clamps_above(self):
        rule = WriteRule(register_name="power", max_value=1000, clamp=True)
        value, rejected = rule.apply("power", 1500)
        assert value == pytest.approx(1000)
        assert rejected is False

    def test_no_bounds_always_passes(self):
        """WriteRule with no min/max should pass any value through."""
        rule = WriteRule(register_name="power")
        value, rejected = rule.apply("power", -999999)
        assert rejected is False
        assert value == pytest.approx(-999999)


class TestWriteRuleValidation:
    """WriteRule construction-time validation."""

    def test_min_greater_than_max_raises(self):
        with pytest.raises(ValueError, match="min_value must be <= max_value"):
            WriteRule(register_name="bad", min_value=100, max_value=50)

    def test_min_equals_max_is_valid(self):
        """min == max is valid — only that exact value is accepted."""
        rule = WriteRule(register_name="fixed", min_value=42, max_value=42, clamp=False)
        _, rejected_exact = rule.apply("fixed", 42)
        _, rejected_below = rule.apply("fixed", 41)
        _, rejected_above = rule.apply("fixed", 43)
        assert rejected_exact is False
        assert rejected_below is True
        assert rejected_above is True

    def test_frozen_dataclass(self):
        rule = WriteRule(register_name="power", min_value=0, max_value=100)
        with pytest.raises(AttributeError):
            rule.min_value = 50  # type: ignore[misc]
