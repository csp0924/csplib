# =============== Tests: equipment.transport.validation ===============
#
# 涵蓋 ValidationResult / WriteValidationRule Protocol / RangeRule（含 NaN/Inf guard）

from __future__ import annotations

import math

import pytest

from csp_lib.equipment.transport import RangeRule, ValidationResult, WriteValidationRule


class TestValidationResult:
    def test_accept_shortcut(self) -> None:
        r = ValidationResult.accept(42)
        assert r.accepted is True
        assert r.effective_value == 42
        assert r.reason == ""

    def test_reject_shortcut(self) -> None:
        r = ValidationResult.reject(99, "out of range")
        assert r.accepted is False
        assert r.effective_value == 99  # reject 保留原值供稽核
        assert r.reason == "out of range"

    def test_rejected_must_have_reason(self) -> None:
        with pytest.raises(ValueError, match="non-empty reason"):
            ValidationResult(accepted=False, effective_value=1, reason="")

    def test_accepted_allows_empty_reason(self) -> None:
        r = ValidationResult(accepted=True, effective_value=1, reason="")
        assert r.accepted is True

    def test_is_frozen(self) -> None:
        r = ValidationResult.accept(1)
        with pytest.raises(AttributeError):
            r.accepted = False  # type: ignore[misc]


class TestRangeRulePostInit:
    def test_min_greater_than_max_raises(self) -> None:
        with pytest.raises(ValueError, match="min_value must be <= max_value"):
            RangeRule(min_value=10, max_value=5)

    def test_min_equals_max_allowed(self) -> None:
        rule = RangeRule(min_value=5, max_value=5)
        assert rule.apply("p", 5).accepted is True

    def test_no_bounds_allowed(self) -> None:
        rule = RangeRule()  # 無下界也無上界
        result = rule.apply("p", 12345.0)
        assert result.accepted is True
        assert result.effective_value == 12345.0


class TestRangeRuleAcceptReject:
    def test_within_range_accepts(self) -> None:
        rule = RangeRule(min_value=0, max_value=100)
        r = rule.apply("setpoint", 50.0)
        assert r.accepted is True
        assert r.effective_value == 50.0

    def test_below_min_rejects_when_clamp_false(self) -> None:
        rule = RangeRule(min_value=0, max_value=100, clamp=False)
        r = rule.apply("setpoint", -5)
        assert r.accepted is False
        assert "below min" in r.reason

    def test_above_max_rejects_when_clamp_false(self) -> None:
        rule = RangeRule(min_value=0, max_value=100, clamp=False)
        r = rule.apply("setpoint", 150)
        assert r.accepted is False
        assert "above max" in r.reason

    def test_below_min_clamps(self) -> None:
        rule = RangeRule(min_value=0, max_value=100, clamp=True)
        r = rule.apply("setpoint", -5)
        assert r.accepted is True
        assert r.effective_value == 0

    def test_above_max_clamps(self) -> None:
        rule = RangeRule(min_value=0, max_value=100, clamp=True)
        r = rule.apply("setpoint", 150)
        assert r.accepted is True
        assert r.effective_value == 100


class TestRangeRuleNaNInfGuard:
    """bug-lesson: numerical-safety-layered — NaN/Inf 必須顯式 reject，
    否則 NaN 與 <、> 比較皆 False 會 silent accept。"""

    def test_nan_rejected_regardless_of_clamp(self) -> None:
        for clamp in (True, False):
            rule = RangeRule(min_value=0, max_value=100, clamp=clamp)
            r = rule.apply("p", float("nan"))
            assert r.accepted is False
            assert "not finite" in r.reason

    def test_positive_inf_rejected(self) -> None:
        rule = RangeRule(min_value=0, max_value=100, clamp=True)
        r = rule.apply("p", math.inf)
        assert r.accepted is False

    def test_negative_inf_rejected(self) -> None:
        rule = RangeRule(min_value=0, max_value=100, clamp=True)
        r = rule.apply("p", -math.inf)
        assert r.accepted is False

    def test_finite_float_still_works(self) -> None:
        rule = RangeRule(min_value=-1e6, max_value=1e6)
        assert rule.apply("p", 3.14).accepted is True


class TestWriteValidationRuleProtocol:
    def test_range_rule_satisfies_protocol(self) -> None:
        rule: WriteValidationRule = RangeRule(min_value=0, max_value=100)
        assert isinstance(rule, WriteValidationRule)

    def test_custom_class_satisfies_protocol(self) -> None:
        class Custom:
            def apply(self, point_name: str, value: object) -> ValidationResult:
                return ValidationResult.accept(value)

        custom = Custom()
        assert isinstance(custom, WriteValidationRule)

    def test_missing_apply_does_not_satisfy_protocol(self) -> None:
        class Broken:
            pass

        assert not isinstance(Broken(), WriteValidationRule)
