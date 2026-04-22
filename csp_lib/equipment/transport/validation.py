# =============== Equipment Transport - Validation ===============
#
# Write validation protocol & built-in rules
#
# 定義寫入前驗證的 Layer 3 合約：
#   - ValidationResult: 驗證結果 (frozen dataclass)
#   - WriteValidationRule: @runtime_checkable Protocol
#   - RangeRule: 最小/最大值範圍驗證（含 NaN/Inf guard）

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from csp_lib.core._numeric import is_non_finite_float


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Write 驗證結果。

    Attributes:
        accepted: True 通過、False 拒絕
        effective_value: 實際要寫入的值；clamp 情境下為修正後值，reject 時保留原值供稽核
        reason: 拒絕原因；``accepted=True`` 時為空字串

    Invariant:
        ``accepted=False`` 時 ``reason`` 不得為空字串（__post_init__ 守門），
        避免無語意 reject 汙染 log。
    """

    accepted: bool
    effective_value: Any
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.accepted and not self.reason:
            raise ValueError("ValidationResult rejected must provide a non-empty reason")

    @classmethod
    def accept(cls, value: Any) -> ValidationResult:
        """Shortcut：驗證通過，effective_value 帶回原值或 clamp 後新值。"""
        return cls(accepted=True, effective_value=value, reason="")

    @classmethod
    def reject(cls, value: Any, reason: str) -> ValidationResult:
        """Shortcut：驗證拒絕，reason 必填非空。"""
        return cls(accepted=False, effective_value=value, reason=reason)


@runtime_checkable
class WriteValidationRule(Protocol):
    """寫入前驗證規則 Protocol（sync，Layer 3）。

    由 ``WriteCommandManager`` 在 ``device.write()`` 之前逐條呼叫。
    每條 rule 檢查 ``(point_name, value)``，回傳 ``ValidationResult``：

    - ``accepted=True`` → 使用 ``effective_value`` 繼續執行（可能是 clamp 後的值）
    - ``accepted=False`` → 中止寫入，記錄 ``reason`` 至 CommandRecord

    **Structural compatibility**：
        ``modbus_gateway.WriteRule`` 透過 ``apply_v2`` 結構相容本 Protocol，
        允許直接作為 ``WriteCommandManager(validation_rules=...)`` 成員。

    Example:
        ```python
        class AlwaysAccept:
            def apply(self, point_name: str, value: Any) -> ValidationResult:
                return ValidationResult.accept(value)
        ```
    """

    def apply(self, point_name: str, value: Any) -> ValidationResult:
        """驗證一次寫入。

        Args:
            point_name: 目標點位名稱
            value: 擬寫入值（原始，未經 pipeline transform）

        Returns:
            ValidationResult — ``accepted`` 決定通行、``effective_value`` 為實寫值
        """
        ...


@dataclass(frozen=True, slots=True)
class RangeRule:
    """最小/最大值範圍驗證規則。

    實作 :class:`WriteValidationRule` Protocol。語意與
    ``modbus_gateway.WriteRule`` 對齊但不綁 ``register_name``（caller 在
    ``Mapping[str, WriteValidationRule]`` 層指名）。

    Attributes:
        min_value: 最小值；None = 無下界
        max_value: 最大值；None = 無上界
        clamp: True → 超界自動夾到邊界 (accepted=True)；False → reject

    NaN/Inf 處理：
        ``value`` 若為 float 且 NaN 或 ±Inf，一律 reject（即使 clamp=True）。
        NaN 與 <、> 比較皆回 False，會 silent accept，因此顯式攔截。
        對照 bug-lesson ``numerical-safety-layered``。

    Example:
        ```python
        rule = RangeRule(min_value=0.0, max_value=100.0, clamp=True)
        rules = {"active_power": rule}
        manager = WriteCommandManager(repo, validation_rules=rules)
        ```
    """

    min_value: float | None = None
    max_value: float | None = None
    clamp: bool = False

    def __post_init__(self) -> None:
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError(f"RangeRule.min_value must be <= max_value, got min={self.min_value} max={self.max_value}")

    def apply(self, point_name: str, value: Any) -> ValidationResult:
        # NaN 穿過 <、> 比較皆回 False 會 silent accept，必須先擋
        if is_non_finite_float(value):
            return ValidationResult.reject(value, f"value is not finite ({value!r})")

        if self.min_value is not None and value < self.min_value:
            if self.clamp:
                return ValidationResult.accept(self.min_value)
            return ValidationResult.reject(value, f"value {value} below min {self.min_value}")

        if self.max_value is not None and value > self.max_value:
            if self.clamp:
                return ValidationResult.accept(self.max_value)
            return ValidationResult.reject(value, f"value {value} above max {self.max_value}")

        return ValidationResult.accept(value)


__all__ = [
    "RangeRule",
    "ValidationResult",
    "WriteValidationRule",
]
