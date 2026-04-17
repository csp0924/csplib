"""Tests for RuntimeParameters — Thread-safe key-value container."""

import threading
from unittest.mock import MagicMock

import pytest

from csp_lib.core.runtime_params import RuntimeParameters

# ===========================================================================
# Construction & Basic Read
# ===========================================================================


class TestRuntimeParametersInit:
    def test_empty_construction(self):
        params = RuntimeParameters()
        assert len(params) == 0
        assert params.keys() == []

    def test_construction_with_kwargs(self):
        params = RuntimeParameters(soc_max=95.0, soc_min=5.0)
        assert params.get("soc_max") == 95.0
        assert params.get("soc_min") == 5.0
        assert len(params) == 2

    def test_repr(self):
        params = RuntimeParameters(a=1, b=2)
        r = repr(params)
        assert "RuntimeParameters" in r
        assert "a" in r
        assert "b" in r


# ===========================================================================
# get / __contains__ / keys / __len__
# ===========================================================================


class TestRuntimeParametersRead:
    def test_get_existing_key(self):
        params = RuntimeParameters(x=42)
        assert params.get("x") == 42

    def test_get_missing_key_returns_default(self):
        params = RuntimeParameters()
        assert params.get("missing") is None
        assert params.get("missing", -1) == -1

    def test_contains_true(self):
        params = RuntimeParameters(a=1)
        assert "a" in params

    def test_contains_false(self):
        params = RuntimeParameters(a=1)
        assert "b" not in params

    def test_keys_returns_list(self):
        params = RuntimeParameters(x=1, y=2, z=3)
        keys = params.keys()
        assert sorted(keys) == ["x", "y", "z"]

    def test_len(self):
        params = RuntimeParameters(a=1, b=2)
        assert len(params) == 2


# ===========================================================================
# snapshot
# ===========================================================================


class TestRuntimeParametersSnapshot:
    def test_snapshot_returns_dict_copy(self):
        params = RuntimeParameters(soc=50.0, voltage=400)
        snap = params.snapshot()
        assert snap == {"soc": 50.0, "voltage": 400}
        # Mutating snapshot must not affect original
        snap["soc"] = 999.0
        assert params.get("soc") == 50.0

    def test_snapshot_empty(self):
        params = RuntimeParameters()
        assert params.snapshot() == {}


# ===========================================================================
# set
# ===========================================================================


class TestRuntimeParametersSet:
    def test_set_new_key(self):
        params = RuntimeParameters()
        params.set("power", 100.0)
        assert params.get("power") == 100.0
        assert len(params) == 1

    def test_set_overwrite_existing(self):
        params = RuntimeParameters(power=100.0)
        params.set("power", 200.0)
        assert params.get("power") == 200.0

    def test_set_same_value_no_observer_fire(self):
        params = RuntimeParameters(x=10)
        cb = MagicMock()
        params.on_change(cb)
        params.set("x", 10)  # same value
        cb.assert_not_called()

    def test_set_different_value_fires_observer(self):
        params = RuntimeParameters(x=10)
        cb = MagicMock()
        params.on_change(cb)
        params.set("x", 20)
        cb.assert_called_once_with("x", 10, 20)


# ===========================================================================
# update
# ===========================================================================


class TestRuntimeParametersUpdate:
    def test_update_multiple_keys(self):
        params = RuntimeParameters(a=1, b=2)
        params.update({"a": 10, "b": 20, "c": 30})
        assert params.get("a") == 10
        assert params.get("b") == 20
        assert params.get("c") == 30

    def test_update_fires_observers_for_changed_keys_only(self):
        params = RuntimeParameters(a=1, b=2)
        cb = MagicMock()
        params.on_change(cb)
        params.update({"a": 1, "b": 99})
        # Only b changed (a stayed 1)
        cb.assert_called_once_with("b", 2, 99)

    def test_update_empty_dict_no_effect(self):
        params = RuntimeParameters(a=1)
        cb = MagicMock()
        params.on_change(cb)
        params.update({})
        cb.assert_not_called()
        assert params.get("a") == 1


# ===========================================================================
# setdefault
# ===========================================================================


class TestRuntimeParametersSetdefault:
    def test_setdefault_key_missing(self):
        params = RuntimeParameters()
        result = params.setdefault("x", 42)
        assert result == 42
        assert params.get("x") == 42

    def test_setdefault_key_exists(self):
        params = RuntimeParameters(x=10)
        result = params.setdefault("x", 42)
        assert result == 10
        assert params.get("x") == 10


# ===========================================================================
# delete
# ===========================================================================


