"""Tests for alarm API endpoints."""

from unittest.mock import PropertyMock

import pytest

from .conftest import make_alarm_state


@pytest.mark.asyncio
class TestAlarmsAPI:
    async def test_list_all_alarms_empty(self, client):
        resp = await client.get("/api/alarms")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    async def test_list_device_alarms_not_found(self, client):
        resp = await client.get("/api/alarms/nonexistent")
        assert resp.status_code == 404

    async def test_list_device_alarms_empty(self, client):
        resp = await client.get("/api/alarms/pcs_01")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_clear_alarm(self, client):
        resp = await client.post("/api/alarms/pcs_01/OVER_TEMP/clear")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_clear_alarm_device_not_found(self, client):
        resp = await client.post("/api/alarms/nonexistent/OVER_TEMP/clear")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestAlarmsWithActiveAlarms:
    async def test_list_alarms_with_active(self, mock_system_controller):
        """Test alarm listing when devices have active alarms."""
        from httpx import ASGITransport, AsyncClient

        from csp_lib.gui.app import create_app

        # Replace device with one that has alarms
        registry = mock_system_controller.registry
        device = registry.get_device("pcs_01")
        alarm = make_alarm_state("OVER_TEMP", "Over Temperature")
        type(device).active_alarms = PropertyMock(return_value=[alarm])

        app = create_app(mock_system_controller)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/alarms")
            data = resp.json()
            assert len(data) == 1
            assert data[0]["code"] == "OVER_TEMP"
            assert data[0]["level"] == "ALARM"
            assert data[0]["device_id"] == "pcs_01"
