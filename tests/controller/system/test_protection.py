"""Tests for ProtectionGuard and protection rules."""

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.system.protection import (
    ProtectionGuard,
    ProtectionResult,
    ReversePowerProtection,
    SOCProtection,
    SOCProtectionConfig,
    SystemAlarmProtection,
)


# =============== SOCProtection Tests ===============


class TestSOCProtection:
    def test_high_soc_clamps_charging(self):
        """SOC >= soc_high → 充電 (P<0) 被 clamp 為 0"""
        rule = SOCProtection(SOCProtectionConfig(soc_high=95.0))
        cmd = Command(p_target=-100.0, q_target=50.0)
        ctx = StrategyContext(soc=96.0)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0
        assert result.q_target == 50.0  # Q 不受影響
        assert rule.is_triggered is True

    def test_high_soc_allows_discharging(self):
        """SOC >= soc_high → 放電 (P>0) 不受影響"""
        rule = SOCProtection(SOCProtectionConfig(soc_high=95.0))
        cmd = Command(p_target=100.0)
        ctx = StrategyContext(soc=96.0)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 100.0
        assert rule.is_triggered is False

    def test_low_soc_clamps_discharging(self):
        """SOC <= soc_low → 放電 (P>0) 被 clamp 為 0"""
        rule = SOCProtection(SOCProtectionConfig(soc_low=5.0))
        cmd = Command(p_target=100.0, q_target=30.0)
        ctx = StrategyContext(soc=3.0)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0
        assert result.q_target == 30.0
        assert rule.is_triggered is True

    def test_low_soc_allows_charging(self):
        """SOC <= soc_low → 充電 (P<0) 不受影響"""
        rule = SOCProtection(SOCProtectionConfig(soc_low=5.0))
        cmd = Command(p_target=-100.0)
        ctx = StrategyContext(soc=3.0)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == -100.0
        assert rule.is_triggered is False

    def test_high_warning_zone_gradual(self):
        """高側警戒區：漸進限制充電"""
        rule = SOCProtection(SOCProtectionConfig(soc_high=95.0, warning_band=5.0))
        cmd = Command(p_target=-100.0)
        # SOC=92.5 → warning_high=90, ratio = (95-92.5)/5 = 0.5
        ctx = StrategyContext(soc=92.5)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(-50.0)
        assert rule.is_triggered is True

    def test_low_warning_zone_gradual(self):
        """低側警戒區：漸進限制放電"""
        rule = SOCProtection(SOCProtectionConfig(soc_low=5.0, warning_band=5.0))
        cmd = Command(p_target=100.0)
        # SOC=7.5 → warning_low=10, ratio = (7.5-5)/5 = 0.5
        ctx = StrategyContext(soc=7.5)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(50.0)
        assert rule.is_triggered is True

    def test_normal_soc_passthrough(self):
        """正常 SOC 不介入"""
        rule = SOCProtection()
        cmd = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext(soc=50.0)

        result = rule.evaluate(cmd, ctx)
        assert result == cmd
        assert rule.is_triggered is False

    def test_soc_none_passthrough(self):
        """SOC=None 不介入"""
        rule = SOCProtection()
        cmd = Command(p_target=100.0)
        ctx = StrategyContext(soc=None)

        result = rule.evaluate(cmd, ctx)
        assert result == cmd
        assert rule.is_triggered is False

    def test_boundary_soc_high(self):
        """SOC 剛好等於 soc_high"""
        rule = SOCProtection(SOCProtectionConfig(soc_high=95.0))
        cmd = Command(p_target=-50.0)
        ctx = StrategyContext(soc=95.0)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0
        assert rule.is_triggered is True

    def test_boundary_soc_low(self):
        """SOC 剛好等於 soc_low"""
        rule = SOCProtection(SOCProtectionConfig(soc_low=5.0))
        cmd = Command(p_target=50.0)
        ctx = StrategyContext(soc=5.0)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0
        assert rule.is_triggered is True

    def test_default_config(self):
        """預設配置"""
        rule = SOCProtection()
        assert rule.name == "soc_protection"

    def test_p_zero_passthrough_at_high_soc(self):
        """P=0 在高 SOC 不受影響"""
        rule = SOCProtection(SOCProtectionConfig(soc_high=95.0))
        cmd = Command(p_target=0.0)
        ctx = StrategyContext(soc=96.0)

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0
        assert rule.is_triggered is False