class TestRuntimeParametersDelete:
    def test_delete_existing_key(self):
        params = RuntimeParameters(a=1, b=2)
        params.delete("a")
        assert "a" not in params
        assert len(params) == 1

    def test_delete_missing_key_silent(self):
        params = RuntimeParameters()
        params.delete("nonexistent")  # should not raise

    def test_delete_fires_observer(self):
        params = RuntimeParameters(x=10)
        cb = MagicMock()
        params.on_change(cb)
        params.delete("x")
        cb.assert_called_once_with("x", 10, None)

    def test_delete_none_value_no_observer(self):
        """Deleting a key that was never set (pop returns None) should not fire."""
        params = RuntimeParameters()
        cb = MagicMock()
        params.on_change(cb)
        params.delete("nonexistent")
        cb.assert_not_called()


# ===========================================================================
# Observer management
# ===========================================================================


class TestRuntimeParametersObservers:
    def test_multiple_observers(self):
        params = RuntimeParameters(x=1)
        cb1 = MagicMock()
        cb2 = MagicMock()
        params.on_change(cb1)
        params.on_change(cb2)
        params.set("x", 2)
        cb1.assert_called_once_with("x", 1, 2)
        cb2.assert_called_once_with("x", 1, 2)

    def test_remove_observer(self):
        params = RuntimeParameters(x=1)
        cb = MagicMock()
        params.on_change(cb)
        params.remove_observer(cb)
        params.set("x", 2)
        cb.assert_not_called()

    def test_remove_nonexistent_observer_silent(self):
        params = RuntimeParameters()
        cb = MagicMock()
        params.remove_observer(cb)  # should not raise

    def test_observer_exception_does_not_block_others(self):
        """A failing observer should not prevent subsequent observers from running."""
        params = RuntimeParameters(x=1)
        bad_cb = MagicMock(side_effect=ValueError("boom"))
        good_cb = MagicMock()
        params.on_change(bad_cb)
        params.on_change(good_cb)
        params.set("x", 2)
        bad_cb.assert_called_once()
        good_cb.assert_called_once_with("x", 1, 2)


# ===========================================================================
# Thread safety (structural)
# ===========================================================================


