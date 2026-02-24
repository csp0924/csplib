"""Shared fixtures for GUI tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system import ModePriority
from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.equipment.alarm.definition import AlarmDefinition, AlarmLevel
from csp_lib.equipment.alarm.state import AlarmState
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.system_controller import SystemController, SystemControllerConfig


def make_mock_device(
    device_id: str = "pcs_01",
    values: dict | None = None,
    responsive: bool = True,
    protected: bool = False,
    connected: bool = True,
    alarms: list | None = None,
    write_points: list[str] | None = None,
) -> MagicMock:
    """Create a mock AsyncModbusDevice."""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=connected)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=connected and responsive and not protected)
    type(dev).latest_values = PropertyMock(return_value=values or {"power": 100.0, "voltage": 220.0})
    type(dev).active_alarms = PropertyMock(return_value=alarms or [])

    # Config mock
    config = MagicMock()
    config.device_id = device_id
    config.unit_id = 1
    config.address_offset = 0
    config.read_interval = 1.0
    config.reconnect_interval = 5.0
    config.disconnect_threshold = 5
    type(dev).config = PropertyMock(return_value=config)

    # Write
    dev.write = AsyncMock()
    dev.clear_alarm = AsyncMock()

    # Write points
    wp = {name: MagicMock() for name in (write_points or ["p_set", "q_set"])}
    dev._write_points = wp

    # Events
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)

    # Health
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
    """A mock strategy for testing."""

    def __init__(self):
        self.execute_count = 0

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.TRIGGERED, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        return Command()

    async def on_activate(self) -> None:
        pass

    async def on_deactivate(self) -> None:
        pass


def make_alarm_state(
    code: str = "OVER_TEMP", name: str = "Over Temperature", level: AlarmLevel = AlarmLevel.ALARM, active: bool = True
) -> AlarmState:
    """Create a mock AlarmState."""
    defn = AlarmDefinition(code=code, name=name, level=level)
    state = AlarmState(definition=defn, is_active=active)
    if active:
        state.activated_at = datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc)
    return state


@pytest.fixture
def mock_registry() -> DeviceRegistry:
    """Create a registry with two mock devices."""
    registry = DeviceRegistry()
    dev1 = make_mock_device("pcs_01", values={"power": 100.0, "voltage": 220.0})
    dev2 = make_mock_device("pcs_02", values={"power": 50.0, "voltage": 221.0}, connected=False)
    registry.register(dev1, ["pcs", "inverter"])
    registry.register(dev2, ["pcs"])
    return registry


@pytest.fixture
def mock_system_controller(mock_registry: DeviceRegistry) -> SystemController:
    """Create a SystemController with mock devices and strategies."""
    config = SystemControllerConfig()
    sc = SystemController(mock_registry, config)

    strategy = MockStrategy()
    sc.register_mode("pq", strategy, ModePriority.SCHEDULE, "PQ Mode")
    sc.register_mode("stop", MockStrategy(), ModePriority.PROTECTION, "Stop Mode")
    return sc


@pytest.fixture
def app(mock_system_controller: SystemController):
    """Create a FastAPI test app."""
    from csp_lib.gui.app import create_app

    return create_app(mock_system_controller)


@pytest_asyncio.fixture
async def client(app) -> AsyncClient:
    """Create an httpx async client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
