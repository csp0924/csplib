"""Tests for SystemController."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system import ModePriority, SOCProtection, SOCProtectionConfig, SystemAlarmProtection
from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL, CapabilityBinding
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CapabilityCommandMapping, CommandMapping, ContextMapping
from csp_lib.integration.system_controller import SystemController, SystemControllerConfig


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

    # health() method for HealthCheck integration
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

    @pytest.mark.slow
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


class TestSystemControllerPerDeviceAlarm:
    @pytest.mark.asyncio
    async def test_per_device_alarm_only_stops_alarmed_device(self):
        """per_device 模式：只關告警設備，其他繼續"""
        reg = DeviceRegistry()
        dev1 = _make_device("pcs1", values={"soc": 50.0}, protected=True)
        dev2 = _make_device("pcs2", values={"soc": 50.0}, protected=False)
        reg.register(dev1)
        reg.register(dev2)

        on_alarm = AsyncMock()
        config = SystemControllerConfig(
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs2"),
            ],
            auto_stop_on_alarm=False,
            alarm_mode="per_device",
            on_device_alarm=on_alarm,
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

        # pcs1 is protected → on_device_alarm called, no write
        on_alarm.assert_awaited_once()
        assert on_alarm.call_args[0][0].device_id == "pcs1"
        dev1.write.assert_not_awaited()
        # pcs2 is normal → written
        dev2.write.assert_awaited_with("p_set", 500.0)
        # auto_stop should NOT be pushed
        assert "__auto_stop__" not in sc.mode_manager.active_override_names

    @pytest.mark.asyncio
    async def test_per_device_alarm_no_system_alarm_in_context(self):
        """per_device 模式：system_alarm=False"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", values={"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            auto_stop_on_alarm=False,
            alarm_mode="per_device",
        )
        sc = SystemController(reg, config)
        ctx = sc._build_context()
        assert ctx.extra["system_alarm"] is False

    @pytest.mark.asyncio
    async def test_system_wide_alarm_still_works(self):
        """system_wide 模式：現有行為不變"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", values={"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            auto_stop_on_alarm=True,
            alarm_mode="system_wide",
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

        assert "__auto_stop__" in sc.mode_manager.active_override_names

    @pytest.mark.asyncio
    async def test_per_device_alarm_clear_callback(self):
        """告警解除時 on_device_alarm_clear 被呼叫"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", values={"soc": 50.0}, protected=True)
        reg.register(dev)

        on_alarm = AsyncMock()
        on_clear = AsyncMock()
        config = SystemControllerConfig(
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            auto_stop_on_alarm=False,
            alarm_mode="per_device",
            on_device_alarm=on_alarm,
            on_device_alarm_clear=on_clear,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)

            assert "pcs1" in sc.alarmed_device_ids
            on_alarm.assert_awaited_once()

            # Clear alarm
            type(dev).is_protected = PropertyMock(return_value=False)
            sc.trigger()
            await asyncio.sleep(0.1)

            on_clear.assert_awaited_once()
            assert "pcs1" not in sc.alarmed_device_ids

            await sc.stop()

    @pytest.mark.asyncio
    async def test_alarmed_device_ids_property(self):
        """alarmed_device_ids 屬性"""
        reg = DeviceRegistry()
        config = SystemControllerConfig(auto_stop_on_alarm=False, alarm_mode="per_device")
        sc = SystemController(reg, config)
        assert sc.alarmed_device_ids == set()


