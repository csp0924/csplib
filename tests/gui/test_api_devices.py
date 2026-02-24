"""Tests for device API endpoints."""

import pytest


@pytest.mark.asyncio
class TestDevicesAPI:
    async def test_list_devices(self, client):
        resp = await client.get("/api/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        ids = [d["device_id"] for d in data]
        assert "pcs_01" in ids
        assert "pcs_02" in ids

    async def test_list_devices_has_status(self, client):
        resp = await client.get("/api/devices")
        data = resp.json()
        pcs01 = next(d for d in data if d["device_id"] == "pcs_01")
        assert pcs01["is_connected"] is True
        assert pcs01["is_responsive"] is True
        assert pcs01["is_protected"] is False

    async def test_get_device_detail(self, client):
        resp = await client.get("/api/devices/pcs_01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_id"] == "pcs_01"
        assert "latest_values" in data
        assert "active_alarms" in data

    async def test_get_device_not_found(self, client):
        resp = await client.get("/api/devices/nonexistent")
        assert resp.status_code == 404

    async def test_get_device_values(self, client):
        resp = await client.get("/api/devices/pcs_01/values")
        assert resp.status_code == 200
        data = resp.json()
        assert "power" in data
        assert data["power"] == 100.0

    async def test_get_device_values_not_found(self, client):
        resp = await client.get("/api/devices/nonexistent/values")
        assert resp.status_code == 404

    async def test_get_devices_by_trait(self, client):
        resp = await client.get("/api/devices/by-trait/pcs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_get_devices_by_trait_inverter(self, client):
        resp = await client.get("/api/devices/by-trait/inverter")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "pcs_01"

    async def test_device_has_traits(self, client):
        resp = await client.get("/api/devices/pcs_01")
        data = resp.json()
        assert "pcs" in data["traits"]
        assert "inverter" in data["traits"]
