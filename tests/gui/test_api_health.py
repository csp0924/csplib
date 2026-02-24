"""Tests for health API endpoint."""

import pytest


@pytest.mark.asyncio
class TestHealthAPI:
    async def test_get_health(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "component" in data
        assert data["component"] == "system_controller"

    async def test_health_has_children(self, client):
        resp = await client.get("/api/health")
        data = resp.json()
        assert "children" in data
        assert len(data["children"]) == 2  # two devices

    async def test_health_children_have_status(self, client):
        resp = await client.get("/api/health")
        data = resp.json()
        for child in data["children"]:
            assert "status" in child
            assert child["status"] in ("healthy", "degraded", "unhealthy")