class TestSystemControllerCascading:
    @pytest.mark.asyncio
    async def test_add_base_mode_creates_cascading(self):
        """add_base_mode + capacity_kva → CascadingStrategy 組合"""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", values={"soc": 50.0})
        reg.register(dev)

        config = SystemControllerConfig(
            command_mappings=[
                CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1"),
            ],
            capacity_kva=1000,
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        s1 = MockStrategy(Command(p_target=600.0))
        s2 = MockStrategy(Command(p_target=600.0, q_target=200.0))
        sc.register_mode("pq", s1, 20)
        sc.register_mode("qv", s2, 10)

        await sc.add_base_mode("pq")
        await sc.add_base_mode("qv")

        # The executor should have a CascadingStrategy
        current = sc.executor.current_strategy
        assert current is not None
        assert "CascadingStrategy" in str(current)

    @pytest.mark.asyncio
    async def test_single_base_mode_no_cascading(self):
        """單一 base mode 不產生 CascadingStrategy"""
        reg = DeviceRegistry()
        config = SystemControllerConfig(capacity_kva=1000, auto_stop_on_alarm=False)
        sc = SystemController(reg, config)

        s1 = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", s1, 20)
        await sc.set_base_mode("pq")

        assert sc.executor.current_strategy is s1

    @pytest.mark.asyncio
    async def test_no_capacity_fallback_to_highest(self):
        """無 capacity_kva → fallback 到最高優先權"""
        reg = DeviceRegistry()
        config = SystemControllerConfig(auto_stop_on_alarm=False)
        sc = SystemController(reg, config)

        s1 = MockStrategy(Command(p_target=500.0))
        s2 = MockStrategy(Command(p_target=300.0))
        sc.register_mode("pq", s1, 20)
        sc.register_mode("qv", s2, 10)

        await sc.add_base_mode("pq")
        await sc.add_base_mode("qv")

        # No capacity → fallback to highest priority (pq)
        assert sc.executor.current_strategy is s1

    @pytest.mark.asyncio
    async def test_override_still_overrides_cascading(self):
        """override 仍然覆蓋 cascading"""
        reg = DeviceRegistry()
        config = SystemControllerConfig(capacity_kva=1000, auto_stop_on_alarm=False)
        sc = SystemController(reg, config)

        s1 = MockStrategy(Command(p_target=500.0))
        s2 = MockStrategy(Command(p_target=300.0))
        s_override = MockStrategy(Command(p_target=0.0))
        sc.register_mode("pq", s1, 20)
        sc.register_mode("qv", s2, 10)
        sc.register_mode("manual_stop", s_override, ModePriority.MANUAL)

        await sc.add_base_mode("pq")
        await sc.add_base_mode("qv")
        await sc.push_override("manual_stop")

        assert sc.executor.current_strategy is s_override

    @pytest.mark.asyncio
    async def test_remove_base_mode_reverts(self):
        """remove_base_mode 後回到單一 base"""
        reg = DeviceRegistry()
        config = SystemControllerConfig(capacity_kva=1000, auto_stop_on_alarm=False)
        sc = SystemController(reg, config)

        s1 = MockStrategy(Command(p_target=500.0))
        s2 = MockStrategy(Command(p_target=300.0))
        sc.register_mode("pq", s1, 20)
        sc.register_mode("qv", s2, 10)

        await sc.add_base_mode("pq")
        await sc.add_base_mode("qv")
        await sc.remove_base_mode("qv")

        assert sc.executor.current_strategy is s1


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
    async def test_on_start_rollback_on_heartbeat_failure(self):
        """若 heartbeat.start() 失敗，_on_start 應呼叫 _on_stop 清理已 attach 的 data_feed。

        PEP 492 規定 ``__aenter__`` 拋異常時不會呼叫 ``__aexit__``，因此 ``_on_start``
        自身必須負責部分啟動的 rollback，否則 data_feed 會洩漏 event listener。
        """
        from csp_lib.integration.schema import DataFeedMapping

        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"pv_power": 100.0})
        reg.register(dev)

        config = SystemControllerConfig(
            data_feed_mapping=DataFeedMapping(device_id="pcs1", point_name="pv_power"),
        )
        sc = SystemController(reg, config)

        # 注入會失敗的 heartbeat mock（直接覆寫 _heartbeat，繞過 config 驅動的初始化）
        failing_hb = MagicMock()
        failing_hb.start = AsyncMock(side_effect=RuntimeError("heartbeat start failed"))
        failing_hb.stop = AsyncMock()
        sc._heartbeat = failing_hb
        sc._validate_heartbeat_points = MagicMock()  # type: ignore[method-assign]

        # 記錄 data_feed 的 detach 呼叫
        assert sc._data_feed is not None
        detach_spy = MagicMock(wraps=sc._data_feed.detach)
        sc._data_feed.detach = detach_spy  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="heartbeat start failed"):
            await sc.start()

        # Rollback 路徑必須呼叫 detach（避免 event listener 洩漏）
        detach_spy.assert_called()
        # _run_task 不應被建立
        assert sc._run_task is None
        # is_running 回到 False
        assert sc.is_running is False

    @pytest.mark.asyncio
    async def test_on_start_rollback_via_async_with(self):
        """async with 模式下若 _on_start 失敗，caller 不應再看到 executor 在跑。

        驗證 PEP 492 陷阱的防護：__aenter__ 拋異常時 __aexit__ 不會被呼叫，
        但 _on_start 內的 try/except 已做 rollback。
        """
        reg = DeviceRegistry()
        config = SystemControllerConfig()
        sc = SystemController(reg, config)

        # 讓 preflight_check 直接 raise
        sc.preflight_check = MagicMock(side_effect=RuntimeError("preflight failed"))  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="preflight failed"):
            async with sc:
                pass  # pragma: no cover

        assert sc._run_task is None
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


