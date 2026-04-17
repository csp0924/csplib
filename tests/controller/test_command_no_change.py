# =============== Command NoChange Sentinel Tests (v0.8.0 WI-V080-004) ===============
#
# 覆蓋 ``NoChange`` sentinel 的所有契約：
#   - Singleton 語義
#   - Equality 與 identity 比較
#   - ``__bool__`` 故意拋 TypeError
#   - ``is_no_change`` TypeGuard
#   - Command 的 effective_p/q、with_p/with_q、fallback 不用 NO_CHANGE
#   - ``dataclasses.replace`` 與 ``__str__`` 整合

from __future__ import annotations

import dataclasses

import pytest

from csp_lib.controller.core import Command
from csp_lib.controller.core.command import NO_CHANGE, NoChange, is_no_change

# =============== Singleton ===============


class TestNoChangeSingleton:
    """NoChange 必須是 singleton，所有實例化都回傳同一物件"""

    def test_multiple_instantiations_return_same_instance(self):
        """NoChange() is NoChange() — 單例保證"""
        assert NoChange() is NoChange()

    def test_module_constant_is_singleton(self):
        """NO_CHANGE 模組常數與 NoChange() 必為同一實例"""
        assert NO_CHANGE is NoChange()

    def test_no_change_is_no_change(self):
        """NO_CHANGE is NO_CHANGE — 反身性"""
        assert NO_CHANGE is NO_CHANGE

    def test_no_change_eq_no_change(self):
        """NO_CHANGE == NO_CHANGE — Eq 對自身成立"""
        assert NO_CHANGE == NO_CHANGE  # noqa: PLR0124

    def test_eq_only_matches_self(self):
        """NO_CHANGE == 0.0 / None 必為 False"""
        assert (NO_CHANGE == 0.0) is False
        assert (NO_CHANGE == None) is False  # noqa: E711
        assert (NO_CHANGE == "NO_CHANGE") is False

    def test_hash_is_stable(self):
        """NO_CHANGE 可作為 dict key / set 成員"""
        s = {NO_CHANGE, NO_CHANGE}
        assert len(s) == 1
        d = {NO_CHANGE: "skip"}
        assert d[NO_CHANGE] == "skip"


# =============== __bool__ 禁止 ===============


class TestNoChangeBoolForbidden:
    """NoChange 不可用於布林脈絡 — 0.0 和 NO_CHANGE 語義差異巨大，必須顯式比對"""

    def test_bool_raises_type_error(self):
        """bool(NO_CHANGE) 必拋 TypeError"""
        with pytest.raises(TypeError, match="NoChange is not a boolean"):
            bool(NO_CHANGE)

    def test_if_statement_raises_type_error(self):
        """if NO_CHANGE: — 經 __bool__ 也會拋"""
        with pytest.raises(TypeError):
            if NO_CHANGE:  # pragma: no cover — 實際不會執行到 body
                pass

    def test_not_operator_raises_type_error(self):
        """not NO_CHANGE — 同樣會觸發 __bool__"""
        with pytest.raises(TypeError):
            _ = not NO_CHANGE


# =============== is_no_change TypeGuard ===============


class TestIsNoChange:
    """is_no_change() TypeGuard 函式"""

    def test_on_no_change_returns_true(self):
        assert is_no_change(NO_CHANGE) is True

    def test_on_float_zero_returns_false(self):
        """0.0 是合法 setpoint，不是 NO_CHANGE"""
        assert is_no_change(0.0) is False

    def test_on_float_nonzero_returns_false(self):
        assert is_no_change(100.0) is False
        assert is_no_change(-50.5) is False

    def test_on_fresh_no_change_instance_returns_true(self):
        """NoChange() 每次都回傳 singleton，is_no_change 應判為 True"""
        assert is_no_change(NoChange()) is True


# =============== Command.effective_p / effective_q ===============


class TestCommandEffective:
    """effective_p/q 解 NO_CHANGE 到具體 float"""

    def test_effective_p_no_change_with_explicit_fallback(self):
        """p_target=NO_CHANGE + fallback=5.0 → 5.0"""
        cmd = Command(p_target=NO_CHANGE, q_target=100.0)
        assert cmd.effective_p(fallback=5.0) == 5.0

    def test_effective_p_no_change_default_fallback_is_zero(self):
        """effective_p() 不傳 fallback → 0.0"""
        cmd = Command(p_target=NO_CHANGE)
        assert cmd.effective_p() == 0.0

    def test_effective_p_float_ignores_fallback(self):
        """p_target=50.0 時 fallback 無效，直接回傳 50.0"""
        cmd = Command(p_target=50.0)
        assert cmd.effective_p(fallback=999.0) == 50.0

    def test_effective_q_no_change_with_fallback(self):
        cmd = Command(p_target=100.0, q_target=NO_CHANGE)
        assert cmd.effective_q(fallback=-3.5) == -3.5

    def test_effective_q_default_fallback_is_zero(self):
        cmd = Command(q_target=NO_CHANGE)
        assert cmd.effective_q() == 0.0


