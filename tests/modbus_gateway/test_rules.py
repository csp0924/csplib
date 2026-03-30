"""Tests for composable WriteRule implementations: RangeRule, AllowedValuesRule, StepRule, CompositeRule."""

import pytest

from csp_lib.modbus_gateway.protocol import WriteRule
from csp_lib.modbus_gateway.rules import (
    AllowedValuesRule,
    CompositeRule,
    RangeRule,
    StepRule,
)

REG = "test_register"


# ===========================================================================
# WriteRule Protocol conformance
# ===========================================================================


class TestWriteRuleProtocol:
    """All rule classes must satisfy the runtime_checkable WriteRule protocol."""

    def test_range_rule_is_write_rule(self):
        assert isinstance(RangeRule(), WriteRule)

    def test_allowed_values_rule_is_write_rule(self):
        assert isinstance(AllowedValuesRule({1, 2}), WriteRule)

    def test_step_rule_is_write_rule(self):
        assert isinstance(StepRule(step=1.0), WriteRule)

    def test_composite_rule_is_write_rule(self):
        assert isinstance(CompositeRule(rules=[]), WriteRule)

    def test_custom_class_with_apply_satisfies_protocol(self):
        class Custom:
            def apply(self, register_name: str, value: float) -> tuple[float, bool]:
                return value, False

        assert isinstance(Custom(), WriteRule)


# ===========================================================================
# RangeRule
# ===========================================================================


class TestRangeRule:
    def test_value_in_range_passes(self):
        rule = RangeRule(min_value=0, max_value=100)
        value, rejected = rule.apply(REG, 50)
        assert value == 50
        assert rejected is False

    def test_below_min_clamp_false_rejected(self):
        rule = RangeRule(min_value=10, max_value=100, clamp=False)
        value, rejected = rule.apply(REG, 5)
        assert rejected is True

    def test_below_min_clamp_true_clamped(self):
        rule = RangeRule(min_value=10, max_value=100, clamp=True)
        value, rejected = rule.apply(REG, 5)
        assert value == 10
        assert rejected is False

    def test_above_max_clamp_false_rejected(self):
        rule = RangeRule(min_value=0, max_value=100, clamp=False)
        value, rejected = rule.apply(REG, 150)
        assert rejected is True

    def test_above_max_clamp_true_clamped(self):
        rule = RangeRule(min_value=0, max_value=100, clamp=True)
        value, rejected = rule.apply(REG, 150)
        assert value == 100
        assert rejected is False

    def test_no_lower_bound(self):
        """min_value=None means no lower limit."""
        rule = RangeRule(min_value=None, max_value=100, clamp=False)
        value, rejected = rule.apply(REG, -999999)
        assert value == -999999
        assert rejected is False

    def test_no_upper_bound(self):
        """max_value=None means no upper limit."""
        rule = RangeRule(min_value=0, max_value=None, clamp=False)
        value, rejected = rule.apply(REG, 999999)
        assert value == 999999
        assert rejected is False

    def test_exact_min_boundary_accepted(self):
        rule = RangeRule(min_value=10, max_value=100, clamp=False)
        value, rejected = rule.apply(REG, 10)
        assert value == 10
        assert rejected is False

    def test_exact_max_boundary_accepted(self):
        rule = RangeRule(min_value=10, max_value=100, clamp=False)
        value, rejected = rule.apply(REG, 100)
        assert value == 100
        assert rejected is False

    def test_no_bounds_always_passes(self):
        rule = RangeRule()
        value, rejected = rule.apply(REG, 12345.678)
        assert value == 12345.678
        assert rejected is False


# ===========================================================================
# AllowedValuesRule
# ===========================================================================


