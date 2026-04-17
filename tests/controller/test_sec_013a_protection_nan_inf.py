"""SEC-013a L4 防禦：Protection rules 對 NaN/Inf 採 fail-safe（視同 None）

設計決策：保護規則在讀取 context.soc / meter_power / grid_limit 等 float
欄位時，若值為 NaN/Inf，行為等同 None：
- 不強制觸發保護（避免 NaN 閃爍造成掉電瞬間 P=0 閃爍）
- 沿用上次 is_triggered 值
- 直接 passthrough command（不介入）

為何不強制觸發保護：NaN 只出現在設備通訊瞬態（如 Float32 讀到 0x7FFFFFFF），
單 cycle 觸發 P=0 會造成功率閃爍；保守做法是視同資料不可用（None），
由上層 timeout / disconnect 檢測接手。

修復前：`soc >= soc_max` 比較中 soc=NaN 永遠回傳 False → 保護被無聲繞過
→ 可能在 SOC 實為異常時仍允許充放電。

本檔案的每個測試在未修 source 前皆應 FAIL。
"""

from __future__ import annotations

import math

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.system.dynamic_protection import (
    DynamicSOCProtection,
    GridLimitProtection,
)
from csp_lib.controller.system.protection import (
    ReversePowerProtection,
    SOCProtection,
    SOCProtectionConfig,
)
from csp_lib.core.runtime_params import RuntimeParameters

# ===========================================================================
# DynamicSOCProtection — context.soc = NaN / Inf
# ===========================================================================


class TestDynamicSOCProtectionNaNInf:
    """DynamicSOCProtection 對 ctx.soc = NaN/Inf 的 fail-safe 行為（SEC-013a L4）"""

    def test_soc_nan_preserves_last_is_triggered_true(self):
        """
        SEC-013a L4: ctx.soc = NaN → 沿用上次 is_triggered 值（此處為 True）。

        修復前：NaN 與 soc_max/soc_min 比較皆為 False，所有分支都不進入，
               最後 fallthrough 到 `self._is_triggered = False; return command`
               → is_triggered 被無聲重置為 False，即使上次還在觸發中。
        修復後：偵測非有限 → 視同 None → 提前 return，**保留上次 is_triggered**。

        實務影響：SOC 保護剛觸發時設備回傳一個 NaN（通訊瞬態）→ is_triggered
        被重置為 False → 上層判斷「保護解除」→ 重新允許充放電 → 實際 SOC
        若仍異常會造成過充/過放。
        """
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = DynamicSOCProtection(params)

        # Step 1: 先用正常 SOC=98 觸發保護
        ctx_triggered = StrategyContext(soc=98.0)
        rule.evaluate(Command(p_target=-100.0), ctx_triggered)
        assert rule.is_triggered is True, "前置條件：應成功觸發 SOC 上限保護"

        # Step 2: 下一個 cycle 收到 NaN
        ctx_nan = StrategyContext()
        ctx_nan.soc = float("nan")
        rule.evaluate(Command(p_target=-100.0), ctx_nan)

        # 修復前：is_triggered 被重置為 False（錯誤）
        # 修復後：沿用上次的 True
        assert rule.is_triggered is True, "SOC=NaN 應視同 None → 沿用上次 is_triggered=True，而非無聲重置為 False"

    def test_soc_nan_passthrough_command(self):
        """
        SEC-013a L4: ctx.soc = NaN → 不介入（passthrough）。

        修復前後行為都是 passthrough（NaN 比較 quirk 使然），但修復後語意明確：
        視同 None → 提前 return，不介入。此測試作為 regression guard。
        """
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = DynamicSOCProtection(params)
        cmd = Command(p_target=-100.0)
        ctx = StrategyContext()
        ctx.soc = float("nan")

        result = rule.evaluate(cmd, ctx)

        assert result.p_target == pytest.approx(-100.0)
        assert math.isfinite(result.p_target)

    def test_soc_positive_inf_treated_as_none(self):
        """
        SEC-013a L4: ctx.soc = +Inf → 視同 None。

        修復前：+Inf >= soc_max (95.0) 為 True → 被判為 SOC 過高，阻擋充電。
        修復後：非有限 → passthrough。
        """
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = DynamicSOCProtection(params)
        cmd = Command(p_target=-100.0)
        ctx = StrategyContext()
        ctx.soc = float("inf")

        result = rule.evaluate(cmd, ctx)

        # 修復前：+Inf >= 95 → 誤 clamp 為 0；修復後應 passthrough
        assert result.p_target == pytest.approx(-100.0), (
            f"SOC=+Inf 應視同 None 不介入，p_target 應維持 -100，實際 {result.p_target!r}"
        )
        assert rule.is_triggered is False

    def test_soc_negative_inf_treated_as_none(self):
        """
        SEC-013a L4: ctx.soc = -Inf → 視同 None。

        修復前：-Inf >= 95 為 False，但 -Inf <= 5 為 True → 誤判為 SOC 過低，阻擋放電。
        修復後：非有限 → passthrough。
        """
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        rule = DynamicSOCProtection(params)
        cmd = Command(p_target=100.0)  # discharging
        ctx = StrategyContext()
        ctx.soc = float("-inf")

        result = rule.evaluate(cmd, ctx)

        assert result.p_target == pytest.approx(100.0), (
            f"SOC=-Inf 應視同 None 不介入，p_target 應維持 100，實際 {result.p_target!r}"
        )
        assert rule.is_triggered is False


