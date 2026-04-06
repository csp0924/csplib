"""
CSP GUI - Web-based Runtime Control Panel

Browser-based monitoring and control panel for SystemController.

Optional dependency: pip install csp0924_lib[gui]

Usage::

    from csp_lib.integration import SystemController
    from csp_lib.gui import create_app, GUIConfig

    app = create_app(controller)

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from .app import create_app
    from .config import GUIConfig
except ImportError as _exc:
    raise ImportError(
        'csp_lib.gui requires additional dependencies. Install with: pip install "csp0924_lib[gui]"'
    ) from _exc

if TYPE_CHECKING:
    pass

__all__ = [
    "create_app",
    "GUIConfig",
]