# =============== ReversePowerProtection Tests ===============


class TestReversePowerProtection:
    def test_discharge_exceeds_meter(self):
        """放電量超過表計讀數 → 限制"""
        rule = ReversePowerProtection(threshold=0.0)
        cmd = Command(p_target=200.0)
        ctx = StrategyContext(extra={"meter_power": 100.0})

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 100.0
        assert rule.is_triggered is True

    def test_discharge_within_meter(self):
        """放電量未超過表計讀數 → passthrough"""
        rule = ReversePowerProtection(threshold=0.0)
        cmd = Command(p_target=50.0)
        ctx = StrategyContext(extra={"meter_power": 100.0})

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 50.0
        assert rule.is_triggered is False

    def test_charging_not_limited(self):
        """充電 (P<0) 不受限"""
        rule = ReversePowerProtection(threshold=0.0)
        cmd = Command(p_target=-100.0)
        ctx = StrategyContext(extra={"meter_power": 50.0})

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == -100.0
        assert rule.is_triggered is False

    def test_with_threshold(self):
        """帶 threshold 的逆送保護"""
        rule = ReversePowerProtection(threshold=10.0)
        cmd = Command(p_target=120.0)
        ctx = StrategyContext(extra={"meter_power": 100.0})

        result = rule.evaluate(cmd, ctx)
        # max_discharge = 100 + 10 = 110
        assert result.p_target == 110.0
        assert rule.is_triggered is True

    def test_meter_none_passthrough(self):
        """meter_power=None 不介入"""
        rule = ReversePowerProtection()
        cmd = Command(p_target=100.0)
        ctx = StrategyContext()

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 100.0
        assert rule.is_triggered is False

    def test_meter_negative(self):
        """meter_power 為負（已逆送）→ 禁止放電"""
        rule = ReversePowerProtection(threshold=0.0)
        cmd = Command(p_target=50.0)
        ctx = StrategyContext(extra={"meter_power": -20.0})

        result = rule.evaluate(cmd, ctx)
        # max_discharge = max(0, -20 + 0) = 0
        assert result.p_target == 0.0
        assert rule.is_triggered is True

    def test_custom_meter_key(self):
        """自定義 meter_power key"""
        rule = ReversePowerProtection(meter_power_key="grid_power")
        cmd = Command(p_target=200.0)
        ctx = StrategyContext(extra={"grid_power": 100.0})

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 100.0
        assert rule.is_triggered is True

    def test_name(self):
        rule = ReversePowerProtection()
        assert rule.name == "reverse_power_protection"


# =============== SystemAlarmProtection Tests ===============


class TestSystemAlarmProtection:
    def test_alarm_active_forces_zero(self):
        """告警啟用 → P=0, Q=0"""
        rule = SystemAlarmProtection()
        cmd = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext(extra={"system_alarm": True})

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0
        assert result.q_target == 0.0
        assert rule.is_triggered is True

    def test_no_alarm_passthrough(self):
        """無告警 → passthrough"""
        rule = SystemAlarmProtection()
        cmd = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext(extra={"system_alarm": False})

        result = rule.evaluate(cmd, ctx)
        assert result == cmd
        assert rule.is_triggered is False

    def test_alarm_key_missing_passthrough(self):
        """告警 key 不存在 → passthrough"""
        rule = SystemAlarmProtection()
        cmd = Command(p_target=100.0)
        ctx = StrategyContext()

        result = rule.evaluate(cmd, ctx)
        assert result == cmd
        assert rule.is_triggered is False

    def test_custom_alarm_key(self):
        """自定義告警 key"""
        rule = SystemAlarmProtection(alarm_key="critical_alarm")
        cmd = Command(p_target=100.0)
        ctx = StrategyContext(extra={"critical_alarm": True})

        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0
        assert result.q_target == 0.0
        assert rule.is_triggered is True

    def test_name(self):
        rule = SystemAlarmProtection()
        assert rule.name == "system_alarm_protection"


