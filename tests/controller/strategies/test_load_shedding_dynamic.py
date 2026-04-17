# =============== LoadSheddingStrategy Dynamic Runtime Tests (v0.8.2) ===============
#
# 驗證 LoadSheddingStrategy 的 RuntimeParameters 動態化行為：
#   - 純 config 路徑回歸（v0.8.1 baseline）
#   - params + param_keys 動態化：evaluation_interval / restore_delay /
#     auto_restore_on_deactivate
#   - 混合 fallback
#   - params.set() 即時反映（execution_config 下次讀到新值）
#   - enabled_key falsy → 回 context.last_command（保守策略）
#   - ctor 驗證

from __future__ import annotations

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.strategies.load_shedding import (
    LoadSheddingConfig,
    LoadSheddingStrategy,
    ShedStage,
    ThresholdCondition,
)
from csp_lib.core.runtime_params import RuntimeParameters


class _Circuit:
    def __init__(self, name: str) -> None:
        self._name = name
        self._is_shed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_shed(self) -> bool:
        return self._is_shed

    async def shed(self) -> None:
        self._is_shed = True

    async def restore(self) -> None:
        self._is_shed = False


def _ctx(
    last_p: float = 500.0, last_q: float = 100.0, params: RuntimeParameters | None = None, **extra: object
) -> StrategyContext:
    return StrategyContext(
        last_command=Command(p_target=last_p, q_target=last_q),
        extra=extra,
        params=params,
    )


def _make_stage(name: str = "s1") -> ShedStage:
    return ShedStage(
        name=name,
        circuits=[_Circuit(f"{name}_c")],
        condition=ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0),
    )


# =============== 1. 回歸：純 config 路徑 ===============


class TestLoadSheddingConfigOnlyRegression:
    def test_pure_config_execution_interval(self):
        cfg = LoadSheddingConfig(stages=[_make_stage()], evaluation_interval=7.5, restore_delay=90.0)
        strat = LoadSheddingStrategy(cfg)
        ec = strat.execution_config
        assert ec.interval_seconds == pytest.approx(7.5)


# =============== 2. 動態化：全欄位 ===============


class TestLoadSheddingDynamicParams:
    def test_full_dynamic_overrides_config(self):
        """params 動態覆蓋 evaluation_interval / restore_delay / auto_restore。"""
        cfg = LoadSheddingConfig(
            stages=[_make_stage()],
            evaluation_interval=5.0,
            restore_delay=60.0,
            auto_restore_on_deactivate=True,
        )
        params = RuntimeParameters(
            ls_interval=2.0,
            ls_restore_delay=120.0,
            ls_auto_restore=False,
        )
        strat = LoadSheddingStrategy(
            cfg,
            params=params,
            param_keys={
                "evaluation_interval": "ls_interval",
                "restore_delay": "ls_restore_delay",
                "auto_restore_on_deactivate": "ls_auto_restore",
            },
        )
        assert strat.execution_config.interval_seconds == pytest.approx(2.0)
        # restore_delay 會在 execute() 內部被讀取，間接驗證
        # （此處直接 resolve 以快速檢查）
        assert float(strat._resolver.resolve("restore_delay")) == pytest.approx(120.0)  # noqa: SLF001
        assert bool(strat._resolver.resolve("auto_restore_on_deactivate")) is False  # noqa: SLF001

    def test_mixed_mapping_fallback(self):
        """只動態化 evaluation_interval；其餘 fallback。"""
        cfg = LoadSheddingConfig(stages=[_make_stage()], evaluation_interval=5.0, restore_delay=60.0)
        params = RuntimeParameters(ls_interval=1.5)
        strat = LoadSheddingStrategy(cfg, params=params, param_keys={"evaluation_interval": "ls_interval"})

        assert strat.execution_config.interval_seconds == pytest.approx(1.5)
        # restore_delay 未動態化 → fallback cfg
        assert float(strat._resolver.resolve("restore_delay")) == pytest.approx(60.0)  # noqa: SLF001

    def test_params_set_reflects_next_execution_config(self):
        cfg = LoadSheddingConfig(stages=[_make_stage()], evaluation_interval=5.0)
        params = RuntimeParameters(ls_interval=5.0)
        strat = LoadSheddingStrategy(cfg, params=params, param_keys={"evaluation_interval": "ls_interval"})
        first = strat.execution_config.interval_seconds
        params.set("ls_interval", 1.0)
        second = strat.execution_config.interval_seconds
        assert first == pytest.approx(5.0)
        assert second == pytest.approx(1.0)


# =============== 3. enabled_key 保守策略 ===============


class TestLoadSheddingEnabledKey:
    def test_enabled_zero_returns_last_command(self):
        """enabled_key falsy → 保守回 context.last_command（不強制 shed/restore）。"""
        cfg = LoadSheddingConfig(stages=[_make_stage()])
        params = RuntimeParameters(ls_on=0)
        strat = LoadSheddingStrategy(
            cfg,
            params=params,
            param_keys={"evaluation_interval": "ls_interval"},
            enabled_key="ls_on",
        )
        # 建立一個原本會觸發 shed 的上下文（soc=10 < 20）
        ctx = _ctx(last_p=123.0, last_q=45.0, params=params, soc=10.0)
        cmd = strat.execute(ctx)
        # enabled=0 → 應回 last_command 原封不動
        assert cmd.p_target == pytest.approx(123.0)
        assert cmd.q_target == pytest.approx(45.0)
        # 狀態不應進入 shed（因為 enabled=false 直接 return）
        assert strat.shed_stage_names == []


# =============== 4. ctor 驗證 ===============


class TestLoadSheddingCtorErrors:
    def test_param_keys_without_params_raises(self):
        with pytest.raises(ValueError, match="params and param_keys"):
            LoadSheddingStrategy(
                LoadSheddingConfig(stages=[_make_stage()]),
                params=None,
                param_keys={"evaluation_interval": "ls_interval"},
            )
