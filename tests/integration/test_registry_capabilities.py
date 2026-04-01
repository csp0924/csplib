"""Tests for DeviceRegistry.register_with_capabilities."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from csp_lib.integration.registry import DeviceRegistry


def _make_device(device_id: str, capabilities: dict | None = None, responsive: bool = True) -> MagicMock:
    """Create a mock AsyncModbusDevice with capabilities."""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).capabilities = PropertyMock(return_value=capabilities or {})
    return dev


class TestRegisterWithCapabilities:
    def test_auto_traits_from_capabilities(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={"active_power_control": MagicMock(), "soc_readable": MagicMock()})
        reg.register_with_capabilities(dev, extra_traits=["pcs"])

        traits = reg.get_traits("d1")
        assert "pcs" in traits
        assert "cap:active_power_control" in traits
        assert "cap:soc_readable" in traits

    def test_query_by_auto_trait(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={"active_power_control": MagicMock(), "soc_readable": MagicMock()})
        reg.register_with_capabilities(dev, extra_traits=["pcs"])

        result = reg.get_devices_by_trait("cap:soc_readable")
        assert len(result) == 1
        assert result[0] is dev

    def test_no_extra_traits(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={"heartbeat": MagicMock()})
        reg.register_with_capabilities(dev)

        traits = reg.get_traits("d1")
        assert traits == {"cap:heartbeat"}

    def test_no_capabilities(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={})
        reg.register_with_capabilities(dev, extra_traits=["pcs"])

        traits = reg.get_traits("d1")
        assert traits == {"pcs"}

    def test_metadata_passed_through(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={"measurable": MagicMock()})
        reg.register_with_capabilities(dev, metadata={"rated_p": 100})

        assert reg.get_metadata("d1") == {"rated_p": 100}

    def test_duplicate_raises(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={"heartbeat": MagicMock()})
        reg.register_with_capabilities(dev)

        with pytest.raises(ValueError, match="already registered"):
            reg.register_with_capabilities(dev)

    def test_extra_traits_before_auto_traits(self):
        """Extra traits appear before auto-generated capability traits in the trait list."""
        reg = DeviceRegistry()
        dev = _make_device("d1", capabilities={"active_power_control": MagicMock()})
        reg.register_with_capabilities(dev, extra_traits=["pcs", "inverter"])

        # All traits should be present
        traits = reg.get_traits("d1")
        assert traits == {"pcs", "inverter", "cap:active_power_control"}
