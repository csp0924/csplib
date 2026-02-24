"""Tests for Capability and CapabilityBinding."""

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.equipment.device.capability import (
    ACTIVE_POWER_CONTROL,
    HEARTBEAT,
    LOAD_SHEDDABLE,
    MEASURABLE,
    SWITCHABLE,
    Capability,
    CapabilityBinding,
)


class TestCapability:
    def test_basic_capability(self):
        cap = Capability(name="test", write_slots=("w1",), read_slots=("r1",))
        assert cap.name == "test"
        assert cap.write_slots == ("w1",)
        assert cap.read_slots == ("r1",)
        assert cap.all_slots == frozenset({"w1", "r1"})

    def test_empty_slots(self):
        cap = Capability(name="empty")
        assert cap.all_slots == frozenset()

    def test_standard_heartbeat(self):
        assert HEARTBEAT.name == "heartbeat"
        assert HEARTBEAT.write_slots == ("heartbeat",)
        assert HEARTBEAT.read_slots == ()

    def test_standard_active_power_control(self):
        assert ACTIVE_POWER_CONTROL.write_slots == ("p_setpoint",)
        assert ACTIVE_POWER_CONTROL.read_slots == ("p_measurement",)

    def test_frozen(self):
        with pytest.raises(AttributeError):
            HEARTBEAT.name = "changed"  # type: ignore[misc]


class TestCapabilityBinding:
    def test_basic_binding(self):
        binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"})
        assert binding.resolve("heartbeat") == "watchdog"

    def test_different_point_names(self):
        """Same capability, different device point names."""
        b1 = CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"})
        b2 = CapabilityBinding(HEARTBEAT, {"heartbeat": "hb_reg"})
        b3 = CapabilityBinding(HEARTBEAT, {"heartbeat": "heartbeat_wr"})

        assert b1.resolve("heartbeat") == "watchdog"
        assert b2.resolve("heartbeat") == "hb_reg"
        assert b3.resolve("heartbeat") == "heartbeat_wr"

    def test_multi_slot_binding(self):
        binding = CapabilityBinding(
            ACTIVE_POWER_CONTROL,
            {"p_setpoint": "p_set", "p_measurement": "active_power"},
        )
        assert binding.resolve("p_setpoint") == "p_set"
        assert binding.resolve("p_measurement") == "active_power"

    def test_missing_slot_raises(self):
        """Missing a required slot."""
        with pytest.raises(ConfigurationError, match="missing slots"):
            CapabilityBinding(ACTIVE_POWER_CONTROL, {"p_setpoint": "p_set"})
            # missing p_measurement

    def test_extra_slot_raises(self):
        """Extra slot that doesn't exist in capability."""
        with pytest.raises(ConfigurationError, match="unknown slots"):
            CapabilityBinding(HEARTBEAT, {"heartbeat": "hb", "extra": "nope"})

    def test_resolve_nonexistent_slot_raises(self):
        binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "hb"})
        with pytest.raises(KeyError):
            binding.resolve("nonexistent")

    def test_load_sheddable_binding(self):
        """LOAD_SHEDDABLE has both read and write slots."""
        binding = CapabilityBinding(
            LOAD_SHEDDABLE,
            {
                "switch_cmd": "breaker_ctrl",
                "active_power": "load_kw",
                "switch_status": "breaker_fb",
            },
        )
        assert binding.resolve("switch_cmd") == "breaker_ctrl"
        assert binding.resolve("active_power") == "load_kw"
        assert binding.resolve("switch_status") == "breaker_fb"


class TestCapabilityOnDevice:
    """Test capability methods on AsyncModbusDevice using mocks."""

    def _make_device(self, bindings=()):
        from unittest.mock import AsyncMock, MagicMock

        from csp_lib.equipment.device.base import AsyncModbusDevice
        from csp_lib.equipment.device.config import DeviceConfig

        config = DeviceConfig(device_id="test_01")
        client = MagicMock()
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        return AsyncModbusDevice(config=config, client=client, capability_bindings=bindings)

    def test_has_capability(self):
        binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"})
        dev = self._make_device(bindings=[binding])
        assert dev.has_capability(HEARTBEAT) is True
        assert dev.has_capability("heartbeat") is True
        assert dev.has_capability(SWITCHABLE) is False
        assert dev.has_capability("switchable") is False

    def test_resolve_point(self):
        binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"})
        dev = self._make_device(bindings=[binding])
        assert dev.resolve_point(HEARTBEAT, "heartbeat") == "watchdog"
        assert dev.resolve_point("heartbeat", "heartbeat") == "watchdog"

    def test_resolve_point_missing_capability_raises(self):
        dev = self._make_device()
        with pytest.raises(ConfigurationError, match="has no capability"):
            dev.resolve_point(HEARTBEAT, "heartbeat")

    def test_get_binding(self):
        binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "hb"})
        dev = self._make_device(bindings=[binding])
        assert dev.get_binding(HEARTBEAT) is binding
        assert dev.get_binding(SWITCHABLE) is None

    def test_capabilities_property(self):
        b1 = CapabilityBinding(HEARTBEAT, {"heartbeat": "hb"})
        b2 = CapabilityBinding(MEASURABLE, {"active_power": "p_out"})
        dev = self._make_device(bindings=[b1, b2])
        caps = dev.capabilities
        assert "heartbeat" in caps
        assert "measurable" in caps
        assert len(caps) == 2

    def test_add_capability_at_runtime(self):
        dev = self._make_device()
        assert dev.has_capability(HEARTBEAT) is False

        binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"})
        dev.add_capability(binding)
        assert dev.has_capability(HEARTBEAT) is True
        assert dev.resolve_point(HEARTBEAT, "heartbeat") == "watchdog"

    def test_remove_capability_at_runtime(self):
        binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "hb"})
        dev = self._make_device(bindings=[binding])
        assert dev.has_capability(HEARTBEAT) is True

        dev.remove_capability(HEARTBEAT)
        assert dev.has_capability(HEARTBEAT) is False

    def test_remove_nonexistent_capability_is_noop(self):
        dev = self._make_device()
        dev.remove_capability(HEARTBEAT)  # should not raise

    def test_add_capability_replaces_existing(self):
        b1 = CapabilityBinding(HEARTBEAT, {"heartbeat": "old_point"})
        dev = self._make_device(bindings=[b1])
        assert dev.resolve_point(HEARTBEAT, "heartbeat") == "old_point"

        b2 = CapabilityBinding(HEARTBEAT, {"heartbeat": "new_point"})
        dev.add_capability(b2)
        assert dev.resolve_point(HEARTBEAT, "heartbeat") == "new_point"
