"""Tests for DistributedController."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system import ModePriority
from csp_lib.integration.distributed.config import DistributedConfig, RemoteSiteConfig
from csp_lib.integration.distributed.controller import DistributedController
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping, ContextMapping
from csp_lib.integration.system_controller import SystemController, SystemControllerConfig


class MockStrategy(Strategy):
    def __init__(self, return_command: Command | None = None):
        self._return_command = return_command or Command()
        self.execute_count = 0
        self.activated = False

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.TRIGGERED, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        return self._return_command

    async def on_activate(self) -> None:
        self.activated = True

    async def on_deactivate(self) -> None:
        pass


def _make_config() -> DistributedConfig:
    return DistributedConfig(
        sites=[
            RemoteSiteConfig(site_id="s1", device_ids=["d1"]),
        ],
        trait_device_map={"inverter": ["d1"]},
        poll_interval=0.1,
    )


def _make_system_controller(
    context_mappings: list[ContextMapping] | None = None,
    command_mappings: list[CommandMapping] | None = None,
) -> SystemController:
    reg = DeviceRegistry()
    sc_config = SystemControllerConfig(
        context_mappings=context_mappings or [],
        command_mappings=command_mappings or [],
    )
    return SystemController(reg, sc_config)


class TestDistributedControllerInit:
    def test_basic_init(self):
        config = _make_config()
        sc = _make_system_controller()
        redis = MagicMock()
        ctrl = DistributedController(config, sc, redis)

        assert ctrl.system_controller is sc
        assert ctrl.subscriber is None
        assert ctrl.remote_router is None
        assert ctrl.is_running is False


class TestDistributedControllerModeManagement:
    def test_register_mode(self):
        config = _make_config()
        sc = _make_system_controller()
        redis = MagicMock()
        ctrl = DistributedController(config, sc, redis)

        strategy = MockStrategy()
        ctrl.register_mode("pq", strategy, ModePriority.SCHEDULE, "PQ mode")

        assert "pq" in sc.mode_manager.registered_modes

    @pytest.mark.asyncio
    async def test_set_base_mode(self):
        config = _make_config()
        sc = _make_system_controller()
        redis = MagicMock()
        ctrl = DistributedController(config, sc, redis)

        strategy = MockStrategy()
        ctrl.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await ctrl.set_base_mode("pq")

        assert sc.mode_manager.effective_mode is not None
        assert sc.mode_manager.effective_mode.name == "pq"


class TestDistributedControllerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        config = _make_config()
        sc = _make_system_controller()
        redis = MagicMock()
        # Mock redis methods for subscriber
        redis.hgetall = AsyncMock(return_value={})
        redis.get = AsyncMock(return_value=None)
        redis.smembers = AsyncMock(return_value=set())

        ctrl = DistributedController(config, sc, redis)

        strategy = MockStrategy(Command(p_target=10.0))
        ctrl.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await ctrl.set_base_mode("pq")

        await ctrl.start()
        # Let executor task start running (it clears stop_event on startup)
        await asyncio.sleep(0.05)
        assert ctrl.subscriber is not None
        assert ctrl.remote_router is not None
        assert ctrl.is_running is True

        await ctrl.stop()
        assert ctrl.subscriber is None
        assert ctrl.remote_router is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        config = _make_config()
        sc = _make_system_controller()
        redis = MagicMock()
        redis.hgetall = AsyncMock(return_value={})
        redis.get = AsyncMock(return_value=None)
        redis.smembers = AsyncMock(return_value=set())

        ctrl = DistributedController(config, sc, redis)

        async with ctrl:
            # Let executor task start running
            await asyncio.sleep(0.05)
            assert ctrl.subscriber is not None

        assert ctrl.subscriber is None


class TestDistributedControllerBuildContext:
    def test_build_context_injects_system_alarm_when_offline(self):
        config = _make_config()
        sc = _make_system_controller()
        redis = MagicMock()
        ctrl = DistributedController(config, sc, redis)

        # Manually set up subscriber with offline device
        from csp_lib.integration.distributed.subscriber import DeviceStateSubscriber

        sub = DeviceStateSubscriber(config, redis)
        sub._device_online = {"d1": False}
        ctrl._subscriber = sub

        from csp_lib.cluster.context import VirtualContextBuilder

        ctrl._virtual_builder = VirtualContextBuilder(
            subscriber=sub, mappings=[], trait_device_map={}
        )

        ctx = ctrl._build_context()
        assert ctx.extra.get("system_alarm") is True

    def test_build_context_no_alarm_when_online(self):
        config = _make_config()
        sc = _make_system_controller()
        redis = MagicMock()
        ctrl = DistributedController(config, sc, redis)

        from csp_lib.integration.distributed.subscriber import DeviceStateSubscriber

        sub = DeviceStateSubscriber(config, redis)
        sub._device_online = {"d1": True}
        ctrl._subscriber = sub

        from csp_lib.cluster.context import VirtualContextBuilder

        ctrl._virtual_builder = VirtualContextBuilder(
            subscriber=sub, mappings=[], trait_device_map={}
        )

        ctx = ctrl._build_context()
        assert ctx.extra.get("system_alarm") is False

    def test_build_context_without_builder_returns_default(self):
        config = _make_config()
        sc = _make_system_controller()
        redis = MagicMock()
        ctrl = DistributedController(config, sc, redis)

        ctx = ctrl._build_context()
        assert isinstance(ctx, StrategyContext)


class TestDistributedControllerOnCommand:
    @pytest.mark.asyncio
    async def test_on_command_routes_via_remote_router(self):
        config = _make_config()
        sc = _make_system_controller(
            command_mappings=[CommandMapping(command_field="p_target", point_name="sp", device_id="d1")],
        )
        redis = MagicMock()
        redis.publish = AsyncMock(return_value=1)
        redis.hgetall = AsyncMock(return_value={})
        redis.get = AsyncMock(return_value="1")
        redis.smembers = AsyncMock(return_value=set())

        ctrl = DistributedController(config, sc, redis)

        # Manually set up components
        from csp_lib.integration.distributed.command_router import RemoteCommandRouter
        from csp_lib.integration.distributed.subscriber import DeviceStateSubscriber

        sub = DeviceStateSubscriber(config, redis)
        sub._device_online = {"d1": True}
        sub._device_alarms = {"d1": set()}
        ctrl._subscriber = sub

        from csp_lib.cluster.context import VirtualContextBuilder

        ctrl._virtual_builder = VirtualContextBuilder(subscriber=sub, mappings=[], trait_device_map={})

        ctrl._remote_router = RemoteCommandRouter(
            config=config,
            redis_client=redis,
            subscriber=sub,
            mappings=sc.config.command_mappings,
        )

        cmd = Command(p_target=50.0)
        await ctrl._on_command(cmd)

        redis.publish.assert_called_once()
