# =============== PVSmoothStrategy Dynamic Runtime Tests (v0.8.2) ===============
#
# 驗證 PVSmoothStrategy 的 RuntimeParameters 動態化行為：
#   - 純 config 路徑回歸（不提供 params/param_keys 時與 v0.8.1 一致）
#   - params + param_keys 動態覆蓋所有欄位
#   - 混合 fallback（部分欄位動態化）
#   - params.set() 即時反映
#   - enabled_key=0 → Command(0, 0)（安全降級）
#   - ctor 驗證（params / param_keys 不對稱）

from __future__ import annotations

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.services import PVDataService
from csp_lib.controller.strategies.pv_smooth_strategy import PVSmoothConfig, PVSmoothStrategy
from csp_lib.core.runtime_params import RuntimeParameters


def _ctx(last_p: float = 0.0, params: RuntimeParameters | None = None) -> StrategyContext:
    return StrategyContext(last_command=Command(p_target=last_p, q_target=0.0), params=params)


def _svc(samples: list[float]) -> PVDataService:
    """建立帶歷史資料的 PVDataService。"""
    svc = PVDataService(max_history=max(len(samples), 1))
    for v in samples:
        svc.append(v)
    return svc


# =============== 1. 回歸：純 config 路徑 ===============


class TestPVSmoothConfigOnlyRegression:
    def test_pure_config_basic_average(self):
        """僅 config：應回傳受 ramp_rate 限制的平均值。"""
        cfg = PVSmoothConfig(capacity=1000.0, ramp_rate=10.0, pv_loss=0.0, min_history=1)
        svc = _svc([500.0, 500.0, 500.0])  # avg=500
        strat = PVSmoothStrategy(cfg, pv_service=svc)

        # last_p=0, ramp_limit=100kW → target=min(500, 0+100)=100
        cmd = strat.execute(_ctx(last_p=0.0))
        assert cmd.p_target == pytest.approx(100.0)
        assert cmd.q_target == 0.0


# =============== 2. 動態化：全欄位 ===============


class TestPVSmoothDynamicParams:
    def test_full_dynamic_equals_config_baseline(self):
        """所有欄位動態化後，結果等同於等價 config。"""
        # baseline: capacity=2000, ramp_rate=20% → ramp_limit=400
        baseline_cfg = PVSmoothConfig(capacity=2000.0, ramp_rate=20.0, pv_loss=50.0, min_history=2)
        svc_base = _svc([600.0, 600.0])
        baseline = PVSmoothStrategy(baseline_cfg, pv_service=svc_base)
        baseline_cmd = baseline.execute(_ctx(last_p=0.0))

        # dyn: config 刻意不同，用 params 覆蓋
        params = RuntimeParameters(
            pv_capacity=2000.0,
            pv_ramp=20.0,
            pv_loss=50.0,
            pv_min_hist=2,
        )
        svc_dyn = _svc([600.0, 600.0])
        dyn = PVSmoothStrategy(
            PVSmoothConfig(capacity=100.0, ramp_rate=5.0, pv_loss=0.0, min_history=1),
            pv_service=svc_dyn,
            params=params,
            param_keys={
                "capacity": "pv_capacity",
                "ramp_rate": "pv_ramp",
                "pv_loss": "pv_loss",
                "min_history": "pv_min_hist",
            },
        )
        dyn_cmd = dyn.execute(_ctx(last_p=0.0, params=params))
        assert dyn_cmd.p_target == pytest.approx(baseline_cmd.p_target)

    def test_mixed_mapping_fallback(self):
        """只動態化 ramp_rate；其餘 fallback 到 config。"""
        cfg = PVSmoothConfig(capacity=1000.0, ramp_rate=10.0, pv_loss=0.0, min_history=1)
        svc = _svc([800.0])
        # params 將 ramp_rate 升到 50% → ramp_limit=500 → target=min(800, 500)=500
        params = RuntimeParameters(pv_ramp=50.0)
        strat = PVSmoothStrategy(cfg, pv_service=svc, params=params, param_keys={"ramp_rate": "pv_ramp"})

        cmd = strat.execute(_ctx(last_p=0.0, params=params))
        assert cmd.p_target == pytest.approx(500.0)

    def test_params_set_reflects_next_execute(self):
        """params.set() 後下次 execute 立即反映。"""
        cfg = PVSmoothConfig(capacity=1000.0, ramp_rate=10.0, pv_loss=0.0, min_history=1)
        svc = _svc([800.0, 800.0, 800.0])
        params = RuntimeParameters(pv_ramp=10.0)
        strat = PVSmoothStrategy(cfg, pv_service=svc, params=params, param_keys={"ramp_rate": "pv_ramp"})

        # 初始 ramp_rate=10% → ramp_limit=100
        cmd1 = strat.execute(_ctx(last_p=0.0, params=params))
        assert cmd1.p_target == pytest.approx(100.0)

        # 變更 ramp_rate → 下次 execute 反映
        params.set("pv_ramp", 30.0)  # ramp_limit=300
        cmd2 = strat.execute(_ctx(last_p=0.0, params=params))
        assert cmd2.p_target == pytest.approx(300.0)


# =============== 3. enabled_key ===============


class TestPVSmoothEnabledKey:
    def test_enabled_zero_returns_zero_command(self):
        """params[enabled_key]=0 → Command(0, 0)（不跑後續運算）。"""
        cfg = PVSmoothConfig(capacity=1000.0, ramp_rate=10.0)
        svc = _svc([500.0, 500.0])
        params = RuntimeParameters(pv_on=0)
        strat = PVSmoothStrategy(
            cfg,
            pv_service=svc,
            params=params,
            param_keys={"capacity": "pv_capacity"},
            enabled_key="pv_on",
        )
        cmd = strat.execute(_ctx(last_p=500.0, params=params))
        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0


# =============== 4. ctor 驗證 ===============


class TestPVSmoothCtorErrors:
    def test_params_with_no_param_keys_raises(self):
        """傳 params 卻未傳 param_keys → ValueError。"""
        with pytest.raises(ValueError, match="params and param_keys"):
            PVSmoothStrategy(PVSmoothConfig(), params=RuntimeParameters(), param_keys=None)
