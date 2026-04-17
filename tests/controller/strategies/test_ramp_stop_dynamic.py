# =============== RampStopStrategy Dynamic Runtime Tests (v0.8.2) ===============
#
# 驗證 RampStopStrategy 的 RuntimeParameters 動態化行為：
#   - 純 config 路徑回歸：既有 positional ctor 100% 不變
#   - params + param_keys 動態覆蓋 rated_power / ramp_rate_pct
#   - 混合 fallback
#   - params.set() 即時反映（下次 execute 步幅變化）
#   - enabled_key falsy → 回 context.last_command（保守策略）
#   - ctor 驗證

from __future__ import annotations

from unittest.mock import patch

import pytest

from csp_lib.controller.core import Command, ExecutionMode, StrategyContext
from csp_lib.controller.strategies.ramp_stop import RampStopStrategy
from csp_lib.core.runtime_params import RuntimeParameters


def _ctx(last_p: float = 500.0, params: RuntimeParameters | None = None) -> StrategyContext:
    return StrategyContext(last_command=Command(p_target=last_p, q_target=0.0), params=params)


# =============== 1. 回歸：既有 positional ctor 完全相容 ===============


class TestRampStopPositionalCtorBackwardCompat:
    """verify pre-v0.8.2 呼叫路徑 100% 相容。"""

    def test_positional_ctor_basic_ramp(self):
        """原呼叫方式：兩個 positional args，無 kwargs。"""
        strat = RampStopStrategy(2000, 5.0)  # rated_power, ramp_rate_pct

        # execution_config 不變
        ec = strat.execution_config
        assert ec.mode == ExecutionMode.PERIODIC
        assert ec.interval_seconds == 1

        # 執行邏輯不變：dt=1s, rate=5%, rated=2000 → step=100
        with patch("csp_lib.controller.strategies.ramp_stop.time.monotonic", side_effect=[100.0, 101.0]):
            cmd1 = strat.execute(_ctx(last_p=500.0))  # 第一次 dt=0, 繼承 500
            assert cmd1.p_target == pytest.approx(500.0)
            cmd2 = strat.execute(_ctx(last_p=500.0))  # dt=1s, step=100
            assert cmd2.p_target == pytest.approx(400.0)

    def test_ctor_rated_power_only(self):
        """僅傳 rated_power，ramp_rate_pct 使用預設 5.0。"""
        strat = RampStopStrategy(1000)
        with patch("csp_lib.controller.strategies.ramp_stop.time.monotonic", side_effect=[0.0, 1.0]):
            strat.execute(_ctx(last_p=500.0))
            cmd2 = strat.execute(_ctx(last_p=500.0))
            # rated=1000, rate=5%, dt=1s → step=50
            assert cmd2.p_target == pytest.approx(450.0)


# =============== 2. 動態化：params 覆蓋 ===============


class TestRampStopDynamicParams:
    def test_full_dynamic_overrides_config(self):
        """params 同時覆蓋 rated_power 與 ramp_rate_pct → step 使用 runtime 值。"""
        params = RuntimeParameters(rated=1000.0, rate=10.0)
        strat = RampStopStrategy(
            100.0,  # 基底刻意很小
            1.0,
            params=params,
            param_keys={"rated_power": "rated", "ramp_rate_pct": "rate"},
        )
        with patch("csp_lib.controller.strategies.ramp_stop.time.monotonic", side_effect=[0.0, 1.0]):
            strat.execute(_ctx(last_p=500.0, params=params))
            cmd = strat.execute(_ctx(last_p=500.0, params=params))
            # runtime: rated=1000, rate=10%, dt=1s → step=100
            assert cmd.p_target == pytest.approx(400.0)

    def test_mixed_mapping_fallback(self):
        """只動態化 ramp_rate_pct，rated_power fallback 到 ctor 值。"""
        params = RuntimeParameters(rate=20.0)
        strat = RampStopStrategy(
            1000.0,
            5.0,
            params=params,
            param_keys={"ramp_rate_pct": "rate"},
        )
        with patch("csp_lib.controller.strategies.ramp_stop.time.monotonic", side_effect=[0.0, 1.0]):
            strat.execute(_ctx(last_p=500.0, params=params))
            cmd = strat.execute(_ctx(last_p=500.0, params=params))
            # rated=1000 (config), rate=20% (runtime), dt=1s → step=200
            assert cmd.p_target == pytest.approx(300.0)

    def test_params_set_reflects_next_execute(self):
        """params.set() 後下次 execute 步幅變化。"""
        params = RuntimeParameters(rate=5.0)
        strat = RampStopStrategy(1000.0, 1.0, params=params, param_keys={"ramp_rate_pct": "rate"})

        with patch("csp_lib.controller.strategies.ramp_stop.time.monotonic", side_effect=[0.0, 1.0, 2.0]):
            # t=0 初始化 current_p=500
            strat.execute(_ctx(last_p=500.0, params=params))
            # t=1, rate=5% → step=50 → p=450
            cmd1 = strat.execute(_ctx(last_p=500.0, params=params))
            assert cmd1.p_target == pytest.approx(450.0)
            # 改為 rate=30%
            params.set("rate", 30.0)
            # t=2, rate=30%, dt=1s → step=300 → 450-300=150
            cmd2 = strat.execute(_ctx(last_p=500.0, params=params))
            assert cmd2.p_target == pytest.approx(150.0)


# =============== 3. enabled_key 保守策略 ===============


class TestRampStopEnabledKey:
    def test_enabled_zero_returns_last_command(self):
        """enabled_key falsy → 保守回 context.last_command（不跑 ramp）。"""
        params = RuntimeParameters(rs_on=False)
        strat = RampStopStrategy(
            1000.0,
            5.0,
            params=params,
            param_keys={"ramp_rate_pct": "rate"},
            enabled_key="rs_on",
        )
        cmd = strat.execute(_ctx(last_p=777.0, params=params))
        assert cmd.p_target == pytest.approx(777.0)
        assert cmd.q_target == 0.0


# =============== 4. ctor 驗證 ===============


class TestRampStopCtorErrors:
    def test_params_without_param_keys_raises(self):
        with pytest.raises(ValueError, match="params and param_keys"):
            RampStopStrategy(1000.0, params=RuntimeParameters(), param_keys=None)
