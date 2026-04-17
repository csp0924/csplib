# =============== QV / FP Strategy Dynamic Runtime Tests (v0.8.2) ===============
#
# 驗證 QVStrategy 和 FPStrategy 的 RuntimeParameters 動態化行為：
#   - 純 config 路徑等同 pre-v0.8.2 baseline
#   - param_keys + params 可動態覆蓋所有欄位
#   - 混合 mapping 的 fallback
#   - enabled_key falsy → Command(0, 0)
#   - ctor 錯誤驗證

from __future__ import annotations

import pytest

from csp_lib.controller.core import Command, StrategyContext, SystemBase
from csp_lib.controller.strategies.fp_strategy import FPConfig, FPStrategy
from csp_lib.controller.strategies.qv_strategy import QVConfig, QVStrategy
from csp_lib.core.runtime_params import RuntimeParameters


def _ctx_qv(voltage: float | None, params: RuntimeParameters | None = None) -> StrategyContext:
    """建立 QV 測試上下文（含 system_base 以啟用 percent_to_kvar）。"""
    extra: dict[str, object] = {}
    if voltage is not None:
        extra["voltage"] = voltage
    return StrategyContext(
        last_command=Command(),
        system_base=SystemBase(p_base=500.0, q_base=500.0),
        extra=extra,
        params=params,
    )


def _ctx_fp(frequency: float | None, params: RuntimeParameters | None = None) -> StrategyContext:
    """建立 FP 測試上下文（含 system_base 以啟用 percent_to_kw）。"""
    extra: dict[str, object] = {}
    if frequency is not None:
        extra["frequency"] = frequency
    return StrategyContext(
        last_command=Command(),
        system_base=SystemBase(p_base=500.0, q_base=500.0),
        extra=extra,
        params=params,
    )


# =============== QVStrategy Tests ===============


class TestQVRegressionBaseline:
    """純 config 路徑行為等同 v0.8.1。"""

    def test_pure_config_mode_voltage_low(self):
        """電壓偏低 → 正 Q。"""
        cfg = QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0, v_deadband=0.0)
        strat = QVStrategy(cfg)
        # 電壓偏低至 95% → 輸出正 Q（至 q_max_ratio 上限）
        cmd = strat.execute(_ctx_qv(voltage=361.0))  # 361/380 ≈ 0.95
        assert cmd.q_target > 0
        assert cmd.p_target == 0.0


class TestQVDynamicParams:
    """params + param_keys 動態化。"""

    def test_full_dynamic_equals_equivalent_config(self):
        """所有欄位動態化 → 與等價 config baseline 結果一致。"""
        params = RuntimeParameters(
            nominal_voltage=380.0,
            v_set=100.0,
            droop=5.0,
            v_deadband=0.0,
            q_max_ratio=0.5,
        )
        dyn = QVStrategy(
            QVConfig(nominal_voltage=220.0, v_set=100.0, droop=3.0),  # 基底刻意不同
            params=params,
            param_keys={
                "nominal_voltage": "nominal_voltage",
                "v_set": "v_set",
                "droop": "droop",
                "v_deadband": "v_deadband",
                "q_max_ratio": "q_max_ratio",
            },
        )
        baseline = QVStrategy(QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0))
        assert dyn.execute(_ctx_qv(370.0, params)).q_target == pytest.approx(baseline.execute(_ctx_qv(370.0)).q_target)

    def test_mixed_mapping_fallback(self):
        """只動態化 droop，其餘 fallback config。"""
        cfg = QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0, v_deadband=0.0)
        params = RuntimeParameters(droop=3.0)
        strat = QVStrategy(cfg, params=params, param_keys={"droop": "droop"})
        # droop 變小 → 輸出 Q 比值變大（但受 q_max_ratio 上限）
        cmd_dyn = strat.execute(_ctx_qv(370.0, params))
        cmd_static = QVStrategy(cfg).execute(_ctx_qv(370.0))
        assert cmd_dyn.q_target >= cmd_static.q_target

    def test_params_set_reflects_next_execute(self):
        """params 變更立即反映。"""
        cfg = QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0, v_deadband=0.0)
        params = RuntimeParameters(droop=5.0)
        strat = QVStrategy(cfg, params=params, param_keys={"droop": "droop"})
        first = strat.execute(_ctx_qv(370.0, params)).q_target
        params.set("droop", 3.0)  # droop 變小 → Q 比值變大
        second = strat.execute(_ctx_qv(370.0, params)).q_target
        assert second >= first


