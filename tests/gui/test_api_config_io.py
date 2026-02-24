"""Tests for config import/export API endpoints."""

import io

import pytest


@pytest.mark.asyncio
class TestConfigAPI:
    async def test_export_config(self, client):
        resp = await client.get("/api/config/export")
        assert resp.status_code == 200
        assert "version" in resp.text
        assert "modes" in resp.text

    async def test_export_config_yaml_format(self, client):
        resp = await client.get("/api/config/export")
        import yaml

        data = yaml.safe_load(resp.text)
        assert data["version"] == "1.0"
        assert isinstance(data["modes"], list)
        assert "active_base_modes" in data
        assert "active_overrides" in data

    async def test_import_config(self, client):
        yaml_content = """
version: "1.0"
modes: []
active_base_modes: []
active_overrides: []
system:
  auto_stop_on_alarm: true
  alarm_mode: system_wide
"""
        files = {"file": ("config.yaml", io.BytesIO(yaml_content.encode()), "application/x-yaml")}
        resp = await client.post("/api/config/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "partial")

    async def test_import_invalid_yaml(self, client):
        files = {"file": ("config.yaml", io.BytesIO(b"{{invalid yaml"), "application/x-yaml")}
        resp = await client.post("/api/config/import", files=files)
        assert resp.status_code == 400

    async def test_import_with_base_modes(self, client):
        yaml_content = """
version: "1.0"
modes: []
active_base_modes:
  - pq
active_overrides: []
"""
        files = {"file": ("config.yaml", io.BytesIO(yaml_content.encode()), "application/x-yaml")}
        resp = await client.post("/api/config/import", files=files)
        assert resp.status_code == 200
