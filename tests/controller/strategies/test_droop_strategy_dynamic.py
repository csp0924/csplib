# =============== DroopStrategy Dynamic Runtime Tests (v0.8.2) ===============
#
# 驗證 DroopStrategy 的 RuntimeParameters 動態化行為：
#   - 純 config 路徑等同 pre-v0.8.2 baseline
#   - param_keys + params 可動態覆蓋 f_base/droop/deadband/rated_power/max_droop_power
#   - droop_scale 套用於 droop 欄位
#   - enabled_key / schedule_p_key 行為
#   - ctor 錯誤驗證

from __future__ import annotations

import pytest

from csp_lib.controller.core import Command, StrategyContext, SystemBase
from csp_lib.controller.strategies.droop_strategy import DroopConfig, DroopStrategy
from csp_lib.core.runtime_params import RuntimeParameters


def _make_context(
    frequency: float | None = 59.8,
    schedule_p: float = 0.0,
    rated: float = 500.0,
    params: RuntimeParameters | None = None,
) -> StrategyContext:
    """建立帶 frequency + system_base 的 StrategyContext。"""
    extra: dict[str, object] = {}
    if frequency is not None:
        extra["frequency"] = frequency
    if schedule_p != 0.0:
        extra["schedule_p"] = schedule_p
    return StrategyContext(
        last_command=Command(),
        system_base=SystemBase(p_base=rated, q_base=rated),
        extra=extra,
        params=params,
    )


class TestDroopRegressionBaseline:
    """純 config 路徑行為等同 v0.8.1（無 params / param_keys）。"""

    def test_pure_config_mode_produces_same_result_as_baseline(self):
        """config-only 模式：正常 droop 計算。"""
        cfg = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        strat = DroopStrategy(cfg)
        ctx = _make_context(frequency=59.8, rated=500.0)
        cmd = strat.execute(ctx)
        # 頻率 59.8，偏差 -0.2；gain = 100/(60*0.05) = 33.33；pct = -33.33 * -0.2 = 6.667
        # droop_power = 500 * 6.667/100 = 33.33
        assert cmd.p_target == pytest.approx(33.333, abs=0.01)
        assert cmd.q_target == 0.0

    def test_deadband_still_zero_output(self):
        """死區內行為不變。"""
        cfg = DroopConfig(f_base=60.0, droop=0.05, deadband=0.5, rated_power=500.0)
        strat = DroopStrategy(cfg)
        ctx = _make_context(frequency=60.2)  # |偏差|=0.2 < deadband 0.5
        cmd = strat.execute(ctx)
        assert cmd.p_target == pytest.approx(0.0)


class TestDroopDynamicParams:
    """params + param_keys 動態化行為。"""

    def test_full_dynamic_equals_equivalent_config(self):
        """所有欄位透過 params → 結果等同用對應 config 建構。"""
        params = RuntimeParameters(
            f_base=60.0,
            droop=0.05,
            deadband=0.0,
            rated_power=500.0,
            max_droop_power=0.0,
        )
        dyn = DroopStrategy(
            DroopConfig(f_base=50.0, droop=0.10),  # 基底 config 刻意亂填
            params=params,
            param_keys={
                "f_base": "f_base",
                "droop": "droop",
                "deadband": "deadband",
                "rated_power": "rated_power",
                "max_droop_power": "max_droop_power",
            },
        )
        baseline = DroopStrategy(
            DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0),
        )
        ctx_dyn = _make_context(frequency=59.9, params=params)
        ctx_base = _make_context(frequency=59.9)
        assert dyn.execute(ctx_dyn).p_target == pytest.approx(baseline.execute(ctx_base).p_target)

    def test_mixed_mapping_fallback_to_config(self):
        """只對 droop 建 mapping，其餘欄位 fallback config。"""
        cfg = DroopConfig(f_base=60.0, droop=0.10, rated_power=500.0)
        params = RuntimeParameters(droop=0.05)
        strat = DroopStrategy(cfg, params=params, param_keys={"droop": "droop"})
        ctx = _make_context(frequency=59.8, params=params)
        # f_base 從 config (60)，droop 從 params (0.05) → gain=33.33 → pct=6.667 → 33.33
        assert strat.execute(ctx).p_target == pytest.approx(33.333, abs=0.01)

    def test_params_set_reflects_next_execute(self):
        """變更 params 後下次 execute 立即反映。"""
        cfg = DroopConfig(f_base=60.0, droop=0.10, rated_power=500.0)
        params = RuntimeParameters(droop=0.10)
        strat = DroopStrategy(cfg, params=params, param_keys={"droop": "droop"})
        ctx = _make_context(frequency=59.8, params=params)
        first = strat.execute(ctx).p_target
        params.set("droop", 0.05)  # droop 變小 → gain 變大 → pct 變大 → p 變大
        second = strat.execute(ctx).p_target
        assert second > first

    def test_param_key_missing_in_params_falls_back_to_config(self):
        """param_keys 提到的 key 但 params 沒這個值 → fallback config，不拋錯。"""
        cfg = DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0)
        params = RuntimeParameters()  # 空 params
        strat = DroopStrategy(
            cfg,
            params=params,
            param_keys={"droop": "droop_pct"},  # 映射存在但 params 沒此 key
        )
        ctx = _make_context(frequency=59.8, params=params)
        cmd = strat.execute(ctx)
        # 應 fallback 到 config.droop=0.05
        assert cmd.p_target == pytest.approx(33.333, abs=0.01)