# =============== ProtectionResult Tests ===============


class TestProtectionResult:
    def test_was_modified_true(self):
        result = ProtectionResult(
            original_command=Command(p_target=100.0),
            protected_command=Command(p_target=50.0),
            triggered_rules=["soc_protection"],
        )
        assert result.was_modified is True

    def test_was_modified_false(self):
        cmd = Command(p_target=100.0)
        result = ProtectionResult(
            original_command=cmd,
            protected_command=cmd,
        )
        assert result.was_modified is False

    def test_frozen(self):
        result = ProtectionResult(
            original_command=Command(),
            protected_command=Command(),
        )
        with pytest.raises(AttributeError):
            result.original_command = Command()  # type: ignore[misc]


# =============== ProtectionGuard Tests ===============


class TestProtectionGuard:
    def test_chain_apply(self):
        """多規則鏈式套用"""
        soc_rule = SOCProtection(SOCProtectionConfig(soc_high=95.0))
        alarm_rule = SystemAlarmProtection()

        guard = ProtectionGuard([soc_rule, alarm_rule])
        cmd = Command(p_target=-100.0)
        ctx = StrategyContext(soc=96.0)

        result = guard.apply(cmd, ctx)
        # SOC protection clamps P from -100 to 0
        assert result.protected_command.p_target == 0.0
        assert result.was_modified is True
        assert "soc_protection" in result.triggered_rules
        assert result.original_command is cmd

    def test_chain_apply_alarm_overrides_all(self):
        """系統告警覆蓋所有"""
        soc_rule = SOCProtection()
        alarm_rule = SystemAlarmProtection()

        guard = ProtectionGuard([soc_rule, alarm_rule])
        cmd = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext(soc=50.0, extra={"system_alarm": True})

        result = guard.apply(cmd, ctx)
        assert result.protected_command.p_target == 0.0
        assert result.protected_command.q_target == 0.0
        assert "system_alarm_protection" in result.triggered_rules

    def test_empty_rules_passthrough(self):
        """空規則列表 → passthrough"""
        guard = ProtectionGuard()
        cmd = Command(p_target=100.0)
        ctx = StrategyContext()

        result = guard.apply(cmd, ctx)
        assert result.protected_command == cmd
        assert result.was_modified is False
        assert result.triggered_rules == []

    def test_add_remove_rule(self):
        guard = ProtectionGuard()
        rule = SOCProtection()
        guard.add_rule(rule)
        assert len(guard.rules) == 1

        guard.remove_rule("soc_protection")
        assert len(guard.rules) == 0

    def test_last_result(self):
        guard = ProtectionGuard()
        assert guard.last_result is None

        cmd = Command(p_target=100.0)
        ctx = StrategyContext()
        result = guard.apply(cmd, ctx)
        assert guard.last_result is result

    def test_exception_in_rule_skipped(self):
        """規則異常時跳過"""

        class BrokenRule(SOCProtection):
            @property
            def name(self) -> str:
                return "broken_rule"

            def evaluate(self, command, context):
                raise RuntimeError("broken")

        guard = ProtectionGuard([BrokenRule(), SystemAlarmProtection()])
        cmd = Command(p_target=100.0)
        ctx = StrategyContext(extra={"system_alarm": True})

        result = guard.apply(cmd, ctx)
        # Broken rule skipped, alarm protection still applies
        assert result.protected_command.p_target == 0.0
        assert "system_alarm_protection" in result.triggered_rules
        assert "broken_rule" not in result.triggered_rules

    def test_triggered_tracking(self):
        """觸發追蹤"""
        soc = SOCProtection(SOCProtectionConfig(soc_high=95.0))
        reverse = ReversePowerProtection()
        alarm = SystemAlarmProtection()
        guard = ProtectionGuard([soc, reverse, alarm])

        cmd = Command(p_target=-100.0)
        ctx = StrategyContext(soc=96.0, extra={"meter_power": 50.0})

        result = guard.apply(cmd, ctx)
        # SOC clamps -100 to 0, reverse doesn't trigger on P<=0, alarm not set
        assert result.triggered_rules == ["soc_protection"]
