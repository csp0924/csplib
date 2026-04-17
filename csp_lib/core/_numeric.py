# =============== Core - Numeric Helpers (Internal) ===============
#
# 數值安全小工具（不對外 export）
#
# 用途：給各層防禦性檢查使用，集中 NaN/Inf 的偵測與 clamp 行為，
#       避免散落於多檔的 `math.isfinite` 呼叫行為不一致。
#
# 設計注意：
#   - 不對外匯出（不進 csp_lib.core.__init__）
#   - 不接受 bool（isinstance(True, int) 的歧義）
#   - int 不會被視為「非有限」（int 永遠是有限值）

from __future__ import annotations

import math

__all__ = [
    "clamp",
    "is_non_finite_float",
    "safe_float",
]


def is_non_finite_float(value: object) -> bool:
    """檢查值是否為非有限的 float（NaN / +Inf / -Inf）。

    int 與 bool 永遠回傳 False，避免 ``isinstance(True, int)`` 造成歧義。

    Args:
        value: 待檢查的值（可能為任意型別）。

    Returns:
        True 當值為 ``float`` 且非有限時；否則 False。
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, float) and not math.isfinite(value)


def safe_float(value: object, default: float | None = None) -> float | None:
    """將值轉為有限 float，非有限或非數字一律回傳 ``default``。

    - ``bool`` 視為非法（回傳 default），避免 True/False 被當成 1/0
    - ``int`` → 轉成 float
    - ``float`` 非有限 → default

    Args:
        value: 待轉換的值。
        default: 非法值時的回傳值（預設 ``None``）。

    Returns:
        有效的有限 float，或 ``default``。
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        f = float(value)
        if math.isfinite(f):
            return f
    return default


def clamp(x: float, lo: float, hi: float) -> float:
    """將 ``x`` 限制在 ``[lo, hi]`` 區間內。

    Args:
        x: 待限制的值。
        lo: 下限。
        hi: 上限。

    Returns:
        ``max(lo, min(hi, x))``。
    """
    return max(lo, min(hi, x))
