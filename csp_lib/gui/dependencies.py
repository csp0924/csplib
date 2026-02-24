"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from csp_lib.controller.system import ModeManager
    from csp_lib.integration import DeviceRegistry, SystemController

    from .ws.manager import WebSocketManager


def get_system_controller(request: Request) -> SystemController:
    """Extract SystemController from app state."""
    return request.app.state.system_controller


def get_registry(request: Request) -> DeviceRegistry:
    """Extract DeviceRegistry from app state."""
    return request.app.state.system_controller.registry


def get_mode_manager(request: Request) -> ModeManager:
    """Extract ModeManager from app state."""
    return request.app.state.system_controller.mode_manager


def get_ws_manager(request: Request) -> WebSocketManager:
    """Extract WebSocketManager from app state."""
    return request.app.state.ws_manager