class TestRuntimeParametersThreadSafety:
    def test_concurrent_set_and_get(self):
        """Many threads writing and reading should not corrupt state."""
        params = RuntimeParameters()
        errors = []

        def writer(key: str, value: int):
            try:
                for _ in range(200):
                    params.set(key, value)
            except Exception as e:
                errors.append(e)

        def reader(key: str):
            try:
                for _ in range(200):
                    params.get(key)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(f"k{i}", i)))
            threads.append(threading.Thread(target=reader, args=(f"k{i}",)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(params) == 5

    def test_concurrent_snapshot(self):
        """snapshot() should not crash under concurrent modification."""
        params = RuntimeParameters(**{f"k{i}": i for i in range(20)})
        errors = []

        def updater():
            try:
                for i in range(100):
                    params.update({f"k{i % 20}": i})
            except Exception as e:
                errors.append(e)

        def snapshotter():
            try:
                for _ in range(100):
                    snap = params.snapshot()
                    assert isinstance(snap, dict)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=updater),
            threading.Thread(target=updater),
            threading.Thread(target=snapshotter),
            threading.Thread(target=snapshotter),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ===========================================================================
# Attribute-style 存取（WI-RP-01）
# ===========================================================================


class TestRuntimeParametersAttributeAccess:
    """驗證 __getattr__ / __setattr__ 對 .get() / .set() 的 dispatch 行為"""

    def test_attr_read_existing_equals_get(self):
        """params.soc_max 讀取等同 params.get("soc_max")"""
        params = RuntimeParameters(soc_max=95.0)
        assert params.soc_max == params.get("soc_max")
        assert params.soc_max == 95.0

    def test_attr_write_existing_equals_set(self):
        """params.soc_max = 90 寫入等同 params.set("soc_max", 90)"""
        params = RuntimeParameters(soc_max=95.0)
        params.soc_max = 90.0
        assert params.get("soc_max") == 90.0

    def test_attr_write_triggers_observer(self):
        """Attribute-style 寫入必須觸發 observer（等同 set()）"""
        params = RuntimeParameters(soc_max=95.0)
        cb = MagicMock()
        params.on_change(cb)
        params.soc_max = 90.0
        cb.assert_called_once_with("soc_max", 95.0, 90.0)

    def test_attr_write_same_value_no_observer(self):
        """寫入相同值不觸發 observer（與 set() 行為一致）"""
        params = RuntimeParameters(soc_max=95.0)
        cb = MagicMock()
        params.on_change(cb)
        params.soc_max = 95.0
        cb.assert_not_called()

    def test_attr_read_missing_raises_attributeerror(self):
        """不存在參數必須拋 AttributeError（而非回傳 None）"""
        params = RuntimeParameters()
        with pytest.raises(AttributeError):
            _ = params.missing_param

    def test_attr_read_missing_error_message_mentions_key(self):
        """AttributeError 訊息應包含缺失的參數名稱"""
        params = RuntimeParameters(x=1)
        with pytest.raises(AttributeError, match="missing_param"):
            _ = params.missing_param

    def test_hasattr_existing_true(self):
        """hasattr 對存在參數回傳 True"""
        params = RuntimeParameters(existing=42)
        assert hasattr(params, "existing") is True

    def test_hasattr_missing_false(self):
        """hasattr 對缺失參數回傳 False（由 AttributeError 驅動）"""
        params = RuntimeParameters()
        assert hasattr(params, "missing") is False

    def test_underscore_attr_read_raises(self):
        """底線開頭未知屬性拋 AttributeError（不 dispatch 到 _values）"""
        params = RuntimeParameters()
        # 即使存入名為 "_foo" 的 key，__getattr__ 也視為內部屬性拒絕
        with pytest.raises(AttributeError):
            _ = params._not_a_real_attr

    def test_internal_slots_still_accessible(self):
        """__slots__ 中的 _lock / _values / _observers 仍正常運作"""
        params = RuntimeParameters(a=1)
        assert isinstance(params._lock, type(threading.Lock()))
        assert params._values == {"a": 1}
        assert params._observers == []

    def test_internal_slots_not_dispatched_to_set(self):
        """__setattr__ 寫入 _xxx 不走 .set()，不會無窮遞迴或污染 _values"""
        params = RuntimeParameters()
        # 建構當下 self._lock = ... 就是此路徑；能完成建構即代表通過
        assert "_lock" not in params._values
        assert "_values" not in params._values
        assert "_observers" not in params._values

    def test_attr_dynamic_add_new_key(self):
        """params.new_key = 1 動態新增參數，get() 可讀取"""
        params = RuntimeParameters()
        params.new_key = 42
        assert params.get("new_key") == 42
        assert params.new_key == 42
        assert "new_key" in params

    def test_attr_dynamic_add_fires_observer(self):
        """動態新增時 observer 被觸發，old=None"""
        params = RuntimeParameters()
        cb = MagicMock()
        params.on_change(cb)
        params.new_key = 99
        cb.assert_called_once_with("new_key", None, 99)

    def test_attr_read_delegates_to_get_for_all_value_types(self):
        """對 dict / list / None 等各種值類型的讀取都正常"""
        params = RuntimeParameters(d={"k": 1}, lst=[1, 2, 3], none_val=None)
        assert params.d == {"k": 1}
        assert params.lst == [1, 2, 3]
        # 注意：值本身為 None 與「key 不存在」在 attribute-style 下的差異
        # key 存在但值為 None → 回傳 None（不拋 AttributeError）
        assert params.none_val is None


class TestRuntimeParametersSubclassing:
    """Subclassing 情境驗證 docstring 警告的行為"""

    def test_subclass_without_class_attr_works_normally(self):
        """Subclass 未覆蓋參數名稱時，attribute-style 存取正常"""

        class MyParams(RuntimeParameters):
            pass

        params = MyParams(soc_max=90.0)
        assert params.soc_max == 90.0
        params.soc_max = 80.0
        assert params.get("soc_max") == 80.0

    def test_subclass_class_attr_shadows_getattr(self):
        """Warning in docstring: class attribute 與參數同名時，讀取命中 class attr"""

        class MyParams(RuntimeParameters):
            soc_max = 100.0  # class attribute shadow

        params = MyParams(soc_max=90.0)
        # 傳統屬性查找先命中 class attribute → __getattr__ 不會被呼叫
        assert params.soc_max == 100.0  # NOT 90.0
        # 但 .get() 仍讀取 _values（資料層級）
        assert params.get("soc_max") == 90.0

    def test_subclass_class_attr_write_still_dispatches_to_set(self):
        """即使 class attr 存在，__setattr__ 對非底線名稱仍走 set() 路徑"""

        class MyParams(RuntimeParameters):
            soc_max = 100.0

        params = MyParams(soc_max=90.0)
        params.soc_max = 80.0
        # .set() 更新 _values，不改動 class attribute
        assert params.get("soc_max") == 80.0
        assert MyParams.soc_max == 100.0  # class attribute 未被動到

    def test_subclass_with_extra_slots_preserves_internal(self):
        """Subclass 定義額外 __slots__ 時，底線屬性仍走原生路徑"""

        class MyParams(RuntimeParameters):
            __slots__ = ("_extra",)

            def __init__(self, **kw):
                super().__init__(**kw)
                self._extra = "internal"  # 透過 object.__setattr__ 路徑

        params = MyParams(a=1)
        assert params._extra == "internal"
        assert params.a == 1
