# =============== RampStopStrategy Tests ===============
#
# 測試斜坡降功率策略：
#   - 斜坡降功率（正功率 / 負功率）
#   - 到零停止並維持
#   - 中途恢復（on_activate / on_deactivate 重置狀態）
#   - 參數配置
#   - execution_config 為 PERIODIC

from unittest.mock import patch

import pytest

from csp_lib.controller.core import Command, ExecutionMode, StrategyContext
from csp_lib.controller.strategies.ramp_stop import RampStopStrategy


class TestRampStopConfiguration:
    """RampStopStrategy 參數與 execution_config 測試"""

    def test_execution_config_is_periodic(self):
        """execution_config 應為 PERIODIC mode，interval=1s"""
        strategy = RampStopStrategy(rated_power=2000)
        config = strategy.execution_config

        assert config.mode == ExecutionMode.PERIODIC
        assert config.interval_seconds == 1

    def test_default_ramp_rate(self):
        """預設 ramp_rate_pct 為 5.0"""
        # v0.8.2: 內部改以 _config (_RampStopRuntimeConfig) 儲存
        strategy = RampStopStrategy(rated_power=1000)
        assert strategy._config.ramp_rate_pct == 5.0
        assert strategy._config.rated_power == 1000

    def test_custom_ramp_rate(self):
        """可自訂 ramp_rate_pct"""
        strategy = RampStopStrategy(rated_power=2000, ramp_rate_pct=10.0)
        assert strategy._config.ramp_rate_pct == 10.0

    def test_str_representation(self):
        """__str__ 應包含 rated 和 rate 資訊"""
        strategy = RampStopStrategy(rated_power=2000, ramp_rate_pct=5.0)
        result = str(strategy)
        assert "2000" in result
        assert "5.0" in result


class TestRampStopExecution:
    """RampStopStrategy execute 斜坡降功率測試"""

    def _make_context(self, p_target: float = 0.0) -> StrategyContext:
        return StrategyContext(last_command=Command(p_target=p_target, q_target=0.0))

    def test_ramp_down_positive_power(self):
        """正功率應逐步降低：rated=2000, rate=5%/s, dt=1s → step=100kW"""
        strategy = RampStopStrategy(rated_power=2000, ramp_rate_pct=5.0)
        ctx = self._make_context(p_target=500.0)

        # Mock monotonic to control dt precisely
        t = 100.0
        with patch("csp_lib.controller.strategies.ramp_stop.time.monotonic", side_effect=[t, t + 1.0, t + 2.0]):
            # First call: dt=0, inherits p=500 from last_command
            cmd1 = strategy.execute(ctx)
            assert cmd1.p_target == pytest.approx(500.0)

            # Second call: dt=1s, step=100kW → 500-100=400
            cmd2 = strategy.execute(ctx)
            assert cmd2.p_target == pytest.approx(400.0)

            # Third call: dt=1s, step=100kW → 400-100=300
            cmd3 = strategy.execute(ctx)
            assert cmd3.p_target == pytest.approx(300.0)

        assert cmd3.q_target == 0.0

    def test_ramp_down_negative_power(self):
        """負功率（充電）應逐步升向零：rated=1000, rate=10%/s, dt=1s → step=100kW"""
        strategy = RampStopStrategy(rated_power=1000, ramp_rate_pct=10.0)
        ctx = self._make_context(p_target=-300.0)

        t = 100.0
        with patch("csp_lib.controller.strategies.ramp_stop.time.monotonic", side_effect=[t, t + 1.0, t + 2.0]):
            cmd1 = strategy.execute(ctx)
            assert cmd1.p_target == pytest.approx(-300.0)

            # dt=1s, step=100, abs(-300)>100 and current_p<0 → -300+100=-200
            cmd2 = strategy.execute(ctx)
            assert cmd2.p_target == pytest.approx(-200.0)

            cmd3 = strategy.execute(ctx)
            assert cmd3.p_target == pytest.approx(-100.0)

    def test_reaches_zero_and_stays(self):
        """功率降至零後應維持 P=0"""
        strategy = RampStopStrategy(rated_power=1000, ramp_rate_pct=50.0)
        # rate=50%/s → step=500kW/s. Starting at 400kW with dt=1s → abs(400)<500 → snap to 0
        ctx = self._make_context(p_target=400.0)

        t = 100.0
        with patch(
            "csp_lib.controller.strategies.ramp_stop.time.monotonic",
            side_effect=[t, t + 1.0, t + 2.0, t + 3.0],
        ):
            cmd1 = strategy.execute(ctx)
            assert cmd1.p_target == pytest.approx(400.0)  # first call inherits

            cmd2 = strategy.execute(ctx)
            assert cmd2.p_target == pytest.approx(0.0)  # abs(400) <= 500 → snap to 0

            # Subsequent calls stay at zero
            cmd3 = strategy.execute(ctx)
            assert cmd3.p_target == pytest.approx(0.0)

    def test_last_command_zero_stays_zero(self):
        """若 last_command 已是 0，第一次執行即返回 0"""
        strategy = RampStopStrategy(rated_power=2000)
        ctx = self._make_context(p_target=0.0)

        t = 100.0
        with patch("csp_lib.controller.strategies.ramp_stop.time.monotonic", return_value=t):
            cmd = strategy.execute(ctx)
            assert cmd.p_target == pytest.approx(0.0)
            assert cmd.q_target == pytest.approx(0.0)