# =============== Command.with_p / with_q ===============


class TestCommandWithReplacement:
    """with_p/with_q 以 dataclasses.replace 建立新 Command"""

    def test_with_p_replaces_no_change_with_float(self):
        cmd = Command(p_target=NO_CHANGE, q_target=100.0)
        new = cmd.with_p(50.0)
        assert new.p_target == 50.0
        assert new.q_target == 100.0
        # 原 Command 不變
        assert is_no_change(cmd.p_target)

    def test_with_p_replaces_float_with_no_change(self):
        cmd = Command(p_target=50.0, q_target=100.0)
        new = cmd.with_p(NO_CHANGE)
        assert is_no_change(new.p_target)
        assert new.q_target == 100.0

    def test_with_q_replaces_no_change_with_float(self):
        cmd = Command(p_target=10.0, q_target=NO_CHANGE)
        new = cmd.with_q(-20.0)
        assert new.p_target == 10.0
        assert new.q_target == -20.0

    def test_with_p_preserves_is_fallback(self):
        """with_p 透過 dataclasses.replace，fallback 旗標應保留"""
        cmd = Command(p_target=0.0, q_target=0.0, is_fallback=True)
        new = cmd.with_p(NO_CHANGE)
        assert new.is_fallback is True


# =============== Command.__str__ ===============


class TestCommandStr:
    """__str__ 顯示 NO_CHANGE / 數值的混合格式"""

    def test_str_with_no_change_p(self):
        cmd = Command(p_target=NO_CHANGE, q_target=100.0)
        s = str(cmd)
        assert "NO_CHANGE" in s
        assert "100" in s

    def test_str_with_no_change_both(self):
        cmd = Command(p_target=NO_CHANGE, q_target=NO_CHANGE)
        s = str(cmd)
        assert s.count("NO_CHANGE") == 2

    def test_str_with_float_both(self):
        cmd = Command(p_target=50.0, q_target=-25.5)
        s = str(cmd)
        assert "50" in s
        assert "-25" in s
        assert "NO_CHANGE" not in s


# =============== fallback 路徑 刻意使用 float 0.0 ===============


class TestFallbackUsesFloatZero:
    """Command(is_fallback=True) 架構決策：fallback 必須是明確 0.0，不是 NO_CHANGE

    這是 StrategyExecutor 在 execute 異常時的安全停機語義 — 不能保留可能危險的舊值。
    """

    def test_default_fallback_command_uses_float_zero(self):
        """Command(p_target=0.0, q_target=0.0, is_fallback=True) 欄位為 float 而非 NO_CHANGE"""
        cmd = Command(p_target=0.0, q_target=0.0, is_fallback=True)
        assert cmd.is_fallback is True
        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0
        assert not is_no_change(cmd.p_target)
        assert not is_no_change(cmd.q_target)

    def test_fallback_with_no_change_is_theoretically_allowable_but_discouraged(self):
        """技術上 Command(p_target=NO_CHANGE, is_fallback=True) 可建立（dataclass 沒擋），
        但 StrategyExecutor 的 fallback 路徑刻意只寫 float 0.0，此行為由 executor 契約保證。
        """
        cmd = Command(p_target=NO_CHANGE, q_target=NO_CHANGE, is_fallback=True)
        assert cmd.is_fallback is True
        # dataclass 不阻擋，但語義上不鼓勵


# =============== dataclasses.replace 整合 ===============


class TestDataclassesReplace:
    """Command 作為 frozen dataclass 可用 dataclasses.replace"""

    def test_replace_p_with_no_change(self):
        cmd = Command(p_target=100.0, q_target=50.0)
        new = dataclasses.replace(cmd, p_target=NO_CHANGE)
        assert is_no_change(new.p_target)
        assert new.q_target == 50.0

    def test_replace_preserves_untouched_fields(self):
        cmd = Command(p_target=100.0, q_target=50.0, is_fallback=True)
        new = dataclasses.replace(cmd, p_target=NO_CHANGE)
        assert new.is_fallback is True
        assert new.q_target == 50.0