# ===========================================================================
# SOCProtection (legacy) — context.soc = NaN / Inf
# ===========================================================================


class TestSOCProtectionNaNInf:
    """SOCProtection (legacy) 對 ctx.soc = NaN/Inf 的 fail-safe 行為（SEC-013a L4）"""

    def test_soc_nan_preserves_last_is_triggered(self):
        """SEC-013a L4: SOCProtection 遇 soc=NaN 沿用上次 is_triggered。"""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            rule = SOCProtection(SOCProtectionConfig(soc_high=95.0, soc_low=5.0))

        # Step 1: 正常 SOC=98 觸發保護
        ctx_triggered = StrategyContext(soc=98.0)
        rule.evaluate(Command(p_target=-100.0), ctx_triggered)
        assert rule.is_triggered is True

        # Step 2: NaN SOC
        ctx_nan = StrategyContext()
        ctx_nan.soc = float("nan")
        rule.evaluate(Command(p_target=-100.0), ctx_nan)

        # 修復前：被重置為 False；修復後：維持 True
        assert rule.is_triggered is True, "SOC=NaN 應視同 None → 沿用上次 is_triggered"

    def test_soc_inf_passthrough(self):
        """SEC-013a L4: SOCProtection 遇 soc=+Inf 應視同 None 不介入。"""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            rule = SOCProtection(SOCProtectionConfig(soc_high=95.0, soc_low=5.0))

        cmd = Command(p_target=-100.0)
        ctx = StrategyContext()
        ctx.soc = float("inf")

        result = rule.evaluate(cmd, ctx)

        # 修復前：+Inf >= 95 → P clamp 為 0
        assert result.p_target == pytest.approx(-100.0), f"SOC=+Inf 應視同 None，實際 {result.p_target!r}"


# ===========================================================================
# ReversePowerProtection — meter_power = NaN / Inf
# ===========================================================================


