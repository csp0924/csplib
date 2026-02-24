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