class TestAllowedValuesRule:
    def test_value_in_allowed_set_passes(self):
        rule = AllowedValuesRule(allowed={0, 1, 3, 7})
        value, rejected = rule.apply(REG, 1)
        assert value == 1
        assert rejected is False

    def test_value_not_in_allowed_set_rejected(self):
        """AC-1: AllowedValuesRule({0,1,3,7}) rejects value=2."""
        rule = AllowedValuesRule(allowed={0, 1, 3, 7})
        value, rejected = rule.apply(REG, 2)
        assert rejected is True

    def test_int_float_equality(self):
        """Python equality: 3.0 == 3, so 3.0 should be found in {3}."""
        rule = AllowedValuesRule(allowed={3})
        value, rejected = rule.apply(REG, 3.0)
        assert rejected is False

    def test_init_from_set(self):
        rule = AllowedValuesRule(allowed={1, 2, 3})
        assert isinstance(rule.allowed, frozenset)
        assert rule.allowed == frozenset({1, 2, 3})

    def test_init_from_list(self):
        rule = AllowedValuesRule(allowed=[1, 2, 3])
        assert isinstance(rule.allowed, frozenset)
        assert rule.allowed == frozenset({1, 2, 3})

    def test_value_never_transformed(self):
        """AllowedValuesRule should return the exact input value, not modify it."""
        rule = AllowedValuesRule(allowed={42})
        value, rejected = rule.apply(REG, 42)
        assert value == 42


# ===========================================================================
# StepRule
# ===========================================================================


class TestStepRule:
    def test_step_0_5_value_0_3_quantized_to_0_5(self):
        """AC-4: StepRule(0.5) on 0.3 -> 0.5."""
        rule = StepRule(step=0.5)
        value, rejected = rule.apply(REG, 0.3)
        assert value == 0.5
        assert rejected is False

    def test_step_0_5_value_0_7_quantized_to_0_5(self):
        """AC-4: StepRule(0.5) on 0.7 -> 0.5."""
        rule = StepRule(step=0.5)
        value, rejected = rule.apply(REG, 0.7)
        assert value == 0.5
        assert rejected is False

    def test_step_0_5_value_0_75_quantized_to_1_0(self):
        rule = StepRule(step=0.5)
        value, rejected = rule.apply(REG, 0.75)
        assert value == 1.0
        assert rejected is False

    def test_step_1_0_value_2_5_bankers_rounding(self):
        """Python banker's rounding: round(2.5) == 2."""
        rule = StepRule(step=1.0)
        value, rejected = rule.apply(REG, 2.5)
        assert value == 2.0
        assert rejected is False

    def test_step_rule_never_rejects(self):
        rule = StepRule(step=0.5)
        _, rejected = rule.apply(REG, 123.456)
        assert rejected is False

    def test_floating_point_precision(self):
        """step=0.1 should not produce artifacts like 0.30000000000000004."""
        rule = StepRule(step=0.1)
        value, _ = rule.apply(REG, 0.3)
        assert value == 0.3

    def test_step_lte_zero_raises(self):
        with pytest.raises(ValueError, match="step must be > 0"):
            StepRule(step=0)
        with pytest.raises(ValueError, match="step must be > 0"):
            StepRule(step=-1)

    def test_precision_negative_raises(self):
        with pytest.raises(ValueError, match="precision must be >= 0"):
            StepRule(step=1.0, precision=-1)

    def test_exact_step_value_unchanged(self):
        """If value is already a step multiple, it should not change."""
        rule = StepRule(step=0.5)
        value, rejected = rule.apply(REG, 1.5)
        assert value == 1.5
        assert rejected is False

    @pytest.mark.parametrize(
        ("step", "input_val", "expected"),
        [
            (0.25, 0.1, 0.0),
            (0.25, 0.13, 0.25),
            (0.25, 0.37, 0.25),
            (0.25, 0.38, 0.5),
            (10, 14, 10),
            (10, 15, 20),  # banker's: round(1.5) == 2
            (10, 16, 20),
        ],
    )
    def test_quantization_parametrized(self, step, input_val, expected):
        rule = StepRule(step=step)
        value, rejected = rule.apply(REG, input_val)
        assert value == expected
        assert rejected is False


# ===========================================================================
# CompositeRule
# ===========================================================================