class TestReversePowerProtectionNaNInf:
    """ReversePowerProtection 對 meter_power = NaN/Inf 的 fail-safe 行為（SEC-013a L4）"""

    def test_meter_power_nan_preserves_last_is_triggered(self):
        """
        SEC-013a L4: meter_power=NaN → 沿用上次 is_triggered（此處為 True）。

        修復前：max_discharge = NaN + threshold = NaN，`p > NaN` 永遠 False
               → fallthrough 到 `self._is_triggered = False` → 無聲重置。
        修復後：偵測非有限 → 視同 None → 保留上次值。

        實務影響：表後逆送保護剛觸發時，meter 回傳 NaN → is_triggered 被重置
        → 上層以為保護解除 → 允許持續放電 → 真正逆送。
        """
        rule = ReversePowerProtection(threshold=0.0)

        # Step 1: 先用正常 meter_power=50 + 超額放電觸發保護
        ctx_triggered = StrategyContext(extra={"meter_power": 50.0})
        rule.evaluate(Command(p_target=500.0), ctx_triggered)
        assert rule.is_triggered is True, "前置條件：應成功觸發逆送保護"

        # Step 2: 下一個 cycle 收到 NaN
        ctx_nan = StrategyContext(extra={"meter_power": float("nan")})
        result = rule.evaluate(Command(p_target=500.0), ctx_nan)

        # 修復前：is_triggered 被重置為 False（錯誤）；修復後：維持 True
        assert rule.is_triggered is True, "meter_power=NaN 應視同 None → 沿用上次 is_triggered=True，而非無聲重置"
        # 輸出必須是有限數
        assert math.isfinite(result.p_target)

    def test_meter_power_inf_does_not_produce_nan_output(self):
        """
        SEC-013a L4: meter_power=+Inf → 視同 None 不介入。

        修復前：max_discharge = Inf + 0 = Inf，`p > Inf` 為 False，passthrough。
               但若下游某個保護又基於此邏輯做運算，Inf 會滲透。
        修復後：明確視同 None，is_triggered=False。
        """
        rule = ReversePowerProtection(threshold=0.0)
        cmd = Command(p_target=500.0)
        ctx = StrategyContext(extra={"meter_power": float("inf")})

        result = rule.evaluate(cmd, ctx)

        assert math.isfinite(result.p_target)
        assert rule.is_triggered is False


# ===========================================================================
# GridLimitProtection — grid_limit_pct = NaN / Inf
# ===========================================================================


class TestGridLimitProtectionNaNInf:
    """GridLimitProtection 對 grid_limit_pct = NaN/Inf 的 fail-safe 行為（SEC-013a L4）"""

    def test_grid_limit_nan_preserves_last_is_triggered(self):
        """
        SEC-013a L4: grid_limit_pct=NaN → 沿用上次 is_triggered（此處為 True）。

        修復前：max_p = 1000 * NaN / 100 = NaN，`p > NaN` 永遠 False
               → fallthrough 到 `self._is_triggered = False` → 無聲重置。
        修復後：偵測非有限 → 視同 None → 保留上次值。

        實務影響：電力公司下達限電指令（如 50%）觸發保護時，若 params 瞬間
        被寫入 NaN（EMS 通訊 glitch），is_triggered 會被無聲重置，
        上層以為限電解除 → 恢復超額輸出。
        """
        # Step 1: 先用正常 limit=50 + 超額指令觸發保護
        params = RuntimeParameters(grid_limit_pct=50)
        rule = GridLimitProtection(params, total_rated_kw=1000.0)
        ctx = StrategyContext()

        rule.evaluate(Command(p_target=800.0), ctx)
        assert rule.is_triggered is True, "前置條件：應成功觸發限電保護"

        # Step 2: grid_limit_pct 被改寫為 NaN
        params.set("grid_limit_pct", float("nan"))
        result = rule.evaluate(Command(p_target=800.0), ctx)

        # 輸出不可為 NaN
        assert math.isfinite(result.p_target), f"grid_limit_pct=NaN 時輸出不可為非有限值，實際 {result.p_target!r}"
        # 修復前：is_triggered 被重置為 False；修復後：維持 True
        assert rule.is_triggered is True, "grid_limit_pct=NaN 應視同 None → 沿用上次 is_triggered=True"

    def test_grid_limit_inf_does_not_produce_nan(self):
        """SEC-013a L4: grid_limit_pct=+Inf → 視同 None。"""
        params = RuntimeParameters(grid_limit_pct=float("inf"))
        rule = GridLimitProtection(params, total_rated_kw=1000.0)
        cmd = Command(p_target=500.0)
        ctx = StrategyContext()

        result = rule.evaluate(cmd, ctx)

        assert math.isfinite(result.p_target)
        assert result.p_target == pytest.approx(500.0)
