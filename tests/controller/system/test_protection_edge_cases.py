from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.system.protection import (
    ProtectionGuard,
    ProtectionRule,
    ReversePowerProtection,
    SOCProtection,
    SOCProtectionConfig,
)


class TestSOCProtectionEdgeCases:
    def test_soc_none_no_intervention(self):
        rule = SOCProtection()
        cmd = Command(p_target=-100)
        ctx = StrategyContext(soc=None)
        result = rule.evaluate(cmd, ctx)
        assert result == cmd
        assert not rule.is_triggered

    def test_soc_exactly_at_high_boundary(self):
        config = SOCProtectionConfig(soc_high=95.0, soc_low=5.0, warning_band=5.0)
        rule = SOCProtection(config)
        cmd = Command(p_target=-100)  # charging
        ctx = StrategyContext(soc=95.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0  # blocked

    def test_soc_exactly_at_low_boundary(self):
        config = SOCProtectionConfig(soc_high=95.0, soc_low=5.0, warning_band=5.0)
        rule = SOCProtection(config)
        cmd = Command(p_target=100)  # discharging
        ctx = StrategyContext(soc=5.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == 0.0  # blocked

    def test_soc_warning_band_zero(self):
        """No warning zone when warning_band=0"""
        config = SOCProtectionConfig(soc_high=95.0, soc_low=5.0, warning_band=0.0)
        rule = SOCProtection(config)
        cmd = Command(p_target=-100)  # charging
        ctx = StrategyContext(soc=93.0)  # below soc_high, no warning band
        result = rule.evaluate(cmd, ctx)
        assert result == cmd  # no intervention

    def test_soc_in_warning_zone_gradual_limit(self):
        config = SOCProtectionConfig(soc_high=95.0, soc_low=5.0, warning_band=5.0)
        rule = SOCProtection(config)
        cmd = Command(p_target=-100)  # charging
        # SOC=92.5 -> in warning zone (90-95), ratio = (95-92.5)/5 = 0.5
        ctx = StrategyContext(soc=92.5)
        result = rule.evaluate(cmd, ctx)
        assert abs(result.p_target - (-50.0)) < 0.1  # -100 * 0.5 = -50


class TestReversePowerEdgeCases:
    def test_meter_none_no_intervention(self):
        rule = ReversePowerProtection()
        cmd = Command(p_target=500)
        ctx = StrategyContext(extra={})
        result = rule.evaluate(cmd, ctx)
        assert result == cmd

    def test_charging_not_affected(self):
        rule = ReversePowerProtection()
        cmd = Command(p_target=-100)  # charging
        ctx = StrategyContext(extra={"meter_power": 10})
        result = rule.evaluate(cmd, ctx)
        assert result == cmd


class TestProtectionGuardEdgeCases:
    def test_empty_rules(self):
        guard = ProtectionGuard(rules=[])
        cmd = Command(p_target=100)
        ctx = StrategyContext()
        result = guard.apply(cmd, ctx)
        assert result.protected_command == cmd
        assert not result.was_modified

    def test_rule_exception_skipped(self):
        """If a rule raises, it is skipped and logged"""

        class BrokenRule(ProtectionRule):
            @property
            def name(self) -> str:
                return "broken"

            @property
            def is_triggered(self) -> bool:
                return False

            def evaluate(self, command, context):
                raise RuntimeError("rule error")

        guard = ProtectionGuard(rules=[BrokenRule()])
        cmd = Command(p_target=100)
        ctx = StrategyContext()
        result = guard.apply(cmd, ctx)
        assert result.protected_command == cmd
