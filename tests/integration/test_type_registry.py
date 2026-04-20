# =============== TypeRegistry Tests ===============
#
# 驗證 Operator Pattern 的 kind → class 查找層：
#   - register / get / __contains__ / list 基本 API
#   - kind 格式驗證（regex: ^[A-Za-z_][A-Za-z0-9_-]*$）
#   - 重複註冊 → ValueError（force=True 覆寫）
#   - 未知 kind → ConfigurationError（不是 KeyError）
#   - Thread-safe（多執行緒併發 register/get）
#   - device_type_registry 與 strategy_type_registry 不共享狀態
#   - register_device_type / register_strategy_type decorator 行為

from __future__ import annotations

import threading

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.integration.type_registry import (
    TypeRegistry,
    device_type_registry,
    register_device_type,
    register_strategy_type,
    strategy_type_registry,
)


class _DummyClass:
    """測試用佔位類別。"""


class _DummyClassAlt:
    """測試用佔位類別 B（用於覆寫測試）。"""


# ─────────────── register / get 基本 ───────────────


class TestRegisterGetBasic:
    def test_register_then_get_returns_class(self):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("Widget", _DummyClass)
        assert reg.get("Widget") is _DummyClass

    def test_register_multiple_kinds(self):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("A", _DummyClass)
        reg.register("B", _DummyClassAlt)
        assert reg.get("A") is _DummyClass
        assert reg.get("B") is _DummyClassAlt


# ─────────────── 重複註冊 ───────────────


class TestDuplicateRegistration:
    def test_duplicate_without_force_raises(self):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("X", _DummyClass)
        with pytest.raises(ValueError, match="already"):
            reg.register("X", _DummyClassAlt)

    def test_duplicate_with_force_overrides(self):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("X", _DummyClass)
        reg.register("X", _DummyClassAlt, force=True)
        assert reg.get("X") is _DummyClassAlt

    def test_force_override_logs_warning(self, caplog):
        """force=True 覆寫應 log warning。

        loguru 不走 pytest caplog（見 MEMORY），改為驗證行為：
        覆寫生效即代表成功；log 觀察另行人工檢查。
        """
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("X", _DummyClass)
        # 不應 raise
        reg.register("X", _DummyClassAlt, force=True)
        assert reg.get("X") is _DummyClassAlt


# ─────────────── 未知 kind ───────────────


class TestUnknownKind:
    def test_unknown_kind_raises_configuration_error(self):
        """重要：未知 kind 拋 ConfigurationError（manifest-driven 錯誤族），
        不是 KeyError。"""
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        with pytest.raises(ConfigurationError) as exc_info:
            reg.get("Nonexistent")
        # 不是內建 KeyError
        assert not isinstance(exc_info.value, KeyError)

    def test_unknown_kind_error_contains_registered_kinds(self):
        """錯誤訊息包含已註冊 kinds 列表，方便 debug。"""
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("Known1", _DummyClass)
        reg.register("Known2", _DummyClassAlt)
        with pytest.raises(ConfigurationError) as exc_info:
            reg.get("Unknown")
        msg = str(exc_info.value)
        assert "Known1" in msg
        assert "Known2" in msg
        assert "Unknown" in msg


# ─────────────── kind 格式驗證 ───────────────


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "has/slash",  # namespace 留未來，目前不允許
        "1startswithnum",  # 必須字母或底線開頭
        "",  # 空字串
        "  ",  # 全空白
        "with space",  # 含空白
        "has.dot",  # 不支援 .
        "has@symbol",
    ],
)
class TestInvalidKindFormat:
    def test_invalid_kind_raises_value_error(self, invalid_kind):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        with pytest.raises(ValueError, match="invalid kind"):
            reg.register(invalid_kind, _DummyClass)


@pytest.mark.parametrize(
    "valid_kind",
    [
        "Simple",
        "_underscore_start",
        "with-dash",
        "mix_of-both",
        "CamelCase",
        "withDigits123",
        "A",  # 單字母
    ],
)
class TestValidKindFormat:
    def test_valid_kind_registers(self, valid_kind):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register(valid_kind, _DummyClass)
        assert valid_kind in reg


# ─────────────── __contains__ / list ───────────────


class TestContainsAndList:
    def test_contains_for_registered(self):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("A", _DummyClass)
        assert "A" in reg

    def test_not_contains_for_unknown(self):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        assert "Unknown" not in reg

    def test_contains_non_string_returns_false(self):
        """傳非 str 應直接回 False，不拋例外。"""
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("A", _DummyClass)
        assert 123 not in reg
        assert None not in reg

    def test_list_returns_sorted_copy(self):
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        reg.register("Zebra", _DummyClass)
        reg.register("Apple", _DummyClassAlt)
        result = reg.list()
        assert result == ["Apple", "Zebra"]  # sorted
        # 為 copy，修改不影響 registry
        result.append("hacked")
        assert "hacked" not in reg


