"""Tests for UnifiedDeviceManager ↔ DeviceRegistry integration."""

from __future__ import annotations

from unittest.mock import MagicMock

from csp_lib.integration.registry import DeviceRegistry
from csp_lib.manager.unified import UnifiedConfig, UnifiedDeviceManager


def _make_mock_device(device_id: str = "dev_01") -> MagicMock:
    """Create a mock AsyncModbusDevice with minimal interface."""
    device = MagicMock()
    device.device_id = device_id
    device.is_responsive = True
    device.has_capability = MagicMock(return_value=False)
    return device


class TestRegisterWithRegistry:
    """register() should auto-register to DeviceRegistry when configured."""

    def test_register_with_traits_registers_to_registry(self) -> None:
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        device = _make_mock_device("pcs_01")

        manager.register(device, traits=["pcs", "inverter"], metadata={"rated_p": 100})

        assert "pcs_01" in registry
        assert registry.get_traits("pcs_01") == {"pcs", "inverter"}
        assert registry.get_metadata("pcs_01") == {"rated_p": 100}

    def test_register_without_traits_registers_with_empty(self) -> None:
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        device = _make_mock_device("meter_01")

        manager.register(device)

        assert "meter_01" in registry
        assert registry.get_traits("meter_01") == set()
        assert registry.get_metadata("meter_01") == {}

    def test_register_without_registry_no_error(self) -> None:
        config = UnifiedConfig()  # device_registry is None
        manager = UnifiedDeviceManager(config)
        device = _make_mock_device("dev_01")

        # Should not raise
        manager.register(device, traits=["pcs"], metadata={"rated_p": 50})


class TestRegisterGroupWithRegistry:
    """register_group() should auto-register all devices to DeviceRegistry."""

    def test_register_group_with_traits(self) -> None:
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        devices = [_make_mock_device("rtu_01"), _make_mock_device("rtu_02")]

        manager.register_group(devices, traits=["rtu", "sensor"], metadata={"location": "site_a"})

        assert "rtu_01" in registry
        assert "rtu_02" in registry
        assert registry.get_traits("rtu_01") == {"rtu", "sensor"}
        assert registry.get_traits("rtu_02") == {"rtu", "sensor"}
        assert registry.get_metadata("rtu_01") == {"location": "site_a"}
        assert registry.get_metadata("rtu_02") == {"location": "site_a"}

    def test_register_group_without_registry_no_error(self) -> None:
        config = UnifiedConfig()
        manager = UnifiedDeviceManager(config)
        devices = [_make_mock_device("dev_01"), _make_mock_device("dev_02")]

        # Should not raise
        manager.register_group(devices, traits=["group_a"])


class TestRegistryQueryAfterRegister:
    """Verify DeviceRegistry queries work after registration through UnifiedDeviceManager."""

    def test_get_devices_by_trait(self) -> None:
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)

        dev1 = _make_mock_device("pcs_01")
        dev2 = _make_mock_device("pcs_02")
        dev3 = _make_mock_device("meter_01")

        manager.register(dev1, traits=["pcs"])
        manager.register(dev2, traits=["pcs"])
        manager.register(dev3, traits=["meter"])

        pcs_devices = registry.get_devices_by_trait("pcs")
        assert len(pcs_devices) == 2
        assert pcs_devices[0].device_id == "pcs_01"
        assert pcs_devices[1].device_id == "pcs_02"

        meter_devices = registry.get_devices_by_trait("meter")
        assert len(meter_devices) == 1
        assert meter_devices[0].device_id == "meter_01"
