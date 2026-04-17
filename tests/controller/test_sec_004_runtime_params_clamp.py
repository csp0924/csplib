"""SEC-004: RuntimeParameters 值域 clamp（dynamic_protection）

設計決策：EMS / Modbus 寫入 RuntimeParameters 的值若超出物理合理範圍
（SOC 百分比應在 [0,100]、grid_limit_pct 應在 [0,100]），
應在保護規則內自動 clamp，避免：
- soc_max=150 讓 SOC 保護永遠不觸發上限（系統可能過充）
- grid_limit_pct=250 讓 max_p 超過額定（保護失效）

修復範圍：
- DynamicSOCProtection._resolve_limits()：soc_max / soc_min clamp 到 [0, 100]
- GridLimitProtection.evaluate()：grid_limit_pct clamp 到 [0, 100]

本檔案的每個測試在未修 source 前皆應 FAIL。
"""

from __future__ import annotations

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.system.dynamic_protection import (
    DynamicSOCProtection,
    GridLimitProtection,
)
from csp_lib.core.runtime_params import RuntimeParameters

# ===========================================================================
# DynamicSOCProtection — soc_max / soc_min 值域 clamp
# ===========================================================================


class TestDynamicSOCProtectionClamp:
    """DynamicSOCProtection 對 soc_max / soc_min 的值域 clamp（SEC-004）"""

    # ─── soc_max 上越界 ───

    def test_soc_max_over_100_clamped_to_100(self):
        """
        SEC-004: soc_max=150 應被 clamp 到 100。

        修復前：soc_max=150 → SOC=98 不會觸發保護（98 < 150），可能造成過充。
        修復後：clamp 到 100 → SOC=98 屬正常範圍，soc_max 有效值=100。

        驗證方式：SOC=100 剛好等於 clamp 後的 soc_max，應觸發禁充。
        """
        params = RuntimeParameters(soc_max=150.0, soc_min=5.0)
        rule = DynamicSOCProtection(params)
        cmd = Command(p_target=-100.0)  # charging
        ctx = StrategyContext(soc=100.0)  # SOC 滿電

        result = rule.evaluate(cmd, ctx)

        # 修復後 soc_max 應 clamp 到 100 → SOC=100 >= 100 → 禁止充電
        assert result.p_target == pytest.approx(0.0), (
            f"soc_max=150 應 clamp 到 100，SOC=100 應觸發禁充，實際 p_target={result.p_target!r}"
        )
        assert rule.is_triggered is True

    # ─── soc_max 下越界（負值）───

    def test_soc_max_negative_clamped_to_zero_then_raises_on_inversion(self):
        """
        SEC-004 + BUG-003 組合：soc_max=-10 clamp 到 0，soc_min=5 仍大於 clamp 後 soc_max。
        BUG-003 不再自動 swap，應拋 ValueError 讓配置錯誤明確可見。
        """
        params = RuntimeParameters(soc_max=-10.0, soc_min=5.0)
        rule = DynamicSOCProtection(params)
        cmd = Command(p_target=100.0)  # discharging
        ctx = StrategyContext(soc=0.0)

        # clamp 後 soc_max=0 < soc_min=5 → BUG-003 raise
        with pytest.raises(ValueError, match="soc_max .* < soc_min"):
            rule.evaluate(cmd, ctx)

    # ─── soc_min 下越界（負值）───

    def test_soc_min_negative_clamped_to_zero(self):
        """
        SEC-004: soc_min=-10 應被 clamp 到 0。

        修復前：SOC=1 > soc_min=-10，不觸發禁放。
        修復後：soc_min clamp 到 0 → SOC=0 剛好等於 soc_min → SOC=0 時禁放。

        驗證：SOC=0 應在 clamp 後觸發禁放。
        """
        params = RuntimeParameters(soc_max=95.0, soc_min=-10.0)
        rule = DynamicSOCProtection(params)
        cmd = Command(p_target=100.0)  # discharging
        ctx = StrategyContext(soc=0.0)

        result = rule.evaluate(cmd, ctx)

        # 修復後 soc_min clamp 到 0 → SOC=0 <= 0 → 禁放
        assert result.p_target == pytest.approx(0.0), (
            f"soc_min=-10 應 clamp 到 0，SOC=0 應觸發禁放，實際 {result.p_target!r}"
        )
        assert rule.is_triggered is True

    # ─── soc_min 上越界 ───

    def test_soc_min_over_100_clamped_to_100_then_raises_on_inversion(self):
        """
        SEC-004 + BUG-003 組合：soc_min=150 clamp 到 100，但仍大於 soc_max=95。
        BUG-003 不再自動 swap，應拋 ValueError。
        """
        params = RuntimeParameters(soc_max=95.0, soc_min=150.0)
        rule = DynamicSOCProtection(params)
        cmd = Command(p_target=100.0)
        ctx = StrategyContext(soc=90.0)

        # clamp 後 soc_max=95 < soc_min=100 → BUG-003 raise
        with pytest.raises(ValueError, match="soc_max .* < soc_min"):
            rule.evaluate(cmd, ctx)

    # ─── regression guard: 正常值不受影響 ───

    def test_normal_soc_limits_unchanged(self):
        """SEC-004 regression guard: 正常範圍的 soc_max / soc_min 不被 clamp 改動。"""
        params = RuntimeParameters(soc_max=90.0, soc_min=10.0)
        rule = DynamicSOCProtection(params)
        cmd = Command(p_target=100.0)
        ctx = StrategyContext(soc=50.0)  # 正常 SOC

        result = rule.evaluate(cmd, ctx)

        assert result.p_target == pytest.approx(100.0)
        assert rule.is_triggered is False


