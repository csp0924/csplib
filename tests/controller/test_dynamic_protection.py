"""Tests for dynamic protection rules: DynamicSOCProtection, GridLimitProtection, RampStopProtection."""

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.system.dynamic_protection import (
    DynamicSOCProtection,
    GridLimitProtection,
    RampStopProtection,
)
from csp_lib.core.runtime_params import RuntimeParameters

# ===========================================================================
# DynamicSOCProtection
# ===========================================================================


class TestDynamicSOCProtection:
    def _make(self, params: RuntimeParameters, **kwargs) -> DynamicSOCProtection:
        return DynamicSOCProtection(params, **kwargs)

    # --- Basic properties ---

    def test_name(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        assert rule.name == "dynamic_soc_protection"

    def test_initial_is_triggered_false(self):
        params = RuntimeParameters()
        rule = self._make(params)
        assert rule.is_triggered is False

    # --- SOC is None ---

    def test_soc_none_passthrough(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=100.0)
        ctx = StrategyContext(soc=None)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(100.0)
        assert rule.is_triggered is False

    # --- SOC >= soc_max (block charging) ---

    def test_soc_at_max_block_charging(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=-100.0)  # charging
        ctx = StrategyContext(soc=95.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)
        assert rule.is_triggered is True

    def test_soc_above_max_block_charging(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=-500.0)
        ctx = StrategyContext(soc=98.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)
        assert rule.is_triggered is True

    def test_soc_at_max_allow_discharge(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=100.0)  # discharging
        ctx = StrategyContext(soc=95.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(100.0)
        assert rule.is_triggered is False

    # --- SOC <= soc_min (block discharging) ---

    def test_soc_at_min_block_discharge(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=100.0)  # discharging
        ctx = StrategyContext(soc=5.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)
        assert rule.is_triggered is True

    def test_soc_below_min_block_discharge(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=200.0)
        ctx = StrategyContext(soc=2.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)
        assert rule.is_triggered is True

    def test_soc_at_min_allow_charging(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=-100.0)  # charging
        ctx = StrategyContext(soc=5.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(-100.0)
        assert rule.is_triggered is False

    # --- Normal range (no trigger) ---

    def test_soc_in_normal_range_passthrough(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext(soc=50.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(100.0)
        assert result.q_target == pytest.approx(50.0)
        assert rule.is_triggered is False

    # --- Warning band (gradual limiting) ---

    def test_high_warning_band_limits_charging(self):
        """SOC in high warning zone: charging should be reduced proportionally."""
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params, warning_band=5.0)
        cmd = Command(p_target=-100.0)  # charging
        # SOC=93 is within [90, 95) warning zone; ratio = (95-93)/5 = 0.4
        ctx = StrategyContext(soc=93.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(-100.0 * 0.4)
        assert rule.is_triggered is True

    def test_low_warning_band_limits_discharging(self):
        """SOC in low warning zone: discharging should be reduced proportionally."""
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params, warning_band=5.0)
        cmd = Command(p_target=100.0)  # discharging
        # SOC=7 is within (5, 10] warning zone; ratio = (7-5)/5 = 0.4
        ctx = StrategyContext(soc=7.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(100.0 * 0.4)
        assert rule.is_triggered is True

    def test_warning_band_zero_no_gradual(self):
        """warning_band=0 should not apply gradual limiting."""
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params, warning_band=0.0)
        cmd = Command(p_target=-100.0)
        ctx = StrategyContext(soc=93.0)
        result = rule.evaluate(cmd, ctx)
        # No warning band, 93 < 95 and > 5 -> passthrough
        assert result.p_target == pytest.approx(-100.0)
        assert rule.is_triggered is False

    # --- Dynamic parameter updates ---

    def test_dynamic_soc_max_update(self):
        """Changing soc_max in RuntimeParameters at runtime should take effect."""
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = self._make(params)
        cmd = Command(p_target=-100.0)

        # SOC=90 is fine with soc_max=95
        ctx = StrategyContext(soc=90.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(-100.0)

        # Now lower soc_max to 85 -> SOC=90 >= 85 -> block charging
        params.set("soc_max", 85.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)
        assert rule.is_triggered is True

    # --- Custom key names ---

    def test_custom_key_names(self):
        params = RuntimeParameters(my_max=80.0, my_min=20.0)
        rule = self._make(params, soc_max_key="my_max", soc_min_key="my_min")
        cmd = Command(p_target=-50.0)
        ctx = StrategyContext(soc=85.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)
        assert rule.is_triggered is True

    # --- Default values when keys missing ---

    def test_defaults_when_keys_missing(self):
        """When keys are not in params, defaults (95/5) should be used."""
        params = RuntimeParameters()  # no soc_max, no soc_min
        rule = self._make(params)
        cmd = Command(p_target=-100.0)
        ctx = StrategyContext(soc=96.0)  # > default 95
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)

    # --- BUG-003: soc_max < soc_min (反轉配置) ---
    #
    # 現象：當使用者誤將 soc_max / soc_min 寫反（例如 soc_max=30, soc_min=70），
    # 保護邏輯會同時禁止充電與放電，導致系統完全無法運作。
    # 修復後：明確拋 ValueError（不自動 swap），讓配置錯誤立即可見，
    # 由上層 ProtectionGuard 捕捉並由配置端修正。

    def test_soc_max_less_than_soc_min_raises_value_error_on_charging(self):
        """
        BUG-003：soc_max=30, soc_min=70（反轉配置）→ evaluate 應拋 ValueError
        充電命令場景驗證。
        """
        params = RuntimeParameters(soc_max=30.0, soc_min=70.0)
        rule = self._make(params)
        cmd = Command(p_target=-100.0)  # charging
        ctx = StrategyContext(soc=50.0)
        with pytest.raises(ValueError, match="soc_max .* < soc_min"):
            rule.evaluate(cmd, ctx)

    def test_soc_max_less_than_soc_min_raises_value_error_on_discharging(self):
        """
        BUG-003：放電命令場景同樣應拋 ValueError，行為一致。
        """
        params = RuntimeParameters(soc_max=30.0, soc_min=70.0)
        rule = self._make(params)
        cmd = Command(p_target=100.0)  # discharging
        ctx = StrategyContext(soc=50.0)
        with pytest.raises(ValueError, match="soc_max .* < soc_min"):
            rule.evaluate(cmd, ctx)


# ===========================================================================
# GridLimitProtection
# ===========================================================================


class TestGridLimitProtection:
    def _make(self, params: RuntimeParameters, rated: float = 1000.0, **kwargs) -> GridLimitProtection:
        return GridLimitProtection(params, total_rated_kw=rated, **kwargs)

    def test_name(self):
        params = RuntimeParameters()
        rule = self._make(params)
        assert rule.name == "grid_limit_protection"

    def test_initial_is_triggered_false(self):
        params = RuntimeParameters()
        rule = self._make(params)
        assert rule.is_triggered is False

    # --- No limit (100%) ---

    def test_no_limit_passthrough(self):
        params = RuntimeParameters(grid_limit_pct=100)
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=1000.0)
        ctx = StrategyContext()
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(1000.0)
        assert rule.is_triggered is False

    # --- Discharge over limit ---

    def test_discharge_clamped_to_limit(self):
        params = RuntimeParameters(grid_limit_pct=50)
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=800.0)  # over 500
        ctx = StrategyContext()
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(500.0)
        assert rule.is_triggered is True

    # --- Charge over limit ---

    def test_charge_clamped_to_negative_limit(self):
        params = RuntimeParameters(grid_limit_pct=50)
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=-800.0)  # more negative than -500
        ctx = StrategyContext()
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(-500.0)
        assert rule.is_triggered is True

    # --- Within limit ---

    def test_within_limit_passthrough(self):
        params = RuntimeParameters(grid_limit_pct=50)
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=300.0)
        ctx = StrategyContext()
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(300.0)
        assert rule.is_triggered is False

    # --- Dynamic update ---

    def test_dynamic_limit_change(self):
        params = RuntimeParameters(grid_limit_pct=100)
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=800.0)
        ctx = StrategyContext()

        # 100% -> 800 is fine
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(800.0)

        # Now drop to 50% -> 800 > 500 -> clamp
        params.set("grid_limit_pct", 50)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(500.0)

    # --- Zero limit ---

    def test_zero_limit_clamps_to_zero(self):
        params = RuntimeParameters(grid_limit_pct=0)
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=100.0)
        ctx = StrategyContext()
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)
        assert rule.is_triggered is True

    # --- Default 100% when key missing ---

    def test_default_100_when_key_missing(self):
        params = RuntimeParameters()  # no grid_limit_pct
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=999.0)
        ctx = StrategyContext()
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(999.0)
        assert rule.is_triggered is False

    # --- Custom key ---

    def test_custom_limit_key(self):
        params = RuntimeParameters(my_limit=30)
        rule = self._make(params, rated=1000.0, limit_key="my_limit")
        cmd = Command(p_target=500.0)
        ctx = StrategyContext()
        result = rule.evaluate(cmd, ctx)
        # max_p = 1000 * 30 / 100 = 300
        assert result.p_target == pytest.approx(300.0)
        assert rule.is_triggered is True

    # --- Q target preserved ---

    def test_q_target_preserved(self):
        params = RuntimeParameters(grid_limit_pct=50)
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=800.0, q_target=200.0)
        ctx = StrategyContext()
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(500.0)
        assert result.q_target == pytest.approx(200.0)


