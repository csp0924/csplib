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


# ======================== _build_metadata (auto inject used_unit_ids) ========================


class _RealDevice:
    """非 MagicMock 的最小 DeviceProtocol stand-in，可指定（或不指定）used_unit_ids。"""

    def __init__(self, device_id: str, *, used_unit_ids=None) -> None:
        self.device_id = device_id
        self.is_responsive = True
        if used_unit_ids is not None:
            self.used_unit_ids = used_unit_ids

    def has_capability(self, _capability) -> bool:
        return False


class TestBuildMetadataAutoInjectUsedUnitIds:
    """UnifiedDeviceManager._build_metadata auto-inject used_unit_ids 行為測試。"""

    def test_device_with_frozenset_used_unit_ids_injected_as_sorted_list(self) -> None:
        """device.used_unit_ids 是 frozenset → metadata 含 sorted list。"""
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        device = _RealDevice("pcs_fs", used_unit_ids=frozenset({3, 1, 2}))

        manager.register(device)

        meta = registry.get_metadata("pcs_fs")
        assert meta["used_unit_ids"] == [1, 2, 3]

    def test_device_with_set_used_unit_ids_injected(self) -> None:
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        device = _RealDevice("pcs_set", used_unit_ids={5, 4})

        manager.register(device)

        meta = registry.get_metadata("pcs_set")
        assert meta["used_unit_ids"] == [4, 5]

    def test_device_with_list_used_unit_ids_injected_sorted(self) -> None:
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        device = _RealDevice("pcs_list", used_unit_ids=[10, 1, 7])

        manager.register(device)

        assert registry.get_metadata("pcs_list")["used_unit_ids"] == [1, 7, 10]

    def test_device_without_used_unit_ids_not_injected(self, mock_device_protocol) -> None:
        """MockDeviceProtocol 預設不設 used_unit_ids → metadata 不含該 key。"""
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)

        assert not hasattr(mock_device_protocol, "used_unit_ids")
        manager.register(mock_device_protocol)

        meta = registry.get_metadata(mock_device_protocol.device_id)
        assert "used_unit_ids" not in meta

    def test_magicmock_device_auto_attr_is_skipped_by_isinstance_guard(self) -> None:
        """MagicMock 物件會自動產生 .used_unit_ids（MagicMock 實例），
        isinstance guard 應讓 metadata 不包含該 key（避免序列化失敗）。"""
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        device = _make_mock_device("mm_dev")  # MagicMock device

        manager.register(device)

        meta = registry.get_metadata("mm_dev")
        assert "used_unit_ids" not in meta

    def test_user_metadata_overrides_auto_used_unit_ids(self) -> None:
        """user 提供的 metadata['used_unit_ids'] 應覆蓋 auto 值。"""
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        device = _RealDevice("pcs_override", used_unit_ids=frozenset({1, 2, 3}))

        manager.register(device, metadata={"used_unit_ids": ["custom"]})

        meta = registry.get_metadata("pcs_override")
        assert meta["used_unit_ids"] == ["custom"]

    def test_user_metadata_none_keeps_auto_only(self) -> None:
        """user metadata 為 None 時，metadata 僅含 auto 值（若 device 有該屬性）。"""
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)
        device = _RealDevice("pcs_auto_only", used_unit_ids=frozenset({7, 8}))

        manager.register(device, metadata=None)

        meta = registry.get_metadata("pcs_auto_only")
        assert meta == {"used_unit_ids": [7, 8]}

    def test_register_group_auto_injects_used_unit_ids_per_device(self) -> None:
        """register_group 也應對每個 device 自動注入。"""
        registry = DeviceRegistry()
        config = UnifiedConfig(device_registry=registry)
        manager = UnifiedDeviceManager(config)

        d1 = _RealDevice("grp_a", used_unit_ids=frozenset({1}))
        d2 = _RealDevice("grp_b", used_unit_ids=frozenset({2, 3}))

        manager.register_group([d1, d2])

        assert registry.get_metadata("grp_a") == {"used_unit_ids": [1]}
        assert registry.get_metadata("grp_b") == {"used_unit_ids": [2, 3]}
