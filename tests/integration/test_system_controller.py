"""Tests for SystemController."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system import ModePriority, SOCProtection, SOCProtectionConfig, SystemAlarmProtection
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping, ContextMapping
from csp_lib.integration.system_controller import SystemController, SystemControllerConfig


def _make_device(
    device_id: str,
    values: dict | None = None,
    responsive: bool = True,
    protected: bool = False,
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


class TestSystemControllerInit:
    def test_basic_init(self):
        reg = DeviceRegistry()
        config = SystemControllerConfig()
        sc = SystemController(reg, config)
        assert sc.registry is reg
        assert sc.pv_service is None
        assert sc.is_running is False
        assert sc.effective_mode_name is None
        assert sc.protection_status is None

    def test_init_with_protection_rules(self):
        reg = DeviceRegistry()
        rules = [SOCProtection(), SystemAlarmProtection()]
        config = SystemControllerConfig(protection_rules=rules)
        sc = SystemController(reg, config)
        assert len(sc.protection_guard.rules) == 2


class TestSystemControllerModeManagement:
    @pytest.mark.asyncio
    async def test_register_and_set_base_mode(self):
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig())
        strategy = MockStrategy()

        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        assert sc.effective_mode_name == "pq"
        assert sc.executor.current_strategy is strategy
        assert strategy.activated is True

    @pytest.mark.asyncio
    async def test_push_pop_override(self):
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig())
        s_base = MockStrategy(Command(p_target=100.0))
        s_override = MockStrategy(Command(p_target=0.0))

        sc.register_mode("pq", s_base, ModePriority.SCHEDULE)
        sc.register_mode("manual_stop", s_override, ModePriority.MANUAL)
        await sc.set_base_mode("pq")
        assert sc.executor.current_strategy is s_base

        await sc.push_override("manual_stop")
        assert sc.executor.current_strategy is s_override
        assert s_base.deactivated is True

        await sc.pop_override("manual_stop")
        assert sc.executor.current_strategy is s_base


class TestSystemControllerProtection:
    @pytest.mark.asyncio
    async def test_protection_applied_on_command(self):
        """保護規則在 command 發送前套用"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 96.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            protection_rules=[SOCProtection(SOCProtectionConfig(soc_high=95.0))],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        # 策略嘗試充電 P=-100，但 SOC=96% > 95% → clamp to 0
        strategy = MockStrategy(Command(p_target=-100.0, q_target=50.0))
        sc.register_mode("charge", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("charge")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        # 保護後 P=0, Q=50 (SOC protection only clamps P)
        dev.write.assert_awaited_with("p_set", 0.0)

    @pytest.mark.asyncio
    async def test_protection_status_tracked(self):
        """保護結果被追蹤"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            protection_rules=[SOCProtection()],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=100.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        # Normal SOC → no protection triggered
        status = sc.protection_status
        assert status is not None
        assert status.was_modified is False


class TestSystemControllerAutoStop:
    @pytest.mark.asyncio
    async def test_auto_stop_on_alarm(self):
        """設備告警 → 自動推入 stop override"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=True,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        # auto_stop override should be active
        assert "__auto_stop__" in sc.mode_manager.active_override_names

    @pytest.mark.asyncio
    async def test_auto_stop_recovery(self):
        """告警解除 → 自動移除 stop override"""
        reg = DeviceRegistry()
        # Start with alarm
        dev = _make_device("pcs1", {"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=True,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)

            # Verify alarm stop is active
            assert "__auto_stop__" in sc.mode_manager.active_override_names

            # Clear alarm
            type(dev).is_protected = PropertyMock(return_value=False)
            # StopStrategy is PERIODIC with 1s interval, so trigger() doesn't interrupt it.
            # Wait for the periodic cycle to complete.
            await asyncio.sleep(1.5)

            # Verify alarm stop is cleared
            assert "__auto_stop__" not in sc.mode_manager.active_override_names

            await sc.stop()

    @pytest.mark.asyncio
    async def test_auto_stop_disabled(self):
        """auto_stop_on_alarm=False → 不自動停機"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        assert "__auto_stop__" not in sc.mode_manager.active_override_names


class TestSystemControllerContextInjection:
    @pytest.mark.asyncio
    async def test_system_alarm_injected_in_context(self):
        """system_alarm 旗標被注入 context"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        # Build context manually
        ctx = sc._build_context()
        assert ctx.extra["system_alarm"] is True

    @pytest.mark.asyncio
    async def test_no_alarm_context(self):
        """無告警時 system_alarm=False"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0}, protected=False)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        ctx = sc._build_context()
        assert ctx.extra["system_alarm"] is False


class TestSystemControllerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        reg = DeviceRegistry()
        config = SystemControllerConfig()
        sc = SystemController(reg, config)

        async with asyncio.timeout(5):
            await sc.start()
            assert sc.is_running is True
            await sc.stop()

        assert sc.is_running is False

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        reg = DeviceRegistry()
        config = SystemControllerConfig()
        sc = SystemController(reg, config)

        async with asyncio.timeout(5):
            async with sc:
                assert sc.is_running is True
            assert sc.is_running is False

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """完整 pipeline: context → strategy → protection → route"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0, "meter_power": 200.0})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[
                ContextMapping(point_name="soc", context_field="soc", device_id="pcs1"),
            ],
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            protection_rules=[SOCProtection()],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(
            return_command=Command(p_target=300.0, q_target=100.0),
        )
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        # SOC=50% is normal, protection doesn't modify
        dev.write.assert_awaited_with("p_set", 300.0)
        assert strategy.execute_count >= 1
