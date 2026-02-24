"""Tests for GroupControllerManager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system import ModePriority
from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.integration.group_controller import GroupControllerManager, GroupDefinition
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping, ContextMapping
from csp_lib.integration.system_controller import SystemControllerConfig


def _make_device(
    device_id: str,
    values: dict | None = None,
    responsive: bool = True,
    protected: bool = False,
    connected: bool = True,
) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=connected)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=connected and responsive and not protected)
    type(dev).latest_values = PropertyMock(return_value=values or {})
    type(dev).active_alarms = PropertyMock(return_value=[])
    dev.write = AsyncMock()
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)

    def _health():
        if connected and responsive and not protected:
            status = HealthStatus.HEALTHY
        elif connected:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY
        return HealthReport(
            status=status,
            component=f"device:{device_id}",
            details={"connected": connected, "responsive": responsive, "protected": protected, "active_alarms": 0},
        )

    dev.health = _health
    return dev


class MockStrategy(Strategy):
    def __init__(self, return_command: Command | None = None, mode: ExecutionMode = ExecutionMode.TRIGGERED):
        self._return_command = return_command or Command()
        self._mode = mode
        self.execute_count = 0
        self.activated = False
        self.deactivated = False

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        return self._return_command

    async def on_activate(self) -> None:
        self.activated = True

    async def on_deactivate(self) -> None:
        self.deactivated = True


def _make_registry_with_devices(*device_ids: str, traits: dict[str, list[str]] | None = None) -> DeviceRegistry:
    """Helper: create a registry with mock devices."""
    reg = DeviceRegistry()
    traits = traits or {}
    for did in device_ids:
        dev = _make_device(did)
        reg.register(dev, traits.get(did))
    return reg


def _make_two_group_manager(
    registry: DeviceRegistry | None = None,
    config1: SystemControllerConfig | None = None,
    config2: SystemControllerConfig | None = None,
) -> GroupControllerManager:
    """Helper: create a manager with two groups (pcs_1+bess_1, pcs_2+bess_2)."""
    if registry is None:
        registry = _make_registry_with_devices(
            "pcs_1",
            "bess_1",
            "pcs_2",
            "bess_2",
            traits={"pcs_1": ["pcs"], "bess_1": ["bess"], "pcs_2": ["pcs"], "bess_2": ["bess"]},
        )
    return GroupControllerManager(
        registry=registry,
        groups=[
            GroupDefinition(
                group_id="group1",
                device_ids=["pcs_1", "bess_1"],
                config=config1 or SystemControllerConfig(auto_stop_on_alarm=False),
            ),
            GroupDefinition(
                group_id="group2",
                device_ids=["pcs_2", "bess_2"],
                config=config2 or SystemControllerConfig(auto_stop_on_alarm=False),
            ),
        ],
    )


# ============================================================
# Validation Tests
# ============================================================


class TestGroupControllerValidation:
    def test_empty_groups_raises(self):
        reg = DeviceRegistry()
        with pytest.raises(ValueError, match="At least one group"):
            GroupControllerManager(reg, groups=[])

    def test_duplicate_group_id_raises(self):
        reg = _make_registry_with_devices("pcs_1", "pcs_2")
        with pytest.raises(ValueError, match="Duplicate group_id"):
            GroupControllerManager(
                reg,
                groups=[
                    GroupDefinition("g1", ["pcs_1"], SystemControllerConfig()),
                    GroupDefinition("g1", ["pcs_2"], SystemControllerConfig()),
                ],
            )

    def test_cross_group_device_overlap_raises(self):
        reg = _make_registry_with_devices("pcs_1", "pcs_2")
        with pytest.raises(ValueError, match="pcs_1.*group1.*group2|pcs_1.*group2.*group1"):
            GroupControllerManager(
                reg,
                groups=[
                    GroupDefinition("group1", ["pcs_1"], SystemControllerConfig()),
                    GroupDefinition("group2", ["pcs_1", "pcs_2"], SystemControllerConfig()),
                ],
            )

    def test_unknown_device_raises(self):
        reg = _make_registry_with_devices("pcs_1")
        with pytest.raises(ValueError, match="not_exist.*not registered"):
            GroupControllerManager(
                reg,
                groups=[
                    GroupDefinition("g1", ["pcs_1", "not_exist"], SystemControllerConfig()),
                ],
            )

    def test_empty_device_list_raises(self):
        reg = _make_registry_with_devices("pcs_1")
        with pytest.raises(ValueError, match="no devices"):
            GroupControllerManager(
                reg,
                groups=[
                    GroupDefinition("g1", [], SystemControllerConfig()),
                ],
            )

    def test_valid_groups_accepted(self):
        mgr = _make_two_group_manager()
        assert len(mgr) == 2


# ============================================================
# Init & Query Tests
# ============================================================


class TestGroupControllerInitQuery:
    def test_controllers_created_per_group(self):
        mgr = _make_two_group_manager()
        assert mgr.group_ids == ["group1", "group2"]
        assert len(mgr) == 2
        assert "group1" in mgr
        assert "group2" in mgr
        assert "group3" not in mgr

    def test_sub_registry_contains_only_group_devices(self):
        mgr = _make_two_group_manager()
        ctrl1 = mgr.get_controller("group1")
        ctrl2 = mgr.get_controller("group2")

        assert "pcs_1" in ctrl1.registry
        assert "bess_1" in ctrl1.registry
        assert "pcs_2" not in ctrl1.registry

        assert "pcs_2" in ctrl2.registry
        assert "bess_2" in ctrl2.registry
        assert "pcs_1" not in ctrl2.registry

    def test_sub_registry_preserves_traits(self):
        mgr = _make_two_group_manager()
        ctrl1 = mgr.get_controller("group1")
        assert ctrl1.registry.get_traits("pcs_1") == {"pcs"}
        assert ctrl1.registry.get_traits("bess_1") == {"bess"}

    def test_get_controller_unknown_raises(self):
        mgr = _make_two_group_manager()
        with pytest.raises(KeyError, match="Unknown group_id"):
            mgr.get_controller("nonexistent")

    def test_controllers_property_returns_copy(self):
        mgr = _make_two_group_manager()
        controllers = mgr.controllers
        assert isinstance(controllers, dict)
        assert len(controllers) == 2
        # Modifying the returned dict should not affect the manager
        controllers["group3"] = MagicMock()
        assert "group3" not in mgr

    def test_iter_yields_sorted_pairs(self):
        mgr = _make_two_group_manager()
        pairs = list(mgr)
        assert len(pairs) == 2
        assert pairs[0][0] == "group1"
        assert pairs[1][0] == "group2"
        assert pairs[0][1] is mgr.get_controller("group1")
        assert pairs[1][1] is mgr.get_controller("group2")

    def test_sub_registry_shares_device_instances(self):
        registry = _make_registry_with_devices("pcs_1", "bess_1", "pcs_2", "bess_2")
        mgr = GroupControllerManager(
            registry=registry,
            groups=[
                GroupDefinition("group1", ["pcs_1", "bess_1"], SystemControllerConfig()),
                GroupDefinition("group2", ["pcs_2", "bess_2"], SystemControllerConfig()),
            ],
        )
        # Same device instance, not a copy
        assert mgr.get_controller("group1").registry.get_device("pcs_1") is registry.get_device("pcs_1")


# ============================================================
# Mode Management Tests
# ============================================================


class TestGroupControllerModeManagement:
    @pytest.mark.asyncio
    async def test_register_mode_per_group(self):
        mgr = _make_two_group_manager()
        s1 = MockStrategy(Command(p_target=100.0))
        s2 = MockStrategy(Command(p_target=200.0))

        mgr.register_mode("group1", "pq", s1, ModePriority.MANUAL)
        mgr.register_mode("group2", "pv", s2, ModePriority.MANUAL)

        await mgr.set_base_mode("group1", "pq")
        await mgr.set_base_mode("group2", "pv")

        assert mgr.effective_mode_name("group1") == "pq"
        assert mgr.effective_mode_name("group2") == "pv"

    @pytest.mark.asyncio
    async def test_set_base_mode_independent(self):
        mgr = _make_two_group_manager()
        s1 = MockStrategy()
        s2 = MockStrategy()

        mgr.register_mode("group1", "pq", s1, ModePriority.MANUAL)
        mgr.register_mode("group2", "pv", s2, ModePriority.MANUAL)

        await mgr.set_base_mode("group1", "pq")
        assert mgr.effective_mode_name("group1") == "pq"
        assert mgr.effective_mode_name("group2") is None

    @pytest.mark.asyncio
    async def test_push_pop_override_independent(self):
        mgr = _make_two_group_manager()
        s_base1 = MockStrategy(Command(p_target=100.0))
        s_base2 = MockStrategy(Command(p_target=200.0))
        s_override = MockStrategy(Command(p_target=0.0))

        mgr.register_mode("group1", "pq", s_base1, ModePriority.SCHEDULE)
        mgr.register_mode("group1", "stop", s_override, ModePriority.MANUAL)
        mgr.register_mode("group2", "pv", s_base2, ModePriority.SCHEDULE)

        await mgr.set_base_mode("group1", "pq")
        await mgr.set_base_mode("group2", "pv")

        # Push override on group1 only
        await mgr.push_override("group1", "stop")
        assert mgr.effective_mode_name("group1") == "stop"
        assert mgr.effective_mode_name("group2") == "pv"  # Unaffected

        # Pop override
        await mgr.pop_override("group1", "stop")
        assert mgr.effective_mode_name("group1") == "pq"

    @pytest.mark.asyncio
    async def test_delegation_unknown_group_raises_key_error(self):
        mgr = _make_two_group_manager()
        s = MockStrategy()

        with pytest.raises(KeyError):
            mgr.register_mode("bad_group", "pq", s, ModePriority.MANUAL)
        with pytest.raises(KeyError):
            await mgr.set_base_mode("bad_group", "pq")
        with pytest.raises(KeyError):
            await mgr.add_base_mode("bad_group", "pq")
        with pytest.raises(KeyError):
            await mgr.remove_base_mode("bad_group", "pq")
        with pytest.raises(KeyError):
            await mgr.push_override("bad_group", "pq")
        with pytest.raises(KeyError):
            await mgr.pop_override("bad_group", "pq")
        with pytest.raises(KeyError):
            mgr.trigger("bad_group")
        with pytest.raises(KeyError):
            mgr.effective_mode_name("bad_group")


# ============================================================
# Independence Tests
# ============================================================


class TestGroupControllerIndependence:
    @pytest.mark.asyncio
    async def test_independent_command_routing(self):
        """Group1 PQ(P=100) and Group2 PQ(P=200) → each PCS gets correct write value."""
        reg = DeviceRegistry()
        dev1 = _make_device("pcs_1", values={"soc": 50.0})
        dev2 = _make_device("pcs_2", values={"soc": 50.0})
        reg.register(dev1, ["pcs"])
        reg.register(dev2, ["pcs"])

        config1 = SystemControllerConfig(
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs_1")],
            auto_stop_on_alarm=False,
        )
        config2 = SystemControllerConfig(
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs_2")],
            auto_stop_on_alarm=False,
        )
        mgr = GroupControllerManager(
            registry=reg,
            groups=[
                GroupDefinition("group1", ["pcs_1"], config1),
                GroupDefinition("group2", ["pcs_2"], config2),
            ],
        )

        s1 = MockStrategy(Command(p_target=100.0))
        s2 = MockStrategy(Command(p_target=200.0))
        mgr.register_mode("group1", "pq", s1, ModePriority.SCHEDULE)
        mgr.register_mode("group2", "pq", s2, ModePriority.SCHEDULE)
        await mgr.set_base_mode("group1", "pq")
        await mgr.set_base_mode("group2", "pq")

        async with asyncio.timeout(5):
            await mgr.start()
            mgr.trigger_all()
            await asyncio.sleep(0.1)
            await mgr.stop()

        dev1.write.assert_awaited_with("p_set", 100.0)
        dev2.write.assert_awaited_with("p_set", 200.0)

    @pytest.mark.asyncio
    async def test_alarm_in_one_group_does_not_affect_other(self):
        """Alarm in group1 does not trigger auto-stop in group2."""
        reg = DeviceRegistry()
        dev1 = _make_device("pcs_1", values={"soc": 50.0}, protected=True)
        dev2 = _make_device("pcs_2", values={"soc": 50.0}, protected=False)
        reg.register(dev1, ["pcs"])
        reg.register(dev2, ["pcs"])

        config1 = SystemControllerConfig(
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs_1")],
            auto_stop_on_alarm=True,
        )
        config2 = SystemControllerConfig(
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs_2")],
            auto_stop_on_alarm=True,
        )
        mgr = GroupControllerManager(
            registry=reg,
            groups=[
                GroupDefinition("group1", ["pcs_1"], config1),
                GroupDefinition("group2", ["pcs_2"], config2),
            ],
        )

        s1 = MockStrategy(Command(p_target=500.0))
        s2 = MockStrategy(Command(p_target=300.0))
        mgr.register_mode("group1", "pq", s1, ModePriority.SCHEDULE)
        mgr.register_mode("group2", "pq", s2, ModePriority.SCHEDULE)
        await mgr.set_base_mode("group1", "pq")
        await mgr.set_base_mode("group2", "pq")

        async with asyncio.timeout(5):
            await mgr.start()
            mgr.trigger_all()
            await asyncio.sleep(0.1)
            await mgr.stop()

        # Group1 should have auto-stop active (pcs_1 is protected)
        ctrl1 = mgr.get_controller("group1")
        assert ctrl1.auto_stop_active is True

        # Group2 should NOT have auto-stop (pcs_2 is not protected)
        ctrl2 = mgr.get_controller("group2")
        assert ctrl2.auto_stop_active is False


# ============================================================
# Lifecycle Tests
# ============================================================


class TestGroupControllerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop_delegates_to_all(self):
        mgr = _make_two_group_manager()
        s1 = MockStrategy()
        s2 = MockStrategy()
        mgr.register_mode("group1", "pq", s1, ModePriority.SCHEDULE)
        mgr.register_mode("group2", "pv", s2, ModePriority.SCHEDULE)

        async with asyncio.timeout(5):
            await mgr.start()
            assert mgr.is_running is True
            assert mgr.get_controller("group1").is_running is True
            assert mgr.get_controller("group2").is_running is True

            await mgr.stop()

        assert mgr.is_running is False

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        mgr = _make_two_group_manager()

        async with asyncio.timeout(5):
            async with mgr:
                assert mgr.is_running is True
            assert mgr.is_running is False

    @pytest.mark.asyncio
    async def test_is_running_reflects_state(self):
        mgr = _make_two_group_manager()
        assert mgr.is_running is False


# ============================================================
# Health Tests
# ============================================================


class TestGroupControllerHealth:
    def test_all_healthy(self):
        reg = _make_registry_with_devices("pcs_1", "pcs_2")
        mgr = GroupControllerManager(
            registry=reg,
            groups=[
                GroupDefinition("group1", ["pcs_1"], SystemControllerConfig(auto_stop_on_alarm=False)),
                GroupDefinition("group2", ["pcs_2"], SystemControllerConfig(auto_stop_on_alarm=False)),
            ],
        )
        report = mgr.health()
        assert report.status == HealthStatus.HEALTHY
        assert report.component == "group_controller_manager"
        assert len(report.children) == 2

    def test_one_unhealthy(self):
        reg = DeviceRegistry()
        dev1 = _make_device("pcs_1", connected=True, responsive=True, protected=False)
        dev2 = _make_device("pcs_2", connected=False, responsive=False, protected=False)
        reg.register(dev1)
        reg.register(dev2)

        mgr = GroupControllerManager(
            registry=reg,
            groups=[
                GroupDefinition("group1", ["pcs_1"], SystemControllerConfig(auto_stop_on_alarm=False)),
                GroupDefinition("group2", ["pcs_2"], SystemControllerConfig(auto_stop_on_alarm=False)),
            ],
        )
        report = mgr.health()
        assert report.status == HealthStatus.UNHEALTHY

    def test_one_degraded(self):
        reg = DeviceRegistry()
        dev1 = _make_device("pcs_1", connected=True, responsive=True, protected=False)
        dev2 = _make_device("pcs_2", connected=True, responsive=True, protected=True)  # protected → degraded
        reg.register(dev1)
        reg.register(dev2)

        mgr = GroupControllerManager(
            registry=reg,
            groups=[
                GroupDefinition("group1", ["pcs_1"], SystemControllerConfig(auto_stop_on_alarm=False)),
                GroupDefinition("group2", ["pcs_2"], SystemControllerConfig(auto_stop_on_alarm=False)),
            ],
        )
        report = mgr.health()
        assert report.status == HealthStatus.DEGRADED

    def test_health_details_include_groups(self):
        mgr = _make_two_group_manager()
        report = mgr.health()
        assert "groups" in report.details
        assert report.details["groups"] == ["group1", "group2"]
