"""Tests for mode API endpoints."""

import pytest


@pytest.mark.asyncio
class TestModesAPI:
    async def test_get_modes(self, client):
        resp = await client.get("/api/modes")
        assert resp.status_code == 200
        data = resp.json()
        assert "registered_modes" in data
        assert "base_mode_names" in data
        assert "active_override_names" in data
        assert "effective_mode" in data

    async def test_registered_modes_listed(self, client):
        resp = await client.get("/api/modes")
        data = resp.json()
        names = [m["name"] for m in data["registered_modes"]]
        assert "pq" in names
        assert "stop" in names

    async def test_set_base_mode(self, client):
        resp = await client.post("/api/modes/base", json={"name": "pq"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_set_base_mode_not_found(self, client):
        resp = await client.post("/api/modes/base", json={"name": "nonexistent"})
        assert resp.status_code == 404

    async def test_add_base_mode(self, client):
        resp = await client.post("/api/modes/base/add", json={"name": "pq"})
        assert resp.status_code == 200

    async def test_remove_base_mode_not_active(self, client):
        resp = await client.post("/api/modes/base/remove", json={"name": "pq"})
        assert resp.status_code == 404

    async def test_push_override(self, client):
        resp = await client.post("/api/modes/override/push", json={"name": "stop"})
        assert resp.status_code == 200

    async def test_push_override_not_found(self, client):
        resp = await client.post("/api/modes/override/push", json={"name": "nonexistent"})
        assert resp.status_code == 400

    async def test_pop_override_not_active(self, client):
        resp = await client.post("/api/modes/override/pop", json={"name": "stop"})
        assert resp.status_code == 400

    async def test_get_protection_status(self, client):
        resp = await client.get("/api/protection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_data"

    async def test_get_mode_config_no_support(self, client):
        resp = await client.get("/api/modes/pq/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    async def test_get_mode_config_not_found(self, client):
        resp = await client.get("/api/modes/nonexistent/config")
        assert resp.status_code == 404
