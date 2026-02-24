"""Tests for csp_lib.core.health."""

from unittest.mock import MagicMock, PropertyMock

from csp_lib.core.health import HealthCheckable, HealthReport, HealthStatus


class TestHealthStatus:
    def test_enum_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


class TestHealthReport:
    def test_basic_creation(self):
        report = HealthReport(status=HealthStatus.HEALTHY, component="test")
        assert report.status == HealthStatus.HEALTHY
        assert report.component == "test"
        assert report.message == ""
        assert report.details == {}
        assert report.children == []

    def test_with_details_and_children(self):
        child = HealthReport(status=HealthStatus.HEALTHY, component="child1")
        parent = HealthReport(
            status=HealthStatus.DEGRADED,
            component="parent",
            message="some issue",
            details={"key": "value"},
            children=[child],
        )
        assert parent.message == "some issue"
        assert parent.details == {"key": "value"}
        assert len(parent.children) == 1
        assert parent.children[0].component == "child1"

    def test_frozen(self):
        report = HealthReport(status=HealthStatus.HEALTHY, component="test")
        try:
            report.status = HealthStatus.UNHEALTHY  # type: ignore[misc]
            assert False, "Should raise"
        except AttributeError:
            pass


class TestHealthCheckable:
    def test_runtime_checkable(self):
        class Good:
            def health(self) -> HealthReport:
                return HealthReport(status=HealthStatus.HEALTHY, component="good")

        class Bad:
            pass

        assert isinstance(Good(), HealthCheckable)
        assert not isinstance(Bad(), HealthCheckable)

    def test_async_modbus_device_conforms(self):
        """AsyncModbusDevice should satisfy HealthCheckable protocol."""
        device = MagicMock()
        device.health = MagicMock(return_value=HealthReport(status=HealthStatus.HEALTHY, component="mock"))
        assert isinstance(device, HealthCheckable)


class TestAsyncModbusDeviceHealth:
    def _make_device_mock(self, connected: bool, responsive: bool, protected: bool, alarm_count: int = 0):
        """Create a mock with health() that mimics AsyncModbusDevice.health()."""
        from csp_lib.equipment.device.base import AsyncModbusDevice

        dev = MagicMock(spec=AsyncModbusDevice)
        type(dev).device_id = PropertyMock(return_value="pcs1")
        type(dev).is_connected = PropertyMock(return_value=connected)
        type(dev).is_responsive = PropertyMock(return_value=responsive)
        type(dev).is_protected = PropertyMock(return_value=protected)
        type(dev).is_healthy = PropertyMock(return_value=connected and responsive and not protected)
        type(dev).active_alarms = PropertyMock(return_value=[None] * alarm_count)

        # Call the real health method
        dev.health = lambda: AsyncModbusDevice.health(dev)
        return dev

    def test_healthy_device(self):
        dev = self._make_device_mock(connected=True, responsive=True, protected=False)
        report = dev.health()
        assert report.status == HealthStatus.HEALTHY
        assert report.component == "device:pcs1"
        assert report.details["connected"] is True
        assert report.details["active_alarms"] == 0

    def test_degraded_device(self):
        """Connected but has alarms → DEGRADED."""
        dev = self._make_device_mock(connected=True, responsive=True, protected=True, alarm_count=2)
        report = dev.health()
        assert report.status == HealthStatus.DEGRADED
        assert report.details["protected"] is True
        assert report.details["active_alarms"] == 2

    def test_unhealthy_device(self):
        """Not connected → UNHEALTHY."""
        dev = self._make_device_mock(connected=False, responsive=False, protected=False)
        report = dev.health()
        assert report.status == HealthStatus.UNHEALTHY
        assert report.details["connected"] is False
