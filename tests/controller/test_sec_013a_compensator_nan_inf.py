"""SEC-013a L4 防禦：PowerCompensator 在 measurement 非有限時整體 bypass

設計決策：measurement 為 NaN/Inf 時，補償器整體 bypass compensate —
- 不更新 _integral（避免 NaN 污染積分狀態永久黏住）
- 不更新 _last_output
- 不更新 FF table
- 回傳原始 command（等同 self._enabled=False 的行為）

修復前：measurement=NaN 進入 compensate → error=setpoint-NaN=NaN →
_filtered_error 變 NaN → _integral += NaN → 之後永遠黏住 NaN。

本檔案的每個測試在未修 source 前皆應 FAIL。
"""

from __future__ import annotations

import math

import pytest

from csp_lib.controller.compensator import PowerCompensator, PowerCompensatorConfig
from csp_lib.controller.core import Command, StrategyContext


def _make_compensator(**overrides) -> PowerCompensator:
    """建立測試用 PowerCompensator（對齊 test_compensator.py 的預設）"""
    defaults = {
        "rated_power": 2000.0,
        "output_min": -2000.0,
        "output_max": 2000.0,
        "ki": 0.3,
        "deadband": 0.5,
        "hold_cycles": 0,
        "error_ema_alpha": 0.0,
        "rate_limit": 0.0,
        "persist_path": "",
    }
    defaults.update(overrides)
    return PowerCompensator(PowerCompensatorConfig(**defaults))


class TestCompensatorProcessNaNInfBypass:
    """PowerCompensator.process() 在 measurement 非有限時整體 bypass（SEC-013a L4）"""

    # ─── NaN measurement ───

    async def test_process_nan_measurement_does_not_poison_filtered_error(self):
        """
        SEC-013a L4: measurement=NaN（EMA 啟用路徑）不應污染 _filtered_error。

        修復前：error_ema_alpha > 0 時，_filtered_error = alpha*NaN + (1-alpha)*prev = NaN，
               後續所有 cycle 的 filtered_error 都變 NaN，deadband 檢查永遠 False，
               integral 永遠不再更新 → 補償器永久失效。
        修復後：偵測到非有限 measurement → 整體 bypass（不進入 EMA 計算），
               _filtered_error 維持前一個有效值。
        """
        comp = _make_compensator(error_ema_alpha=0.1)
        # 先 warm up，讓 _filtered_error 累積有效值
        comp.compensate(setpoint=100.0, measurement=95.0, dt=0.3)
        filtered_before = comp._filtered_error
        assert math.isfinite(filtered_before)

        # 餵 NaN
        ctx = StrategyContext(extra={"meter_power": float("nan"), "dt": 0.3})
        await comp.process(Command(p_target=100.0), ctx)

        filtered_after = comp._filtered_error
        # 關鍵驗證：_filtered_error 必須維持有限數
        assert math.isfinite(filtered_after), f"NaN measurement 不應污染 _filtered_error，實際 {filtered_after!r}"
        # 精確驗證：bypass 後值應維持 warm-up 結束時的值
        assert filtered_after == pytest.approx(filtered_before), (
            f"NaN measurement 應 bypass 不更新 _filtered_error，before={filtered_before!r}, after={filtered_after!r}"
        )

    async def test_process_nan_measurement_returns_original_command(self):
        """
        SEC-013a L4: measurement=NaN → process() 應回傳原始 command（bypass 整體補償）。

        修復前：compensate() 仍然執行，某些路徑下（如 error_ema_alpha=0 + deadband>0）
               因為 NaN 比較永遠 False 而 silently bypass，但仍會呼叫 with_p(...)
               取代原始 p_target（數值可能碰巧相等）。
        修復後：明確 bypass → 回傳原始 command 物件（或至少邏輯上等同）。
        """
        comp = _make_compensator()
        original = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext(extra={"meter_power": float("nan"), "dt": 0.3})

        result = await comp.process(original, ctx)

        # 主要驗證：q_target 應保留（若走補償路徑會被 with_p 只取代 p_target；
        # 我們要求整體 bypass → 回傳原 command，q_target 自然保留）
        assert result.q_target == pytest.approx(50.0)
        # p_target 必須是有限數
        assert math.isfinite(result.p_target), f"p_target 不應為非有限值，得到 {result.p_target!r}"
        # p_target 應等同原值（整體 bypass 的最直接驗證）
        assert result.p_target == pytest.approx(100.0), (
            f"measurement=NaN 時應 bypass，p_target 應維持原值 100.0，實際得到 {result.p_target!r}"
        )

    async def test_process_nan_measurement_does_not_update_last_output(self):
        """
        SEC-013a L4: measurement=NaN 時不應更新 _last_output。

        修復前：走 compensate() 後 _last_output 被設為當次計算結果（即使 NaN 比較讓
               output 碰巧等於 ff_output，仍是「被更新」）。
        修復後：整體 bypass → _last_output 維持前次值。

        觀察差異：先讓 last_output 達到某值 X，再餵 NaN，_last_output 仍為 X。
        """
        comp = _make_compensator()
        # 先建立 _last_output = 某個非零值
        comp.compensate(setpoint=150.0, measurement=140.0, dt=1.0)
        last_output_before = comp.diagnostics["last_output"]
        assert last_output_before != 0.0

        # 餵 NaN，但 setpoint 變到 100 — 若走補償路徑，_last_output 會更新為 ~100
        ctx = StrategyContext(extra={"meter_power": float("nan"), "dt": 0.3})
        await comp.process(Command(p_target=100.0), ctx)

        last_output_after = comp.diagnostics["last_output"]
        assert math.isfinite(last_output_after)
        # 修復後 bypass → _last_output 不變
        assert last_output_after == pytest.approx(last_output_before), (
            f"NaN measurement 應 bypass 不更新 _last_output，before={last_output_before}, after={last_output_after}"
        )

    # ─── +Inf measurement ───

    async def test_process_positive_inf_measurement_returns_original(self):
        """SEC-013a L4: measurement=+Inf → bypass，回傳原始 command。"""
        comp = _make_compensator()
        original = Command(p_target=100.0)
        ctx = StrategyContext(extra={"meter_power": float("inf"), "dt": 0.3})

        result = await comp.process(original, ctx)

        assert math.isfinite(result.p_target), f"p_target 不應為非有限值，得到 {result.p_target!r}"
        assert result.p_target == pytest.approx(100.0)

    # ─── -Inf measurement ───

    async def test_process_negative_inf_measurement_returns_original(self):
        """SEC-013a L4: measurement=-Inf → bypass，回傳原始 command。"""
        comp = _make_compensator()
        original = Command(p_target=100.0)
        ctx = StrategyContext(extra={"meter_power": float("-inf"), "dt": 0.3})

        result = await comp.process(original, ctx)

        assert math.isfinite(result.p_target)
        assert result.p_target == pytest.approx(100.0)

    # ─── 正常 measurement 不受影響（regression guard）───

    async def test_process_finite_measurement_still_compensates(self):
        """SEC-013a L4: 正常 measurement 應正常進行補償（regression guard）。"""
        comp = _make_compensator(ki=0.0)  # 關掉 integral 簡化驗證
        ctx = StrategyContext(extra={"meter_power": 90.0, "dt": 0.3})

        # 正常路徑：setpoint=100, ff=1.0 → output = 100.0
        result = await comp.process(Command(p_target=100.0), ctx)

        assert result.p_target == pytest.approx(100.0)
