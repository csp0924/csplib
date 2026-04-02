# =============== DroopStrategy Tests ===============
#
# 測試 DroopStrategy 下垂控制一次頻率響應策略
# 包含：正常執行、死區、邊界條件、無頻率資料 fail-safe、配置驗證

import pytest

from csp_lib.controller.core import Command, ExecutionMode, StrategyContext, SystemBase
from csp_lib.controller.strategies.droop_strategy import DroopConfig, DroopStrategy

# =============== DroopConfig Tests ===============


class TestDroopConfig:
    """DroopConfig 配置驗證測試"""

    def test_default_config_values(self):
        """預設配置應有合理的初始值"""
        cfg = DroopConfig()
        assert cfg.f_base == 60.0
        assert cfg.droop == 0.05
        assert cfg.deadband == 0.0
        assert cfg.rated_power == 0.0
        assert cfg.max_droop_power == 0.0
        assert cfg.interval == 0.3

    def test_validate_passes_with_defaults(self):
        """預設配置應通過驗證"""
        cfg = DroopConfig()
        cfg.validate()  # should not raise

    def test_validate_droop_must_be_positive(self):
        """droop <= 0 應拋出 ValueError"""
        with pytest.raises(ValueError, match="droop must be positive"):
            DroopConfig(droop=0).validate()
        with pytest.raises(ValueError, match="droop must be positive"):
            DroopConfig(droop=-0.01).validate()

    def test_validate_f_base_must_be_positive(self):
        """f_base <= 0 應拋出 ValueError"""
        with pytest.raises(ValueError, match="f_base must be positive"):
            DroopConfig(f_base=0).validate()
        with pytest.raises(ValueError, match="f_base must be positive"):
            DroopConfig(f_base=-50.0).validate()

    def test_validate_deadband_must_be_non_negative(self):
        """deadband < 0 應拋出 ValueError"""
        with pytest.raises(ValueError, match="deadband must be non-negative"):
            DroopConfig(deadband=-0.01).validate()

    def test_validate_rated_power_must_be_non_negative(self):
        """rated_power < 0 應拋出 ValueError"""
        with pytest.raises(ValueError, match="rated_power must be non-negative"):
            DroopConfig(rated_power=-100).validate()

    def test_validate_max_droop_power_must_be_non_negative(self):
        """max_droop_power < 0 應拋出 ValueError"""
        with pytest.raises(ValueError, match="max_droop_power must be non-negative"):
            DroopConfig(max_droop_power=-1).validate()

    def test_validate_interval_must_be_positive(self):
        """interval <= 0 應拋出 ValueError"""
        with pytest.raises(ValueError, match="interval must be positive"):
            DroopConfig(interval=0).validate()
        with pytest.raises(ValueError, match="interval must be positive"):
            DroopConfig(interval=-1).validate()

    def test_from_dict_filters_unknown_keys(self):
        """from_dict 應忽略未知欄位"""
        cfg = DroopConfig.from_dict({"f_base": 50.0, "droop": 0.04, "unknown_key": 999})
        assert cfg.f_base == 50.0
        assert cfg.droop == 0.04

    def test_to_dict_roundtrip(self):
        """to_dict 應能還原所有欄位"""
        cfg = DroopConfig(f_base=50.0, droop=0.04, deadband=0.1, rated_power=500.0)
        d = cfg.to_dict()
        assert d["f_base"] == 50.0
        assert d["droop"] == 0.04
        assert d["deadband"] == 0.1
        assert d["rated_power"] == 500.0


# =============== DroopStrategy Tests ===============


