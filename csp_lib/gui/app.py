"""FastAPI app factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import GUIConfig
from .ws.events import EventBridge
from .ws.manager import WebSocketManager

if TYPE_CHECKING:
    from csp_lib.integration import SystemController

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    system_controller: SystemController,
    config: GUIConfig | None = None,
) -> FastAPI:
    """
    Create the GUI FastAPI application.

    Args:
        system_controller: A live SystemController instance.
        config: Optional GUI configuration.

    Returns:
        Configured FastAPI app.
    """
    config = config or GUIConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bridge = EventBridge(
            system_controller=app.state.system_controller,
            ws_manager=app.state.ws_manager,
            snapshot_interval=config.snapshot_interval,
        )
        app.state.event_bridge = bridge
        await bridge.attach()
        try:
            yield
        finally:
            await bridge.detach()

    app = FastAPI(
        title="CSP Control Panel",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Store references
    app.state.system_controller = system_controller
    app.state.ws_manager = WebSocketManager()

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # REST API routers
    from .api.alarms import router as alarms_router
    from .api.commands import router as commands_router
    from .api.config_io import router as config_io_router
    from .api.devices import router as devices_router
    from .api.health import router as health_router
    from .api.modes import router as modes_router
    from .ws.router import router as ws_router

    app.include_router(devices_router, prefix="/api")
    app.include_router(alarms_router, prefix="/api")
    app.include_router(commands_router, prefix="/api")
    app.include_router(modes_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(config_io_router, prefix="/api")
    app.include_router(ws_router)

    # Static files (SPA)
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