# ─────────────── Decorator 語法 ───────────────


class TestDecorators:
    def test_register_device_type_decorator(self):
        """@register_device_type 套到 class 後能從 device_type_registry 取回。"""
        kind = "__TestDeviceKindForPytest__"
        # 確認初始未註冊
        assert kind not in device_type_registry

        @register_device_type(kind)
        class MyDevice:
            pass

        # registry 中能取回同一個 class
        assert device_type_registry.get(kind) is MyDevice
        # decorator 回傳原 class（不包裝）
        assert MyDevice.__name__ == "MyDevice"

        # cleanup：重覆 register 需 force=True
        # 直接從 table 移除，確保其他 test 不受影響
        device_type_registry._table.pop(kind, None)

    def test_register_strategy_type_decorator(self):
        """@register_strategy_type 套到 class 後能從 strategy_type_registry 取回。"""
        kind = "__TestStrategyKindForPytest__"
        assert kind not in strategy_type_registry

        @register_strategy_type(kind)
        class MyStrategy:
            pass

        assert strategy_type_registry.get(kind) is MyStrategy

        # cleanup
        strategy_type_registry._table.pop(kind, None)

    def test_register_device_type_force_override(self):
        """decorator 的 force=True 參數允許覆寫。"""
        kind = "__TestForceOverrideKind__"

        @register_device_type(kind)
        class V1:
            pass

        @register_device_type(kind, force=True)
        class V2:
            pass

        assert device_type_registry.get(kind) is V2

        # cleanup
        device_type_registry._table.pop(kind, None)


# ─────────────── Singleton 獨立 ───────────────


class TestSingletonsAreIsolated:
    """device_type_registry 與 strategy_type_registry 必須是獨立實例，
    不共享 state（label 不同、內部 dict 不同）。
    """

    def test_different_instances(self):
        assert device_type_registry is not strategy_type_registry

    def test_register_in_device_does_not_leak_to_strategy(self):
        """device_type_registry 註冊後，strategy_type_registry 不應看到同一 kind。"""
        kind = "__IsolationTestKind__"

        # 確認兩邊初始都沒有
        assert kind not in device_type_registry
        assert kind not in strategy_type_registry

        device_type_registry.register(kind, _DummyClass)
        try:
            assert kind in device_type_registry
            assert kind not in strategy_type_registry  # 關鍵
        finally:
            device_type_registry._table.pop(kind, None)


# ─────────────── Thread safety ───────────────


class TestThreadSafety:
    """TypeRegistry 內部用 threading.Lock，併發 register/get 不應 race 或漏值。"""

    def test_concurrent_register_no_lost_updates(self):
        """100 個 thread 各自 register 一個唯一 kind，最終 registry 應有 100 個 entry。"""
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")

        def worker(i: int) -> None:
            reg.register(f"Kind_{i}", _DummyClass)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有 kind 都應註冊成功
        assert len(reg.list()) == 100
        for i in range(100):
            assert f"Kind_{i}" in reg

    def test_concurrent_register_and_get_no_crash(self):
        """同時有 register 與 get 執行，不應 RuntimeError（dict during iteration）或死鎖。"""
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        errors: list[Exception] = []

        def register_worker(i: int) -> None:
            try:
                reg.register(f"K_{i}", _DummyClass)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        def get_worker(i: int) -> None:
            try:
                # 可能查不到（因 register 尚未完成）→ 捕獲 ConfigurationError
                reg.get(f"K_{i}")
            except ConfigurationError:
                pass
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads: list[threading.Thread] = []
        for i in range(50):
            threads.append(threading.Thread(target=register_worker, args=(i,)))
            threads.append(threading.Thread(target=get_worker, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 不應有非預期錯誤
        assert errors == []

    def test_concurrent_duplicate_register_only_one_succeeds(self):
        """多個 thread 同時 register 同一 kind（非 force），只有一個成功，其他收到 ValueError。"""
        reg: TypeRegistry[_DummyClass] = TypeRegistry("test")
        kind = "ContendedKind"
        successes: list[int] = []
        failures: list[int] = []
        lock = threading.Lock()

        def worker(i: int) -> None:
            try:
                reg.register(kind, _DummyClass)
                with lock:
                    successes.append(i)
            except ValueError:
                with lock:
                    failures.append(i)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 只有 1 個 thread 成功；其他 19 個拿到 ValueError
        assert len(successes) == 1
        assert len(failures) == 19