# ===========================================================================
# GridLimitProtection — grid_limit_pct 值域 clamp
# ===========================================================================


class TestGridLimitProtectionClamp:
    """GridLimitProtection 對 grid_limit_pct 的值域 clamp（SEC-004）"""

    # ─── 上越界 ───

    def test_grid_limit_over_100_clamped_to_100(self):
        """
        SEC-004: grid_limit_pct=250 應被 clamp 到 100（物理上不可能超過額定 100%）。

        修復前：max_p = 1000 * 250 / 100 = 2500 → 允許輸出 2500kW（超過額定 1000kW 2.5 倍）
        修復後：pct clamp 到 100 → max_p = 1000 → p=1500 被 clamp 到 1000。

        驗證：設 p=1500 放電，clamp 後應限制到 1000。
        """
        params = RuntimeParameters(grid_limit_pct=250)
        rule = GridLimitProtection(params, total_rated_kw=1000.0)
        cmd = Command(p_target=1500.0)
        ctx = StrategyContext()

        result = rule.evaluate(cmd, ctx)

        # 修復後：pct clamp 到 100 → max_p=1000 → p=1500 > 1000 → clamp 到 1000
        assert result.p_target == pytest.approx(1000.0), (
            f"grid_limit_pct=250 應 clamp 到 100，p=1500 應被限制為 1000，實際 {result.p_target!r}"
        )
        assert rule.is_triggered is True

    # ─── 下越界（負值）───

    def test_grid_limit_negative_clamped_to_zero(self):
        """
        SEC-004: grid_limit_pct=-50 應被 clamp 到 0（物理上不可能為負）。

        修復前：max_p = 1000 * (-50) / 100 = -500 → p > -500 時觸發限制 → p=100 被 clamp 到 -500（錯誤：放電變充電）。
        修復後：pct clamp 到 0 → max_p=0 → 任何 P 都被限制為 0。
        """
        params = RuntimeParameters(grid_limit_pct=-50)
        rule = GridLimitProtection(params, total_rated_kw=1000.0)
        cmd = Command(p_target=100.0)
        ctx = StrategyContext()

        result = rule.evaluate(cmd, ctx)

        # 修復後：pct clamp 到 0 → max_p=0 → p=100 > 0 → clamp 到 0
        assert result.p_target == pytest.approx(0.0), (
            f"grid_limit_pct=-50 應 clamp 到 0，max_p=0，p=100 應被限制為 0，實際 {result.p_target!r}"
        )
        assert rule.is_triggered is True

    # ─── 邊界：剛好 100 與剛好 0 ───

    def test_grid_limit_exactly_100_no_clamp_needed(self):
        """SEC-004 regression guard: grid_limit_pct=100 屬邊界合法值，不被改動。"""
        params = RuntimeParameters(grid_limit_pct=100)
        rule = GridLimitProtection(params, total_rated_kw=1000.0)
        cmd = Command(p_target=999.0)
        ctx = StrategyContext()

        result = rule.evaluate(cmd, ctx)

        assert result.p_target == pytest.approx(999.0)
        assert rule.is_triggered is False

    def test_grid_limit_exactly_0_no_clamp_needed(self):
        """SEC-004 regression guard: grid_limit_pct=0 屬邊界合法值。"""
        params = RuntimeParameters(grid_limit_pct=0)
        rule = GridLimitProtection(params, total_rated_kw=1000.0)
        cmd = Command(p_target=100.0)
        ctx = StrategyContext()

        result = rule.evaluate(cmd, ctx)

        assert result.p_target == pytest.approx(0.0)
        assert rule.is_triggered is True