# ===========================================================================
# RampStopProtection
# ===========================================================================


class TestRampStopProtection:
    def _make(self, params: RuntimeParameters, rated: float = 1000.0, **kwargs) -> RampStopProtection:
        defaults = {"interval_seconds": 1.0}
        defaults.update(kwargs)
        return RampStopProtection(params, total_rated_kw=rated, **defaults)

    def test_name(self):
        params = RuntimeParameters()
        rule = self._make(params)
        assert rule.name == "ramp_stop_protection"

    def test_initial_is_triggered_false(self):
        params = RuntimeParameters()
        rule = self._make(params)
        assert rule.is_triggered is False

    # --- Not triggered ---

    def test_not_triggered_passthrough(self):
        params = RuntimeParameters(battery_status=0)
        rule = self._make(params)
        cmd = Command(p_target=500.0)
        ctx = StrategyContext(last_command=Command(p_target=500.0))
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(500.0)
        assert rule.is_triggered is False

    def test_trigger_key_missing_passthrough(self):
        params = RuntimeParameters()
        rule = self._make(params)
        cmd = Command(p_target=500.0)
        ctx = StrategyContext(last_command=Command(p_target=500.0))
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(500.0)
        assert rule.is_triggered is False

    # --- Triggered, ramp down from positive P ---

    def test_ramp_down_positive_p(self):
        """When triggered, P should ramp down by ramp_step each call."""
        params = RuntimeParameters(battery_status=1, ramp_rate=10.0)
        rule = self._make(params, rated=1000.0, interval_seconds=1.0)
        # ramp_step = 10/100 * 1000 * 1 = 100 kW
        ctx = StrategyContext(last_command=Command(p_target=500.0))
        cmd = Command(p_target=500.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(400.0)  # 500 - 100
        assert rule.is_triggered is True

    # --- Triggered, ramp down from negative P (charging) ---

    def test_ramp_down_negative_p(self):
        """When triggered with negative P (charging), ramp toward 0."""
        params = RuntimeParameters(battery_status=1, ramp_rate=10.0)
        rule = self._make(params, rated=1000.0, interval_seconds=1.0)
        # ramp_step = 100
        ctx = StrategyContext(last_command=Command(p_target=-500.0))
        cmd = Command(p_target=-500.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(-400.0)  # -500 + 100
        assert rule.is_triggered is True

    # --- Ramp completes to zero ---

    def test_ramp_reaches_zero(self):
        """When |current_p| <= ramp_step, should go directly to 0."""
        params = RuntimeParameters(battery_status=1, ramp_rate=10.0)
        rule = self._make(params, rated=1000.0, interval_seconds=1.0)
        # ramp_step = 100, current_p = 50 < 100 -> target = 0
        ctx = StrategyContext(last_command=Command(p_target=50.0))
        cmd = Command(p_target=50.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)

    def test_ramp_reaches_zero_negative(self):
        """Same for negative current_p."""
        params = RuntimeParameters(battery_status=1, ramp_rate=10.0)
        rule = self._make(params, rated=1000.0, interval_seconds=1.0)
        ctx = StrategyContext(last_command=Command(p_target=-50.0))
        cmd = Command(p_target=-50.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(0.0)

    # --- Different interval ---

    def test_shorter_interval_smaller_step(self):
        params = RuntimeParameters(battery_status=1, ramp_rate=10.0)
        rule = self._make(params, rated=1000.0, interval_seconds=0.3)
        # ramp_step = 10/100 * 1000 * 0.3 = 30
        ctx = StrategyContext(last_command=Command(p_target=500.0))
        cmd = Command(p_target=500.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(470.0)

    # --- Default ramp_rate when key missing ---

    def test_default_ramp_rate(self):
        params = RuntimeParameters(battery_status=1)
        rule = self._make(params, rated=1000.0, interval_seconds=1.0, default_ramp_rate=5.0)
        # ramp_step = 5/100 * 1000 * 1 = 50
        ctx = StrategyContext(last_command=Command(p_target=200.0))
        cmd = Command(p_target=200.0)
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(150.0)

    # --- Custom trigger key/value ---

    def test_custom_trigger_key_value(self):
        params = RuntimeParameters(my_flag=99)
        rule = self._make(
            params,
            rated=1000.0,
            trigger_key="my_flag",
            trigger_value=99,
        )
        ctx = StrategyContext(last_command=Command(p_target=300.0))
        cmd = Command(p_target=300.0)
        result = rule.evaluate(cmd, ctx)
        assert rule.is_triggered is True
        assert result.p_target < 300.0

    def test_wrong_trigger_value_passthrough(self):
        params = RuntimeParameters(battery_status=2)
        rule = self._make(params, trigger_value=1)
        cmd = Command(p_target=500.0)
        ctx = StrategyContext(last_command=Command(p_target=500.0))
        result = rule.evaluate(cmd, ctx)
        assert result.p_target == pytest.approx(500.0)
        assert rule.is_triggered is False

    # --- Dynamic trigger change ---

    def test_trigger_activation_deactivation(self):
        params = RuntimeParameters(battery_status=0, ramp_rate=10.0)
        rule = self._make(params, rated=1000.0)
        cmd = Command(p_target=500.0)
        ctx = StrategyContext(last_command=Command(p_target=500.0))

        # Not triggered
        result = rule.evaluate(cmd, ctx)
        assert rule.is_triggered is False
        assert result.p_target == pytest.approx(500.0)

        # Activate
        params.set("battery_status", 1)
        result = rule.evaluate(cmd, ctx)
        assert rule.is_triggered is True
        assert result.p_target < 500.0

    # --- Q target preserved ---

    def test_q_target_preserved(self):
        params = RuntimeParameters(battery_status=1, ramp_rate=10.0)
        rule = self._make(params, rated=1000.0, interval_seconds=1.0)
        ctx = StrategyContext(last_command=Command(p_target=500.0, q_target=200.0))
        cmd = Command(p_target=500.0, q_target=200.0)
        result = rule.evaluate(cmd, ctx)
        assert result.q_target == pytest.approx(200.0)
