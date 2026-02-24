"""Tests for command API endpoints."""

import pytest


@pytest.mark.asyncio
class TestCommandsAPI:
    async def test_list_write_points(self, client):
        resp = await client.get("/api/devices/pcs_01/write-points")
        assert resp.status_code == 200
        data = resp.json()
        assert "p_set" in data
        assert "q_set" in data

    async def test_list_write_points_not_found(self, client):
        resp = await client.get("/api/devices/nonexistent/write-points")
        assert resp.status_code == 404

    async def test_write_to_device(self, client):
        resp = await client.post(
            "/api/devices/pcs_01/write",
            json={"point_name": "p_set", "value": 100.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    async def test_write_to_device_not_found(self, client):
        resp = await client.post(
            "/api/devices/nonexistent/write",
            json={"point_name": "p_set", "value": 100.0},
        )
        assert resp.status_code == 404

    async def test_trigger_executor(self, client):
        resp = await client.post("/api/executor/trigger")
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"
