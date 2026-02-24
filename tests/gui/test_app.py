"""Tests for GUI app factory."""

from csp_lib.gui.app import create_app
from csp_lib.gui.config import GUIConfig


class TestCreateApp:
    def test_create_app_returns_fastapi(self, mock_system_controller):
        app = create_app(mock_system_controller)
        assert app is not None
        assert app.title == "CSP Control Panel"

    def test_create_app_with_custom_config(self, mock_system_controller):
        config = GUIConfig(host="127.0.0.1", port=9090, snapshot_interval=10.0)
        app = create_app(mock_system_controller, config=config)
        assert app is not None

    def test_system_controller_in_state(self, mock_system_controller):
        app = create_app(mock_system_controller)
        assert app.state.system_controller is mock_system_controller

    def test_ws_manager_in_state(self, mock_system_controller):
        app = create_app(mock_system_controller)
        assert app.state.ws_manager is not None


class TestGUIConfig:
    def test_defaults(self):
        c = GUIConfig()
        assert c.host == "0.0.0.0"
        assert c.port == 8080
        assert c.cors_origins == ["*"]
        assert c.snapshot_interval == 5.0

    def test_custom(self):
        c = GUIConfig(host="127.0.0.1", port=9090, cors_origins=["http://localhost"], snapshot_interval=10.0)
        assert c.host == "127.0.0.1"
        assert c.port == 9090