class TestQVEnabledKey:
    """enabled_key falsy → Command(0, 0)。"""

    def test_enabled_false_returns_zero_command(self):
        """params[enabled_key]=False → 立即停止 Q 輸出。"""
        params = RuntimeParameters(qv_enabled=False)
        strat = QVStrategy(
            QVConfig(nominal_voltage=380.0),
            params=params,
            param_keys={"droop": "droop"},
            enabled_key="qv_enabled",
        )
        cmd = strat.execute(_ctx_qv(370.0, params))
        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0


class TestQVCtorErrors:
    """ctor 驗證。"""

    def test_params_none_with_param_keys_raises(self):
        with pytest.raises(ValueError, match="params and param_keys"):
            QVStrategy(QVConfig(), params=None, param_keys={"droop": "droop"})


# =============== FPStrategy Tests ===============


class TestFPRegressionBaseline:
    """純 config 路徑行為等同 v0.8.1。"""

    def test_pure_config_mode_low_frequency_max_discharge(self):
        """頻率低於 f1 → 最大放電（p1）。"""
        cfg = FPConfig()  # 預設 f_base=60, f1=-0.5 → 59.5 Hz
        strat = FPStrategy(cfg)
        cmd = strat.execute(_ctx_fp(frequency=59.0))  # < 59.5
        # p1=100% → p_kw = 500 * 100 / 100 = 500
        assert cmd.p_target == pytest.approx(500.0)
        assert cmd.q_target == 0.0


class TestFPDynamicParams:
    """FP params + param_keys 動態化。"""

    def test_full_dynamic_equals_equivalent_config(self):
        """全欄位動態化 → 結果等同對應 config。"""
        # 新 f_base=50 + 偏移 → 用 params 覆蓋
        params = RuntimeParameters(
            f_base=50.0,
            f1=-0.5,
            f2=-0.25,
            f3=-0.02,
            f4=0.02,
            f5=0.25,
            f6=0.5,
            p1=100.0,
            p2=52.0,
            p3=9.0,
            p4=-9.0,
            p5=-52.0,
            p6=-100.0,
        )
        keys = {k: k for k in ("f_base", "f1", "f2", "f3", "f4", "f5", "f6", "p1", "p2", "p3", "p4", "p5", "p6")}
        dyn = FPStrategy(FPConfig(f_base=60.0), params=params, param_keys=keys)
        baseline = FPStrategy(FPConfig(f_base=50.0))  # 其餘用預設

        # 測試 50-0.3 = 49.7 Hz 在 f1(49.5)~f2(49.75) 之間
        assert dyn.execute(_ctx_fp(49.7, params)).p_target == pytest.approx(baseline.execute(_ctx_fp(49.7)).p_target)

    def test_mixed_mapping_fallback(self):
        """只動態化 f_base，其餘 fallback config。"""
        cfg = FPConfig(f_base=60.0)
        params = RuntimeParameters(f_base=50.0)
        strat = FPStrategy(cfg, params=params, param_keys={"f_base": "f_base"})
        # f_base 變為 50 → 49.0 Hz 會低於 f1(49.5) → max discharge p1=100%
        cmd = strat.execute(_ctx_fp(49.0, params))
        assert cmd.p_target == pytest.approx(500.0)  # 100% of 500

    def test_params_set_reflects_next_execute(self):
        """變更 params.f_base → 同一 frequency 進不同曲線區段。"""
        cfg = FPConfig(f_base=60.0)
        params = RuntimeParameters(f_base=60.0)
        strat = FPStrategy(cfg, params=params, param_keys={"f_base": "f_base"})
        # 60.0 Hz 在死區 (f3~f4) 內，p=0
        first = strat.execute(_ctx_fp(60.0, params)).p_target
        params.set("f_base", 50.0)
        # 現 f_base=50，60.0 Hz 遠高於 f6(50.5) → max charge p6=-100%
        second = strat.execute(_ctx_fp(60.0, params)).p_target
        assert first != second
        assert second == pytest.approx(-500.0)


class TestFPEnabledKey:
    """FP enabled_key falsy → Command(0, 0)。"""

    def test_enabled_false_returns_zero_command(self):
        """params[enabled_key]=0 → 立即停止。"""
        params = RuntimeParameters(fp_enabled=0)
        strat = FPStrategy(
            FPConfig(),
            params=params,
            param_keys={"f_base": "f_base"},
            enabled_key="fp_enabled",
        )
        cmd = strat.execute(_ctx_fp(59.0, params))
        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0


class TestFPCtorErrors:
    """FP ctor 驗證。"""

    def test_params_none_with_param_keys_raises(self):
        with pytest.raises(ValueError, match="params and param_keys"):
            FPStrategy(FPConfig(), params=None, param_keys={"f_base": "f_base"})
