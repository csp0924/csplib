"""Tests for RuntimeParameters — Thread-safe key-value container."""

import threading
from unittest.mock import MagicMock

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