class TestDroopStrategy:
    """DroopStrategy 下垂控制策略測試"""

    # --------------- 正常執行 ---------------

    def test_execute_frequency_below_base_produces_positive_power(self):
        """頻率低於基準 -> 正功率 (放電)
        freq=59.7, f_base=60, droop=0.05
        gain = 100 / (60 * 0.05) = 33.333...
        pct = -33.333 * (59.7 - 60) = -33.333 * (-0.3) = 10.0
        droop_power = 500 * 10.0 / 100 = 50.0
        total = 0 + 50 = 50.0
        """
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strategy = DroopStrategy(config)
        ctx = StrategyContext(extra={"frequency": 59.7})

        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(50.0)
        assert cmd.q_target == 0.0

    def test_execute_frequency_above_base_produces_negative_power(self):
        """頻率高於基準 -> 負功率 (充電)
        freq=60.3, error=+0.3
        pct = -33.333 * 0.3 = -10.0
        droop_power = 500 * (-10) / 100 = -50.0
        total = 0 + (-50) = -50.0
        """
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strategy = DroopStrategy(config)
        ctx = StrategyContext(extra={"frequency": 60.3})

        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(-50.0)
        assert cmd.q_target == 0.0

    def test_execute_with_schedule_p(self):
        """droop_power 應疊加 schedule_p
        freq=59.7 -> droop_power=50, schedule_p=100
        total = 100 + 50 = 150
        """
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strategy = DroopStrategy(config)
        ctx = StrategyContext(extra={"frequency": 59.7, "schedule_p": 100.0})

        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(150.0)

    def test_execute_at_exact_base_frequency_produces_zero(self):
        """頻率恰好等於基準 -> 0 功率"""
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strategy = DroopStrategy(config)
        ctx = StrategyContext(extra={"frequency": 60.0})

        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(0.0)
        assert cmd.q_target == 0.0

    # --------------- 死區 (deadband) ---------------

    def test_deadband_within_range_no_response(self):
        """頻率偏差在死區內 -> pct=0, 只返回 schedule_p"""
        config = DroopConfig(f_base=60.0, droop=0.05, deadband=0.2, rated_power=500.0)
        strategy = DroopStrategy(config)

        # freq=60.1, error=0.1, |0.1| <= 0.2 -> deadband
        ctx = StrategyContext(extra={"frequency": 60.1, "schedule_p": 80.0})
        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(80.0)  # schedule_p only, no droop

    def test_deadband_at_boundary_no_response(self):
        """頻率偏差接近死區邊界但仍在內 -> 不響應
        Note: exact boundary (60.2 - 60.0) suffers from float representation;
        use a value clearly within deadband to test the <= condition reliably.
        """
        config = DroopConfig(f_base=60.0, droop=0.05, deadband=0.2, rated_power=500.0)
        strategy = DroopStrategy(config)

        # |error| = 0.19 < deadband=0.2 -> within deadband
        ctx = StrategyContext(extra={"frequency": 60.19})
        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(0.0)

    def test_deadband_just_outside_responds(self):
        """頻率偏差剛好超出死區 -> 應響應"""
        config = DroopConfig(f_base=60.0, droop=0.05, deadband=0.2, rated_power=500.0)
        strategy = DroopStrategy(config)

        # freq=59.79, error=-0.21, |error| > 0.2 -> outside deadband
        ctx = StrategyContext(extra={"frequency": 59.79})
        cmd = strategy.execute(ctx)

        # Should produce positive power (frequency below base)
        assert cmd.p_target > 0.0

    def test_deadband_zero_always_responds(self):
        """deadband=0 時，任何頻率偏差都應響應"""
        config = DroopConfig(f_base=60.0, droop=0.05, deadband=0.0, rated_power=500.0)
        strategy = DroopStrategy(config)

        ctx = StrategyContext(extra={"frequency": 60.001})
        cmd = strategy.execute(ctx)

        # Very small but non-zero response
        assert cmd.p_target != 0.0

    # --------------- 邊界條件 ---------------

    def test_output_clamped_to_rated_power(self):
        """輸出應被限制在 [-rated_power, rated_power]
        freq=57.0, error=-3.0, gain=33.333
        pct = -33.333 * (-3) = 100.0 (clamped to 100)
        droop_power = 500 * 100 / 100 = 500
        total = 0 + 500 = 500 (= rated_power, clamped)
        """
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strategy = DroopStrategy(config)

        # Extreme low frequency
        ctx = StrategyContext(extra={"frequency": 57.0})
        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(500.0)

    def test_output_clamped_negative_direction(self):
        """負方向也應被限制在 -rated_power"""
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strategy = DroopStrategy(config)

        # Extreme high frequency
        ctx = StrategyContext(extra={"frequency": 63.0})
        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(-500.0)

    def test_pct_clamped_to_100(self):
        """pct 應被限制在 [-100, 100]
        freq=50.0, error=-10.0
        pct = -33.333 * (-10) = 333.33 -> clamped to 100
        """
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=1000.0)
        strategy = DroopStrategy(config)

        ctx = StrategyContext(extra={"frequency": 50.0})
        cmd = strategy.execute(ctx)

        # droop_power = 1000 * 100 / 100 = 1000, total clamped to rated_power
        assert cmd.p_target == pytest.approx(1000.0)

    def test_max_droop_power_limits_output(self):
        """max_droop_power 應限制 droop_power 的絕對值
        freq=59.7, droop_power=50, but max_droop_power=30 -> clamp to 30
        total = 0 + 30 = 30
        """
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0, max_droop_power=30.0)
        strategy = DroopStrategy(config)

        ctx = StrategyContext(extra={"frequency": 59.7})
        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(30.0)

    def test_rated_power_zero_returns_schedule_p_only(self):
        """rated_power=0 且無 system_base -> 只返回 schedule_p"""
        config = DroopConfig(rated_power=0.0)
        strategy = DroopStrategy(config)

        ctx = StrategyContext(extra={"frequency": 59.5, "schedule_p": 42.0})
        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(42.0)
        assert cmd.q_target == 0.0

    def test_rated_power_resolved_from_system_base(self):
        """rated_power=0 時應從 system_base.p_base 取值
        system_base.p_base=1000, freq=59.7
        gain = 33.333, pct = 10.0, droop_power = 1000 * 10 / 100 = 100
        """
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=0.0)
        strategy = DroopStrategy(config)

        ctx = StrategyContext(
            system_base=SystemBase(p_base=1000.0),
            extra={"frequency": 59.7},
        )
        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(100.0)

    def test_config_rated_power_takes_priority_over_system_base(self):
        """config.rated_power > 0 時優先於 system_base.p_base"""
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strategy = DroopStrategy(config)

        ctx = StrategyContext(
            system_base=SystemBase(p_base=1000.0),
            extra={"frequency": 59.7},
        )
        cmd = strategy.execute(ctx)

        # Uses config.rated_power=500, not system_base.p_base=1000
        assert cmd.p_target == pytest.approx(50.0)

    # --------------- 無頻率資料 fail-safe ---------------

    def test_missing_frequency_returns_last_command(self):
        """context.extra 無 frequency -> 返回 last_command"""
        config = DroopConfig(rated_power=500.0)
        strategy = DroopStrategy(config)

        last_cmd = Command(p_target=123.0, q_target=45.0)
        ctx = StrategyContext(last_command=last_cmd, extra={})

        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(123.0)
        assert cmd.q_target == pytest.approx(45.0)

    def test_missing_frequency_returns_default_command_when_no_last(self):
        """無 frequency 且無 last_command -> 返回預設 Command(0,0)"""
        strategy = DroopStrategy(DroopConfig(rated_power=500.0))
        ctx = StrategyContext(extra={})

        cmd = strategy.execute(ctx)

        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0

    def test_frequency_none_explicit_returns_last_command(self):
        """frequency=None (明確設定) 也應返回 last_command"""
        strategy = DroopStrategy(DroopConfig(rated_power=500.0))
        last_cmd = Command(p_target=200.0)
        ctx = StrategyContext(last_command=last_cmd, extra={"frequency": None})

        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(200.0)

    def test_frequency_lost_then_recovered(self):
        """頻率資料遺失後恢復 -> 應重新計算"""
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strategy = DroopStrategy(config)

        # First call with frequency: active
        ctx1 = StrategyContext(extra={"frequency": 59.7})
        cmd1 = strategy.execute(ctx1)
        assert cmd1.p_target == pytest.approx(50.0)

        # Second call without frequency: hold last
        ctx2 = StrategyContext(last_command=cmd1, extra={})
        cmd2 = strategy.execute(ctx2)
        assert cmd2.p_target == pytest.approx(50.0)  # holds last

        # Third call with frequency recovered
        ctx3 = StrategyContext(extra={"frequency": 60.3})
        cmd3 = strategy.execute(ctx3)
        assert cmd3.p_target == pytest.approx(-50.0)  # recalculated

    # --------------- update_config ---------------

    def test_update_config_changes_behavior(self):
        """update_config 應更新策略行為"""
        strategy = DroopStrategy(DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0))

        # Before update
        ctx = StrategyContext(extra={"frequency": 59.7})
        cmd1 = strategy.execute(ctx)
        assert cmd1.p_target == pytest.approx(50.0)

        # Update to different droop coefficient
        strategy.update_config(DroopConfig(f_base=60.0, droop=0.10, rated_power=500.0))

        # After update: gain = 100 / (60 * 0.10) = 16.667
        # pct = -16.667 * (-0.3) = 5.0, droop_power = 500 * 5 / 100 = 25
        cmd2 = strategy.execute(ctx)
        assert cmd2.p_target == pytest.approx(25.0)

    def test_config_property_reflects_current(self):
        """config property 應反映當前配置"""
        original = DroopConfig(droop=0.05)
        strategy = DroopStrategy(original)
        assert strategy.config is original

        new_cfg = DroopConfig(droop=0.10)
        strategy.update_config(new_cfg)
        assert strategy.config is new_cfg

    # --------------- execution_config ---------------

    def test_execution_config_periodic_mode(self):
        """執行模式應為 PERIODIC"""
        strategy = DroopStrategy()
        assert strategy.execution_config.mode == ExecutionMode.PERIODIC

    def test_execution_config_interval_min_1(self):
        """interval < 1 時, ExecutionConfig.interval_seconds 最小為 1"""
        strategy = DroopStrategy(DroopConfig(interval=0.3))
        assert strategy.execution_config.interval_seconds == 1

    def test_execution_config_interval_from_config(self):
        """interval >= 1 時應使用 int 截斷"""
        strategy = DroopStrategy(DroopConfig(interval=5.7))
        assert strategy.execution_config.interval_seconds == 5

    # --------------- lifecycle ---------------

    @pytest.mark.asyncio
    async def test_on_activate_resets_active_state(self):
        """on_activate 應重置 _active 狀態"""
        config = DroopConfig(rated_power=500.0)
        strategy = DroopStrategy(config)

        # Make it active
        strategy.execute(StrategyContext(extra={"frequency": 60.0}))
        assert strategy._active is True

        # on_activate should reset
        await strategy.on_activate()
        assert strategy._active is False

    @pytest.mark.asyncio
    async def test_on_deactivate_resets_active_state(self):
        """on_deactivate 應重置 _active 狀態"""
        config = DroopConfig(rated_power=500.0)
        strategy = DroopStrategy(config)

        # Make it active
        strategy.execute(StrategyContext(extra={"frequency": 60.0}))
        assert strategy._active is True

        await strategy.on_deactivate()
        assert strategy._active is False

    # --------------- str ---------------

    def test_str_representation(self):
        """__str__ 應包含關鍵配置"""
        strategy = DroopStrategy(DroopConfig(f_base=60.0, droop=0.05, deadband=0.2))
        s = str(strategy)
        assert "60.0" in s
        assert "0.05" in s
        assert "0.2" in s

    # --------------- 50Hz system ---------------

    def test_50hz_system(self):
        """應支援 50Hz 系統
        f_base=50, freq=49.8, droop=0.04
        gain = 100 / (50 * 0.04) = 50.0
        pct = -50 * (49.8 - 50) = -50 * (-0.2) = 10.0
        droop_power = 1000 * 10 / 100 = 100
        """
        config = DroopConfig(f_base=50.0, droop=0.04, rated_power=1000.0)
        strategy = DroopStrategy(config)

        ctx = StrategyContext(extra={"frequency": 49.8})
        cmd = strategy.execute(ctx)

        assert cmd.p_target == pytest.approx(100.0)
