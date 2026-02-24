"""Tests for Capability integration with EquipmentTemplate and DeviceRegistry."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.equipment.device.capability import (
    ACTIVE_POWER_CONTROL,
    HEARTBEAT,
    MEASURABLE,
    SWITCHABLE,
    CapabilityBinding,
)


class TestEquipmentTemplateValidation:
    def _make_read_point(self, name, address=0):
        from csp_lib.equipment.core.point import ReadPoint
        from csp_lib.modbus.types import UInt16

        return ReadPoint(name=name, address=address, data_type=UInt16())

    def _make_write_point(self, name, address=0):
        from csp_lib.equipment.core.point import WritePoint
        from csp_lib.modbus.types import UInt16

        return WritePoint(name=name, address=address, data_type=UInt16())

    def test_valid_template_with_capabilities(self):
        from csp_lib.equipment.template import EquipmentTemplate

        template = EquipmentTemplate(
            model="TestPCS",
            always_points=(self._make_read_point("active_power"),),
            write_points=(
                self._make_write_point("p_set"),
                self._make_write_point("watchdog"),
            ),
            capability_bindings=(
                CapabilityBinding(ACTIVE_POWER_CONTROL, {"p_setpoint": "p_set", "p_measurement": "active_power"}),
                CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"}),
            ),
        )
        assert len(template.capability_bindings) == 2

    def test_missing_write_point_raises(self):
        from csp_lib.equipment.template import EquipmentTemplate

        with pytest.raises(ConfigurationError, match="write point 'p_set' which does not exist"):
            EquipmentTemplate(
                model="BadPCS",
                always_points=(self._make_read_point("active_power"),),
                write_points=(),  # missing p_set!
                capability_bindings=(
                    CapabilityBinding(
                        ACTIVE_POWER_CONTROL, {"p_setpoint": "p_set", "p_measurement": "active_power"}
                    ),
                ),
            )

    def test_missing_read_point_raises(self):
        from csp_lib.equipment.template import EquipmentTemplate

        with pytest.raises(ConfigurationError, match="read point 'active_power' which does not exist"):
            EquipmentTemplate(
                model="BadPCS",
                always_points=(),  # missing active_power!
                write_points=(self._make_write_point("p_set"),),
                capability_bindings=(
                    CapabilityBinding(
                        ACTIVE_POWER_CONTROL, {"p_setpoint": "p_set", "p_measurement": "active_power"}
                    ),
                ),
            )

    def test_rotating_points_count_as_read(self):
        """Read points in rotating groups should also satisfy capability checks."""
        from csp_lib.equipment.template import EquipmentTemplate

        template = EquipmentTemplate(
            model="TestMeter",
            rotating_points=((self._make_read_point("active_power"),),),
            capability_bindings=(CapabilityBinding(MEASURABLE, {"active_power": "active_power"}),),
        )
        assert len(template.capability_bindings) == 1

    def test_no_capabilities_is_valid(self):
        from csp_lib.equipment.template import EquipmentTemplate

        template = EquipmentTemplate(model="Basic")
        assert len(template.capability_bindings) == 0

    def test_different_devices_different_point_names(self):
        """The core use case: same capability, different point names per device model."""
        from csp_lib.equipment.template import EquipmentTemplate

        sungrow = EquipmentTemplate(
            model="Sungrow-SG110CX",
            write_points=(self._make_write_point("watchdog"),),
            capability_bindings=(CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"}),),
        )

        huawei = EquipmentTemplate(
            model="Huawei-SUN2000",
            write_points=(self._make_write_point("hb_reg"),),
            capability_bindings=(CapabilityBinding(HEARTBEAT, {"heartbeat": "hb_reg"}),),
        )

        # Both declare HEARTBEAT, but map to different point names
        assert sungrow.capability_bindings[0].resolve("heartbeat") == "watchdog"
        assert huawei.capability_bindings[0].resolve("heartbeat") == "hb_reg"


class TestDeviceRegistryCapabilityQuery:
    def _make_device(self, device_id, capabilities=(), responsive=True):
        dev = MagicMock()
        type(dev).device_id = PropertyMock(return_value=device_id)
        type(dev).is_responsive = PropertyMock(return_value=responsive)
        cap_bindings = {b.capability.name: b for b in capabilities}
        dev.has_capability = lambda c: (c.name if hasattr(c, "name") else c) in cap_bindings
        dev.resolve_point = lambda c, s: cap_bindings[c.name if hasattr(c, "name") else c].resolve(s)
        dev.write = AsyncMock()
        return dev

    def test_get_devices_with_capability(self):
        from csp_lib.integration.registry import DeviceRegistry

        hb_binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "hb"})
        sw_binding = CapabilityBinding(SWITCHABLE, {"switch_cmd": "sw", "switch_status": "sw_fb"})

        dev1 = self._make_device("pcs_01", capabilities=[hb_binding])
        dev2 = self._make_device("pcs_02", capabilities=[hb_binding, sw_binding])
        dev3 = self._make_device("meter_01", capabilities=[])

        reg = DeviceRegistry()
        reg.register(dev1, traits=["pcs"])
        reg.register(dev2, traits=["pcs"])
        reg.register(dev3, traits=["meter"])

        hb_devices = reg.get_devices_with_capability(HEARTBEAT)
        assert [d.device_id for d in hb_devices] == ["pcs_01", "pcs_02"]

        sw_devices = reg.get_devices_with_capability(SWITCHABLE)
        assert [d.device_id for d in sw_devices] == ["pcs_02"]

        meter_devices = reg.get_devices_with_capability(MEASURABLE)
        assert meter_devices == []

    def test_get_responsive_devices_with_capability(self):
        from csp_lib.integration.registry import DeviceRegistry

        hb_binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "hb"})

        dev1 = self._make_device("pcs_01", capabilities=[hb_binding], responsive=True)
        dev2 = self._make_device("pcs_02", capabilities=[hb_binding], responsive=False)

        reg = DeviceRegistry()
        reg.register(dev1, traits=["pcs"])
        reg.register(dev2, traits=["pcs"])

        responsive = reg.get_responsive_devices_with_capability(HEARTBEAT)
        assert [d.device_id for d in responsive] == ["pcs_01"]

    def test_query_by_string_name(self):
        from csp_lib.integration.registry import DeviceRegistry

        hb_binding = CapabilityBinding(HEARTBEAT, {"heartbeat": "hb"})
        dev = self._make_device("pcs_01", capabilities=[hb_binding])

        reg = DeviceRegistry()
        reg.register(dev)

        assert len(reg.get_devices_with_capability("heartbeat")) == 1


class TestHeartbeatServiceCapabilityMode:
    """Test HeartbeatService with use_capability=True."""

    def _make_device(self, device_id, hb_point="heartbeat", responsive=True):
        dev = MagicMock()
        type(dev).device_id = PropertyMock(return_value=device_id)
        type(dev).is_responsive = PropertyMock(return_value=responsive)

        hb_binding = CapabilityBinding(HEARTBEAT, {"heartbeat": hb_point})
        cap_bindings = {HEARTBEAT.name: hb_binding}
        dev.has_capability = lambda c: (c.name if hasattr(c, "name") else c) in cap_bindings
        dev.resolve_point = lambda c, s: cap_bindings[c.name if hasattr(c, "name") else c].resolve(s)
        dev.write = AsyncMock()
        return dev

    @pytest.mark.asyncio
    async def test_auto_discovers_heartbeat_capable_devices(self):
        import asyncio

        from csp_lib.integration.heartbeat import HeartbeatService
        from csp_lib.integration.registry import DeviceRegistry

        dev1 = self._make_device("pcs_01", hb_point="watchdog")
        dev2 = self._make_device("pcs_02", hb_point="hb_reg")

        reg = DeviceRegistry()
        reg.register(dev1, traits=["pcs"])
        reg.register(dev2, traits=["pcs"])

        svc = HeartbeatService(reg, use_capability=True, interval=0.05)
        await svc.start()
        await asyncio.sleep(0.12)
        await svc.stop()

        # Each device should have been written with its OWN point name
        dev1.write.assert_any_call("watchdog", 1)
        dev2.write.assert_any_call("hb_reg", 1)

    @pytest.mark.asyncio
    async def test_skips_non_capable_devices(self):
        import asyncio

        from csp_lib.integration.heartbeat import HeartbeatService
        from csp_lib.integration.registry import DeviceRegistry

        # Device without heartbeat capability
        dev = MagicMock()
        type(dev).device_id = PropertyMock(return_value="meter_01")
        type(dev).is_responsive = PropertyMock(return_value=True)
        dev.has_capability = lambda c: False
        dev.write = AsyncMock()

        reg = DeviceRegistry()
        reg.register(dev, traits=["meter"])

        svc = HeartbeatService(reg, use_capability=True, interval=0.05)
        await svc.start()
        await asyncio.sleep(0.12)
        await svc.stop()

        dev.write.assert_not_called()
