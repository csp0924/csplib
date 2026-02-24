"""GUI configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GUIConfig:
    """
    GUI server configuration.

    Attributes:
        host: Bind host address
        port: Bind port
        cors_origins: Allowed CORS origins
        snapshot_interval: WebSocket full-state broadcast interval (seconds)
    """

    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    snapshot_interval: float = 5.0