class TestRampStopLifecycle:
    """on_activate / on_deactivate 狀態重置測試"""

    @pytest.mark.asyncio
    async def test_on_activate_resets_state(self):
        """on_activate 應重置 _current_p 和 _last_time"""
        strategy = RampStopStrategy(rated_power=2000, ramp_rate_pct=5.0)
        # Simulate partial ramp
        strategy._current_p = 300.0
        strategy._last_time = 12345.0

        await strategy.on_activate()

        assert strategy._current_p == 0.0
        assert strategy._last_time is None

    @pytest.mark.asyncio
    async def test_on_deactivate_resets_state(self):
        """on_deactivate 應重置狀態，使下次啟動從新的 last_command 開始"""
        strategy = RampStopStrategy(rated_power=2000)
        strategy._current_p = 150.0
        strategy._last_time = 99999.0

        await strategy.on_deactivate()

        assert strategy._current_p == 0.0
        assert strategy._last_time is None

    @pytest.mark.asyncio
    async def test_mid_ramp_deactivate_then_reactivate(self):
        """中途 deactivate 再 activate 後，應從新的 last_command 重新開始 ramp"""
        strategy = RampStopStrategy(rated_power=1000, ramp_rate_pct=10.0)
        ctx_initial = StrategyContext(last_command=Command(p_target=500.0))

        t = 100.0
        with patch(
            "csp_lib.controller.strategies.ramp_stop.time.monotonic",
            side_effect=[t, t + 1.0],
        ):
            # Start ramp from 500
            cmd1 = strategy.execute(ctx_initial)
            assert cmd1.p_target == pytest.approx(500.0)

            # One step: 500 - 100 = 400
            cmd2 = strategy.execute(ctx_initial)
            assert cmd2.p_target == pytest.approx(400.0)

        # Deactivate mid-ramp
        await strategy.on_deactivate()

        # Re-activate with different power
        await strategy.on_activate()

        ctx_new = StrategyContext(last_command=Command(p_target=200.0))
        t2 = 200.0
        with patch(
            "csp_lib.controller.strategies.ramp_stop.time.monotonic",
            side_effect=[t2, t2 + 1.0],
        ):
            # Should start fresh from 200, not continue from 400
            cmd3 = strategy.execute(ctx_new)
            assert cmd3.p_target == pytest.approx(200.0)

            # 200 - 100 = 100
            cmd4 = strategy.execute(ctx_new)
            assert cmd4.p_target == pytest.approx(100.0)
