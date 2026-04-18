"""Tests for DeviceRegistry."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from csp_lib.integration.registry import DeviceRegistry


def _make_device(device_id: str, responsive: bool = True) -> MagicMock:
    """Create a mock AsyncModbusDevice."""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    return dev


class _FakeDevice:
    """可翻轉 is_responsive 的輕量 fake 設備（避開 PropertyMock 一次性求值陷阱）"""

    def __init__(self, device_id: str, responsive: bool = True) -> None:
        self.device_id = device_id
        self.is_responsive = responsive


def _make_mutable_device(device_id: str, responsive: bool = True) -> _FakeDevice:
    """建立可翻轉 is_responsive 狀態的 fake 設備"""
    return _FakeDevice(device_id, responsive)


def _set_responsive(dev: _FakeDevice, value: bool) -> None:
    """翻轉 fake 設備的 is_responsive"""
    dev.is_responsive = value


class TestRegistration:
    def test_register_and_lookup(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)
        assert reg.get_device("d1") is dev
        assert "d1" in reg
        assert len(reg) == 1

    def test_register_with_traits(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["pcs", "inverter"])
        assert reg.get_traits("d1") == {"pcs", "inverter"}

    def test_duplicate_register_raises(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(dev)

    def test_unregister(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["pcs"])
        reg.unregister("d1")
        assert reg.get_device("d1") is None
        assert "d1" not in reg
        assert len(reg) == 0
        assert reg.get_devices_by_trait("pcs") == []

    def test_unregister_nonexistent_no_error(self):
        reg = DeviceRegistry()
        reg.unregister("missing")  # should not raise


class TestTraitManagement:
    def test_add_trait(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)
        reg.add_trait("d1", "bms")
        assert "bms" in reg.get_traits("d1")

    def test_add_trait_unregistered_raises(self):
        reg = DeviceRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.add_trait("missing", "pcs")

    def test_remove_trait(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["pcs", "inverter"])
        reg.remove_trait("d1", "pcs")
        assert reg.get_traits("d1") == {"inverter"}
        assert reg.get_devices_by_trait("pcs") == []

    def test_remove_trait_unregistered_raises(self):
        reg = DeviceRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.remove_trait("missing", "pcs")


class TestQueries:
    def test_get_device_not_found(self):
        reg = DeviceRegistry()
        assert reg.get_device("missing") is None

    def test_get_devices_by_trait_sorted(self):
        reg = DeviceRegistry()
        d2 = _make_device("d2")
        d1 = _make_device("d1")
        reg.register(d2, traits=["pcs"])
        reg.register(d1, traits=["pcs"])
        result = reg.get_devices_by_trait("pcs")
        assert [d.device_id for d in result] == ["d1", "d2"]

    def test_get_devices_by_trait_empty(self):
        reg = DeviceRegistry()
        assert reg.get_devices_by_trait("missing") == []

    def test_get_responsive_devices_by_trait(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=True)
        d2 = _make_device("d2", responsive=False)
        d3 = _make_device("d3", responsive=True)
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])
        reg.register(d3, traits=["pcs"])
        result = reg.get_responsive_devices_by_trait("pcs")
        assert [d.device_id for d in result] == ["d1", "d3"]

    def test_get_first_responsive_device_by_trait(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=False)
        d2 = _make_device("d2", responsive=True)
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])
        result = reg.get_first_responsive_device_by_trait("pcs")
        assert result is d2

    def test_get_first_responsive_device_by_trait_none(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1", responsive=False)
        reg.register(d1, traits=["pcs"])
        assert reg.get_first_responsive_device_by_trait("pcs") is None

    def test_get_traits_unregistered(self):
        reg = DeviceRegistry()
        assert reg.get_traits("missing") == set()

    def test_all_devices_sorted(self):
        reg = DeviceRegistry()
        d2 = _make_device("d2")
        d1 = _make_device("d1")
        reg.register(d2)
        reg.register(d1)
        assert [d.device_id for d in reg.all_devices] == ["d1", "d2"]

    def test_all_traits_sorted(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        reg.register(d1, traits=["zz", "aa", "mm"])
        assert reg.all_traits == ["aa", "mm", "zz"]


# ===========================================================================
# Status-change 觀察者（WI-GW-02）
# ===========================================================================


class TestStatusChangeObservers:
    """覆蓋 on_status_change / remove_status_observer / notify_status / _last_responsive"""

    def test_first_notify_builds_baseline_no_fire(self):
        """首次 notify_status 僅建立 baseline，不觸發 observer"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        cb = MagicMock()
        reg.on_status_change(cb)

        reg.notify_status("d1")

        cb.assert_not_called()
        # baseline 已建立
        assert reg._last_responsive.get("d1") is True

    def test_false_to_true_triggers_once(self):
        """狀態從 False → True，observer 觸發一次，responsive=True"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=False)
        reg.register(dev)
        cb = MagicMock()
        reg.on_status_change(cb)

        reg.notify_status("d1")  # baseline: False
        _set_responsive(dev, True)
        reg.notify_status("d1")  # 變化：False → True

        cb.assert_called_once_with("d1", True)

    def test_true_to_false_triggers_once(self):
        """狀態從 True → False，observer 觸發一次，responsive=False"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        cb = MagicMock()
        reg.on_status_change(cb)

        reg.notify_status("d1")  # baseline: True
        _set_responsive(dev, False)
        reg.notify_status("d1")  # 變化：True → False

        cb.assert_called_once_with("d1", False)

    def test_same_status_repeated_no_refire(self):
        """重複呼叫 notify_status 但狀態沒變，observer 不再觸發（去重）"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        cb = MagicMock()
        reg.on_status_change(cb)

        reg.notify_status("d1")  # baseline
        reg.notify_status("d1")  # same True
        reg.notify_status("d1")  # same True

        cb.assert_not_called()

    def test_multiple_transitions(self):
        """連續多次狀態變化，每次都觸發"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        cb = MagicMock()
        reg.on_status_change(cb)

        reg.notify_status("d1")  # baseline True
        _set_responsive(dev, False)
        reg.notify_status("d1")  # True → False
        _set_responsive(dev, True)
        reg.notify_status("d1")  # False → True
        _set_responsive(dev, False)
        reg.notify_status("d1")  # True → False

        assert cb.call_count == 3
        assert cb.call_args_list[0].args == ("d1", False)
        assert cb.call_args_list[1].args == ("d1", True)
        assert cb.call_args_list[2].args == ("d1", False)

    def test_multiple_observers_all_called(self):
        """多個 observer 都應被呼叫"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        cb1 = MagicMock()
        cb2 = MagicMock()
        reg.on_status_change(cb1)
        reg.on_status_change(cb2)

        reg.notify_status("d1")  # baseline
        _set_responsive(dev, False)
        reg.notify_status("d1")

        cb1.assert_called_once_with("d1", False)
        cb2.assert_called_once_with("d1", False)

    def test_observer_exception_does_not_block_others(self):
        """其中一個 observer 拋例外，其他 observer 仍被呼叫"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        bad_cb = MagicMock(side_effect=RuntimeError("boom"))
        good_cb_before = MagicMock()
        good_cb_after = MagicMock()
        # 註冊順序：good_before → bad → good_after
        reg.on_status_change(good_cb_before)
        reg.on_status_change(bad_cb)
        reg.on_status_change(good_cb_after)

        reg.notify_status("d1")  # baseline
        _set_responsive(dev, False)
        reg.notify_status("d1")  # fire

        good_cb_before.assert_called_once_with("d1", False)
        bad_cb.assert_called_once_with("d1", False)
        good_cb_after.assert_called_once_with("d1", False)  # 未被 bad 的例外中斷

    def test_notify_unregistered_device_silent(self):
        """對未註冊的 device_id 呼叫 notify_status 不拋、不觸發 observer"""
        reg = DeviceRegistry()
        cb = MagicMock()
        reg.on_status_change(cb)

        reg.notify_status("unregistered")  # 不拋

        cb.assert_not_called()
        assert "unregistered" not in reg._last_responsive

    def test_unregister_clears_baseline(self):
        """unregister 後 _last_responsive 對該 device_id 應被清除"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        reg.notify_status("d1")
        assert "d1" in reg._last_responsive

        reg.unregister("d1")

        assert "d1" not in reg._last_responsive

    def test_reregister_same_id_fresh_baseline(self):
        """unregister 後以同 id re-register，視為新 baseline（首次 notify 不觸發）"""
        reg = DeviceRegistry()
        dev1 = _make_mutable_device("d1", responsive=True)
        reg.register(dev1)
        reg.notify_status("d1")  # baseline True
        reg.unregister("d1")

        # 重新註冊同名但初始 responsive=False 的設備
        dev2 = _make_mutable_device("d1", responsive=False)
        reg.register(dev2)
        cb = MagicMock()
        reg.on_status_change(cb)

        # 首次 notify 應僅建立新 baseline，不觸發（儘管前一輪 baseline 是 True）
        reg.notify_status("d1")
        cb.assert_not_called()
        assert reg._last_responsive["d1"] is False

        # 後續變化才觸發
        _set_responsive(dev2, True)
        reg.notify_status("d1")
        cb.assert_called_once_with("d1", True)

    def test_remove_observer_prevents_fire(self):
        """remove_status_observer 後 observer 不再被呼叫"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        cb = MagicMock()
        reg.on_status_change(cb)
        reg.notify_status("d1")  # baseline

        reg.remove_status_observer(cb)

        _set_responsive(dev, False)
        reg.notify_status("d1")
        cb.assert_not_called()

    def test_remove_nonexistent_observer_silent(self):
        """移除未註冊的 callback 不拋例外"""
        reg = DeviceRegistry()
        cb = MagicMock()
        # 從未註冊過
        reg.remove_status_observer(cb)  # should not raise

    def test_remove_observer_only_affects_that_one(self):
        """移除某個 observer 不影響其他仍註冊的 observer"""
        reg = DeviceRegistry()
        dev = _make_mutable_device("d1", responsive=True)
        reg.register(dev)
        cb_keep = MagicMock()
        cb_remove = MagicMock()
        reg.on_status_change(cb_keep)
        reg.on_status_change(cb_remove)
        reg.notify_status("d1")  # baseline

        reg.remove_status_observer(cb_remove)

        _set_responsive(dev, False)
        reg.notify_status("d1")
        cb_keep.assert_called_once_with("d1", False)
        cb_remove.assert_not_called()

    def test_notify_isolated_per_device(self):
        """多裝置的 baseline 彼此獨立"""
        reg = DeviceRegistry()
        d1 = _make_mutable_device("d1", responsive=True)
        d2 = _make_mutable_device("d2", responsive=False)
        reg.register(d1)
        reg.register(d2)
        cb = MagicMock()
        reg.on_status_change(cb)

        reg.notify_status("d1")  # d1 baseline True
        reg.notify_status("d2")  # d2 baseline False
        cb.assert_not_called()

        _set_responsive(d1, False)
        reg.notify_status("d1")  # d1: True → False
        cb.assert_called_once_with("d1", False)

        # d2 沒變，不應觸發
        reg.notify_status("d2")
        assert cb.call_count == 1
