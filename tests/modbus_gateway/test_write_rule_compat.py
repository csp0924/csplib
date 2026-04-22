# =============== Tests: WriteRule.apply_v2 + Protocol compat ===============
#
# 驗證 modbus_gateway.WriteRule 透過 apply_v2 結構相容
# equipment.transport.WriteValidationRule Protocol，
# 可直接塞進 WriteCommandManager(validation_rules=...)。
#
# 注意：此測試放在 tests/modbus_gateway/ 是刻意的 —
# tests/manager/ 不得 import modbus_gateway（Layer 5 → Layer 8 違規）。

from __future__ import annotations

import math

from csp_lib.equipment.transport import ValidationResult, WriteValidationRule
from csp_lib.modbus_gateway.config import WriteRule, WriteRuleAdapter


class TestLegacyApplyUntouched:
    """apply() tuple 介面必須完全不動（v1.0 前 WritePipeline 仍依賴）。"""

    def test_apply_returns_tuple(self) -> None:
        rule = WriteRule(register_name="sp", min_value=0, max_value=100, clamp=False)
        value, rejected = rule.apply("sp", 50)
        assert (value, rejected) == (50, False)

    def test_apply_rejects_out_of_range(self) -> None:
        rule = WriteRule(register_name="sp", min_value=0, max_value=100, clamp=False)
        value, rejected = rule.apply("sp", 150)
        assert rejected is True

    def test_apply_clamps(self) -> None:
        rule = WriteRule(register_name="sp", min_value=0, max_value=100, clamp=True)
        value, rejected = rule.apply("sp", 150)
        assert (value, rejected) == (100, False)


class TestApplyV2Protocol:
    """apply_v2() 回傳 ValidationResult，用 adapter 可滿足 WriteValidationRule Protocol。"""

    def test_runtime_checkable_only_checks_method_names(self) -> None:
        """提醒：@runtime_checkable Protocol 只檢查 method **是否存在**，
        不驗證簽名或回傳型別。

        WriteRule 恰好有 ``apply(name, value)`` method，所以 ``isinstance`` 會回 True，
        **但呼叫 apply 會拿到 tuple 不是 ValidationResult** — 直接當作
        WriteValidationRule 傳給 WriteCommandManager 會在 runtime 爆。

        正確做法：使用 ``apply_v2`` 或下面的 ``WriteRuleAdapter``。
        """
        rule = WriteRule(register_name="sp", min_value=0, max_value=100)
        assert isinstance(rule, WriteValidationRule)  # 結構符合 — 但語意錯！
        value, rejected = rule.apply("sp", 50)  # 回 tuple，不是 ValidationResult
        assert (value, rejected) == (50, False)

    def test_apply_v2_accepts(self) -> None:
        rule = WriteRule(register_name="sp", min_value=0, max_value=100)
        r = rule.apply_v2("sp", 50)
        assert isinstance(r, ValidationResult)
        assert r.accepted is True
        assert r.effective_value == 50

    def test_apply_v2_rejects(self) -> None:
        rule = WriteRule(register_name="sp", min_value=0, max_value=100, clamp=False)
        r = rule.apply_v2("sp", 150)
        assert r.accepted is False
        assert "above max" in r.reason

    def test_apply_v2_clamps(self) -> None:
        rule = WriteRule(register_name="sp", min_value=0, max_value=100, clamp=True)
        r = rule.apply_v2("sp", 150)
        assert r.accepted is True
        assert r.effective_value == 100

    def test_apply_v2_rejects_nan(self) -> None:
        """bug-lesson numerical-safety-layered：NaN 必須 reject。"""
        rule = WriteRule(register_name="sp", min_value=0, max_value=100, clamp=True)
        r = rule.apply_v2("sp", float("nan"))
        assert r.accepted is False
        assert "not finite" in r.reason

    def test_apply_v2_rejects_inf(self) -> None:
        rule = WriteRule(register_name="sp", min_value=0, max_value=100, clamp=True)
        assert rule.apply_v2("sp", math.inf).accepted is False
        assert rule.apply_v2("sp", -math.inf).accepted is False


class TestWriteRuleAdapter:
    """官方 adapter：把 WriteRule 包成符合 Protocol 的 rule，
    用於 WriteCommandManager(validation_rules=...)。"""

    def test_adapter_satisfies_protocol(self) -> None:
        wr = WriteRule(register_name="sp", min_value=0, max_value=100)
        adapter = WriteRuleAdapter(wr)
        assert isinstance(adapter, WriteValidationRule)

    def test_adapter_accept(self) -> None:
        adapter = WriteRuleAdapter(WriteRule(register_name="sp", min_value=0, max_value=100))
        r = adapter.apply("sp", 50)
        assert isinstance(r, ValidationResult)
        assert r.accepted is True
        assert r.effective_value == 50

    def test_adapter_reject(self) -> None:
        adapter = WriteRuleAdapter(WriteRule(register_name="sp", min_value=0, max_value=100, clamp=False))
        r = adapter.apply("sp", 150)
        assert r.accepted is False

    def test_adapter_clamp(self) -> None:
        adapter = WriteRuleAdapter(WriteRule(register_name="sp", min_value=0, max_value=100, clamp=True))
        r = adapter.apply("sp", 150)
        assert r.accepted is True
        assert r.effective_value == 100
