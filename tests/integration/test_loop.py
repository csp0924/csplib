"""Tests for GridControlLoop."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext, SystemBase
from csp_lib.integration.loop import GridControlLoop, GridControlLoopConfig
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping, ContextMapping, DataFeedMapping


def _make_device(
    device_id: str, values: dict | None = None, responsive: bool = True, protected: bool = False
) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).latest_values = PropertyMock(return_value=values or {})
    dev.write = AsyncMock()
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)
    return dev


class MockStrategy(Strategy):
    def __init__(self, return_command: Command | None = None, mode: ExecutionMode = ExecutionMode.PERIODIC):
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


class TestGridControlLoopInit:
    def test_basic_init(self):
        reg = DeviceRegistry()
        config = GridControlLoopConfig()
        loop = GridControlLoop(reg, config)
        assert loop.registry is reg
        assert loop.pv_service is None
        assert loop.is_running is False

    def test_init_with_data_feed(self):
        reg = DeviceRegistry()
        config = GridControlLoopConfig(
            data_feed_mapping=DataFeedMapping(point_name="pv_power", device_id="meter1"),
            pv_max_history=100,
        )
        loop = GridControlLoop(reg, config)
        assert loop.pv_service is not None
        assert loop.pv_service.max_history == 100

    def test_init_with_system_base(self):
        reg = DeviceRegistry()
        sb = SystemBase(p_base=2000, q_base=1000)
        config = GridControlLoopConfig(system_base=sb)
        loop = GridControlLoop(reg, config)
        # system_base is passed through to context builder; verified via build()
        ctx = loop._context_builder.build()
        assert ctx.system_base is sb


class TestGridControlLoopSetStrategy:
    @pytest.mark.asyncio
    async def test_set_strategy(self):
        reg = DeviceRegistry()
        loop = GridControlLoop(reg, GridControlLoopConfig())
        strategy = MockStrategy()
        await loop.set_strategy(strategy)
        assert loop.executor.current_strategy is strategy
        assert strategy.activated is True

    @pytest.mark.asyncio
    async def test_set_strategy_none(self):
        reg = DeviceRegistry()
        loop = GridControlLoop(reg, GridControlLoopConfig())
        strategy = MockStrategy()
        await loop.set_strategy(strategy)
        await loop.set_strategy(None)
        assert strategy.deactivated is True
        assert loop.executor.current_strategy is None


class TestGridControlLoopLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        reg = DeviceRegistry()
        dev = _make_device("d1", {"soc": 80.0})
        reg.register(dev)

        config = GridControlLoopConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="d1")],
        )
        loop = GridControlLoop(reg, config)

        strategy = MockStrategy(
            return_command=Command(p_target=500.0),
            mode=ExecutionMode.TRIGGERED,
        )
        await loop.set_strategy(strategy)

        async with asyncio.timeout(5):
            await loop.start()
            assert loop.is_running is True
            loop.trigger()
            await asyncio.sleep(0.05)
            await loop.stop()

        assert loop.is_running is False

    @pytest.mark.asyncio
    async def test_context_manager(self):
        reg = DeviceRegistry()
        loop = GridControlLoop(reg, GridControlLoopConfig())

        async with asyncio.timeout(5):
            await loop.start()
            assert loop.is_running is True
            await loop.stop()

        assert loop.is_running is False

    @pytest.mark.asyncio
    async def test_data_feed_attach_detach(self):
        reg = DeviceRegistry()
        dev = _make_device("meter1")
        reg.register(dev)

        config = GridControlLoopConfig(
            data_feed_mapping=DataFeedMapping(point_name="pv_power", device_id="meter1"),
        )
        loop = GridControlLoop(reg, config)

        async with asyncio.timeout(5):
            await loop.start()
            dev.on.assert_called_once()
            await loop.stop()

    @pytest.mark.asyncio
    async def test_trigger(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        config = GridControlLoopConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )
        loop = GridControlLoop(reg, config)

        strategy = MockStrategy(
            return_command=Command(p_target=100.0),
            mode=ExecutionMode.TRIGGERED,
        )
        await loop.set_strategy(strategy)

        async with asyncio.timeout(5):
            await loop.start()
            loop.trigger()
            await asyncio.sleep(0.1)
            assert strategy.execute_count >= 1
            await loop.stop()

    @pytest.mark.asyncio
    async def test_full_round_trip(self):
        """Test context build → strategy execute → command route."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 80.0})
        reg.register(dev)

        config = GridControlLoopConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
        )
        loop = GridControlLoop(reg, config)

        strategy = MockStrategy(
            return_command=Command(p_target=1000.0),
            mode=ExecutionMode.TRIGGERED,
        )
        await loop.set_strategy(strategy)

        async with asyncio.timeout(5):
            await loop.start()
            loop.trigger()
            await asyncio.sleep(0.1)
            await loop.stop()

        dev.write.assert_awaited_with("p_set", 1000.0)