class TestSystemControllerHealth:
    def test_health_all_healthy(self):
        reg = DeviceRegistry()
        d1 = _make_device("pcs1", connected=True, responsive=True, protected=False)
        d2 = _make_device("pcs2", connected=True, responsive=True, protected=False)
        reg.register(d1)
        reg.register(d2)

        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))
        report = sc.health()

        assert report.status == HealthStatus.HEALTHY
        assert report.component == "system_controller"
        assert len(report.children) == 2
        assert all(c.status == HealthStatus.HEALTHY for c in report.children)

    def test_health_one_unhealthy(self):
        reg = DeviceRegistry()
        d1 = _make_device("pcs1", connected=True, responsive=True, protected=False)
        d2 = _make_device("pcs2", connected=False, responsive=False, protected=False)
        reg.register(d1)
        reg.register(d2)

        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))
        report = sc.health()

        assert report.status == HealthStatus.UNHEALTHY

    def test_health_degraded(self):
        reg = DeviceRegistry()
        d1 = _make_device("pcs1", connected=True, responsive=True, protected=True)  # alarmed → degraded
        d2 = _make_device("pcs2", connected=True, responsive=True, protected=False)
        reg.register(d1)
        reg.register(d2)

        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))
        report = sc.health()

        assert report.status == HealthStatus.DEGRADED

    def test_health_no_devices(self):
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))
        report = sc.health()

        # No devices → all() on empty is True → HEALTHY
        assert report.status == HealthStatus.HEALTHY
        assert len(report.children) == 0

    def test_health_details(self):
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))
        report = sc.health()

        assert "mode" in report.details
        assert "alarmed" in report.details


class TestBuildDeviceSnapshots:
    """測試 _build_device_snapshots 應僅回傳有 capability binding 的設備。

    Bug: _build_device_snapshots() 迭代 registry.all_devices 而未過濾無 capability 的設備。
    當 registry 包含無 capability 的設備（如電表），它們會被包含在 snapshot 清單中，
    導致 EqualDistributor 以錯誤的設備數量分配功率（例如 3 台而非 2 台 PCS）。

    修復前：回傳 3 個 snapshot（2 PCS + 1 meter）
    修復後：回傳 2 個 snapshot（僅 PCS）
    """

    @staticmethod
    def _make_pcs_device(device_id: str) -> MagicMock:
        """建立具有 ACTIVE_POWER_CONTROL capability 的 PCS 設備 mock。"""
        dev = _make_device(device_id, values={"p_meas": 50.0}, responsive=True, protected=False)
        binding = CapabilityBinding(
            ACTIVE_POWER_CONTROL,
            {"p_setpoint": "p_set", "p_measurement": "p_meas"},
        )
        # 設備的 capabilities 屬性：capability_name → CapabilityBinding
        type(dev).capabilities = PropertyMock(return_value={"active_power_control": binding})
        return dev

    @staticmethod
    def _make_meter_device(device_id: str) -> MagicMock:
        """建立不具備任何 capability 的電表設備 mock。"""
        dev = _make_device(device_id, values={"voltage": 220.0}, responsive=True, protected=False)
        # 電表沒有 capability binding
        type(dev).capabilities = PropertyMock(return_value={})
        return dev

    def test_snapshots_exclude_devices_without_capabilities(self):
        """_build_device_snapshots 應僅回傳有 capability 的設備，排除無 capability 的電表。

        這是 bug 重現測試：修復前 len(snapshots) == 3（錯誤包含電表），
        修復後應為 len(snapshots) == 2（僅 PCS）。
        """
        reg = DeviceRegistry()
        pcs1 = self._make_pcs_device("pcs_1")
        pcs2 = self._make_pcs_device("pcs_2")
        meter = self._make_meter_device("meter_1")

        reg.register(pcs1, metadata={"rated_p": 100.0})
        reg.register(pcs2, metadata={"rated_p": 100.0})
        reg.register(meter, metadata={"type": "meter"})

        config = SystemControllerConfig(
            auto_stop_on_alarm=False,
            capability_command_mappings=[
                CapabilityCommandMapping(
                    command_field="p_target",
                    capability=ACTIVE_POWER_CONTROL,
                    slot="p_setpoint",
                    trait="pcs",
                ),
            ],
        )
        sc = SystemController(reg, config)

        snapshots = sc._build_device_snapshots()

        # 修復後：僅有 2 台 PCS 設備的 snapshot
        assert len(snapshots) == 2, (
            f"預期僅回傳 2 個有 capability 的設備 snapshot，但實際回傳 {len(snapshots)} 個（包含無 capability 的電表）"
        )
        snapshot_ids = {s.device_id for s in snapshots}
        assert snapshot_ids == {"pcs_1", "pcs_2"}, f"Snapshot 應僅包含 PCS 設備，但包含了: {snapshot_ids}"