class TestDroopScale:
    """droop_scale 套用倍率。"""

    def test_droop_scale_converts_percent_to_fraction(self):
        """EMS 傳 5.0（%）且 scale=0.01 → 等同 DroopConfig(droop=0.05)。"""
        params = RuntimeParameters(ramp_rate=5.0)
        dyn = DroopStrategy(
            DroopConfig(f_base=60.0, rated_power=500.0),
            params=params,
            param_keys={"droop": "ramp_rate"},
            droop_scale=0.01,
        )
        baseline = DroopStrategy(DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0))
        ctx_dyn = _make_context(frequency=59.8, params=params)
        ctx_base = _make_context(frequency=59.8)
        assert dyn.execute(ctx_dyn).p_target == pytest.approx(baseline.execute(ctx_base).p_target, abs=0.01)


class TestDroopEnabledKey:
    """enabled_key 旗標行為。"""

    def test_enabled_false_returns_schedule_p_only(self):
        """params[enabled_key]=False → 回傳 Command(schedule_p, 0)。"""
        params = RuntimeParameters(droop_enabled=False, schedule_p=120.0)
        strat = DroopStrategy(
            DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0),
            params=params,
            param_keys={"droop": "droop"},
            enabled_key="droop_enabled",
            schedule_p_key="schedule_p",
        )
        ctx = _make_context(frequency=59.5, params=params)
        cmd = strat.execute(ctx)
        assert cmd.p_target == 120.0
        assert cmd.q_target == 0.0

    def test_enabled_false_no_schedule_key_returns_zero(self):
        """enabled=False 且未設 schedule_p_key → p_target=0。"""
        params = RuntimeParameters(droop_enabled=0)
        strat = DroopStrategy(
            DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0),
            params=params,
            param_keys={"droop": "droop"},
            enabled_key="droop_enabled",
        )
        ctx = _make_context(frequency=59.5, params=params)
        cmd = strat.execute(ctx)
        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0

    def test_enabled_true_runs_droop_calculation(self):
        """params[enabled_key]=True → 正常走 droop 計算。"""
        params = RuntimeParameters(droop_enabled=True)
        strat = DroopStrategy(
            DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0),
            params=params,
            param_keys={"droop": "droop"},
            enabled_key="droop_enabled",
        )
        ctx = _make_context(frequency=59.8, params=params)
        cmd = strat.execute(ctx)
        # 正常 droop 計算 → p_target 非零
        assert cmd.p_target == pytest.approx(33.333, abs=0.01)


class TestDroopScheduleP:
    """schedule_p_key 優先於 context.extra['schedule_p']。"""

    def test_schedule_p_from_params_takes_priority(self):
        """params 有 schedule_p_key 值 → 優先於 context.extra。"""
        params = RuntimeParameters(sched_p=50.0)
        strat = DroopStrategy(
            DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0),
            params=params,
            param_keys={"droop": "droop"},
            schedule_p_key="sched_p",
        )
        # context.extra['schedule_p']=200 會被 params.sched_p=50 覆蓋
        ctx = StrategyContext(
            last_command=Command(),
            system_base=SystemBase(p_base=500.0, q_base=500.0),
            extra={"frequency": 60.0, "schedule_p": 200.0},  # deadband=0 → droop_power=0
            params=params,
        )
        cmd = strat.execute(ctx)
        # 60.0 == f_base → pct=0 → droop_power=0，只剩 schedule_p=50（非 200）
        assert cmd.p_target == pytest.approx(50.0)

    def test_schedule_p_fallback_to_context_extra(self):
        """未設 schedule_p_key → 讀 context.extra['schedule_p']。"""
        strat = DroopStrategy(DroopConfig(f_base=60.0, droop=0.05, rated_power=500.0))
        ctx = StrategyContext(
            last_command=Command(),
            system_base=SystemBase(p_base=500.0, q_base=500.0),
            extra={"frequency": 60.0, "schedule_p": 77.0},
        )
        cmd = strat.execute(ctx)
        assert cmd.p_target == pytest.approx(77.0)


class TestDroopCtorErrors:
    """ctor 輸入驗證。"""

    def test_params_none_but_param_keys_provided_raises(self):
        """params=None 但 param_keys 非 None → ValueError（從 ParamResolver 傳出）。"""
        cfg = DroopConfig()
        with pytest.raises(ValueError, match="params and param_keys"):
            DroopStrategy(cfg, params=None, param_keys={"droop": "droop"})
