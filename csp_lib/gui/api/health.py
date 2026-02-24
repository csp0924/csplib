"""Health API endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from csp_lib.core.health import HealthReport
from csp_lib.integration import SystemController

from ..dependencies import get_system_controller

router = APIRouter(tags=["health"])


def _serialize_health(report: HealthReport) -> dict[str, Any]:
    """Recursively serialize a HealthReport."""
    return {
        "status": report.status.value,
        "component": report.component,
        "message": report.message,
        "details": report.details,
        "children": [_serialize_health(c) for c in report.children],
    }


@router.get("/health")
def get_health(sc: SystemController = Depends(get_system_controller)) -> dict[str, Any]:
    """Get system health report."""
    report = sc.health()
    return _serialize_health(report)