class TestCompositeRule:
    def test_empty_rules_pass_through(self):
        rule = CompositeRule(rules=[])
        value, rejected = rule.apply(REG, 42)
        assert value == 42
        assert rejected is False

    def test_single_rule_same_as_direct(self):
        inner = RangeRule(min_value=0, max_value=100, clamp=True)
        composite = CompositeRule(rules=[inner])
        value, rejected = composite.apply(REG, 150)
        assert value == 100
        assert rejected is False

    def test_multiple_rules_applied_in_order(self):
        """RangeRule(clamp) + StepRule: first clamp then quantize."""
        composite = CompositeRule(
            rules=[
                RangeRule(min_value=0, max_value=100, clamp=True),
                StepRule(step=0.5),
            ]
        )
        # AC-2: 100.3 -> clamped to 100.0 -> quantized to 100.0
        value, rejected = composite.apply(REG, 100.3)
        assert value == 100.0
        assert rejected is False

    def test_first_rule_rejects_short_circuits(self):
        """AC-3: RangeRule(clamp=False) rejects 150, StepRule never runs."""
        composite = CompositeRule(
            rules=[
                RangeRule(min_value=0, max_value=100, clamp=False),
                StepRule(step=0.5),
            ]
        )
        value, rejected = composite.apply(REG, 150)
        assert rejected is True

    def test_init_from_list_converts_to_tuple(self):
        composite = CompositeRule(rules=[RangeRule(), StepRule(step=1)])
        assert isinstance(composite.rules, tuple)
        assert len(composite.rules) == 2

    def test_range_clamp_then_step_quantize(self):
        """End-to-end: value=-3.7 -> clamped to 0 -> quantized to 0.0."""
        composite = CompositeRule(
            rules=[
                RangeRule(min_value=0, max_value=100, clamp=True),
                StepRule(step=0.5),
            ]
        )
        value, rejected = composite.apply(REG, -3.7)
        assert value == 0.0
        assert rejected is False

    def test_allowed_then_step(self):
        """AllowedValuesRule rejects before StepRule runs."""
        composite = CompositeRule(
            rules=[
                AllowedValuesRule(allowed={0, 50, 100}),
                StepRule(step=10),
            ]
        )
        # 50 is allowed, step quantize 50 -> 50
        value, rejected = composite.apply(REG, 50)
        assert value == 50
        assert rejected is False

        # 25 not allowed -> rejected
        _, rejected = composite.apply(REG, 25)
        assert rejected is True


# ===========================================================================
# WritePipeline integration with new rules
# ===========================================================================


class TestPipelineWithComposableRules:
    """Integration tests: WritePipeline._apply_rule works with the new rule classes."""

    def test_pipeline_apply_rule_with_allowed_values_rejects(self):
        """Pipeline uses AllowedValuesRule to reject an invalid value."""
        from csp_lib.modbus_gateway.pipeline import WritePipeline

        rule = AllowedValuesRule(allowed={0, 1, 3, 7})
        pipeline = WritePipeline(register_map=None, write_rules={})
        # Directly test _apply_rule since it delegates to rule.apply
        value, rejected = pipeline._apply_rule(rule, REG, 2)
        assert rejected is True

    def test_pipeline_apply_rule_with_allowed_values_accepts(self):
        from csp_lib.modbus_gateway.pipeline import WritePipeline

        rule = AllowedValuesRule(allowed={0, 1, 3, 7})
        pipeline = WritePipeline(register_map=None, write_rules={})
        value, rejected = pipeline._apply_rule(rule, REG, 3)
        assert value == 3
        assert rejected is False

    def test_pipeline_apply_rule_with_composite(self):
        """Pipeline delegates to CompositeRule for multi-step processing."""
        from csp_lib.modbus_gateway.pipeline import WritePipeline

        composite = CompositeRule(
            rules=[
                RangeRule(min_value=0, max_value=100, clamp=True),
                StepRule(step=0.5),
            ]
        )
        pipeline = WritePipeline(register_map=None, write_rules={})
        value, rejected = pipeline._apply_rule(composite, REG, 100.3)
        assert value == 100.0
        assert rejected is False

    def test_pipeline_apply_rule_with_composite_rejection(self):
        from csp_lib.modbus_gateway.pipeline import WritePipeline

        composite = CompositeRule(
            rules=[
                RangeRule(min_value=0, max_value=100, clamp=False),
                StepRule(step=0.5),
            ]
        )
        pipeline = WritePipeline(register_map=None, write_rules={})
        value, rejected = pipeline._apply_rule(composite, REG, 150)
        assert rejected is True
