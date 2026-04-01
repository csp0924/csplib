"""Root conftest for csp_lib test suite.

Provides cross-cutting fixtures shared across all test directories.
Directory-specific fixtures should remain in their local conftest.py files.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.integration.registry import DeviceRegistry

# ---------------------------------------------------------------------------
# make_mock_device — Factory fixture for AsyncModbusDevice mocks
# ---------------------------------------------------------------------------


def _make_mock_device(
    device_id: str = "dev_01",
    values: dict | None = None,
    responsive: bool = True,
    protected: bool = False,
    connected: bool = True,
) -> MagicMock:
    """Create a mock AsyncModbusDevice with sensible defaults.

    This is the underlying factory function. Use the ``make_mock_device``
    fixture in tests so that the factory is available via dependency injection.

    Args:
        device_id: Unique device identifier.
        values: Dict returned by ``latest_values``. Defaults to empty dict.
        responsive: Value for ``is_responsive`` property.
        protected: Value for ``is_protected`` property.
        connected: Value for ``is_connected`` property.

    Returns:
        A MagicMock that quacks like an ``AsyncModbusDevice``.
    """
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=connected)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=connected and responsive and not protected)
    type(dev).latest_values = PropertyMock(return_value=values or {})
    type(dev).active_alarms = PropertyMock(return_value=[])

    # Async write method
    dev.write = AsyncMock()

    # Event subscription — returns an unsubscribe callable
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)

    # Capability stubs (default: no capabilities)
    dev.has_capability = MagicMock(return_value=False)
    type(dev).capabilities = PropertyMock(return_value={})

    # Health report
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
            details={
                "connected": connected,
                "responsive": responsive,
                "protected": protected,
                "active_alarms": 0,
            },
        )

    dev.health = _health
    return dev


@pytest.fixture
def make_mock_device():
    """Factory fixture that returns a callable to create mock devices.

    Usage::

        def test_example(make_mock_device):
            dev = make_mock_device("pcs_01", values={"soc": 80.0})
            assert dev.device_id == "pcs_01"
    """
    return _make_mock_device


# ---------------------------------------------------------------------------
# mock_strategy — A simple Strategy implementation for testing
# ---------------------------------------------------------------------------


class _MockStrategyImpl(Strategy):
    """Concrete Strategy implementation for testing purposes.

    Tracks execution count and activation/deactivation lifecycle.
    """

    def __init__(
        self,
        return_command: Command | None = None,
        mode: ExecutionMode = ExecutionMode.TRIGGERED,
        interval: int = 1,
    ):
        self._return_command = return_command or Command()
        self._mode = mode
        self._interval = interval
        self.execute_count = 0
        self.activated = False
        self.deactivated = False

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=self._interval)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        return self._return_command

    async def on_activate(self) -> None:
        self.activated = True

    async def on_deactivate(self) -> None:
        self.deactivated = True


@pytest.fixture
def mock_strategy():
    """Fixture that returns a fresh mock Strategy instance.

    The strategy returns ``Command()`` by default and tracks:
    - ``execute_count``: number of times ``execute()`` was called
    - ``activated`` / ``deactivated``: lifecycle flags

    Usage::

        def test_example(mock_strategy):
            ctx = StrategyContext()
            cmd = mock_strategy.execute(ctx)
            assert mock_strategy.execute_count == 1
    """
    return _MockStrategyImpl()


# ---------------------------------------------------------------------------
# mock_registry — A DeviceRegistry pre-populated with two mock devices
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_registry(make_mock_device):
    """Fixture that returns a DeviceRegistry with two mock devices.

    Devices:
    - ``dev_01``: connected, responsive, healthy. Traits: ["pcs"].
    - ``dev_02``: connected, not responsive. Traits: ["pcs"].

    Usage::

        def test_example(mock_registry):
            assert len(mock_registry) == 2
            devs = mock_registry.get_devices_by_trait("pcs")
            assert len(devs) == 2
    """
    registry = DeviceRegistry()
    dev1 = make_mock_device("dev_01", values={"soc": 80.0})
    dev2 = make_mock_device("dev_02", values={"soc": 50.0}, responsive=False)
    registry.register(dev1, traits=["pcs"])
    registry.register(dev2, traits=["pcs"])
    return registry
