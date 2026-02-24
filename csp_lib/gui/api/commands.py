"""Command and write API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from csp_lib.integration import DeviceRegistry, SystemController

from ..dependencies import get_registry, get_system_controller

router = APIRouter(tags=["commands"])


class WriteRequest(BaseModel):
    point_name: str
    value: Any
    verify: bool = False


@router.get("/devices/{device_id}/write-points")
def list_write_points(
    device_id: str,
    registry: DeviceRegistry = Depends(get_registry),
) -> list[str]:
    """List available write point names for a device."""
    device = registry.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return sorted(device._write_points.keys())


@router.post("/devices/{device_id}/write")
async def write_to_device(
    device_id: str,
    body: WriteRequest,
    registry: DeviceRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Write a value to a device point."""
    device = registry.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    result = await device.write(body.point_name, body.value, verify=body.verify)
    return {
        "status": result.status.name,
        "point_name": result.point_name,
        "value": result.value,
        "error_message": result.error_message,
    }


@router.post("/executor/trigger")
def trigger_executor(
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, str]:
    """Manually trigger strategy execution."""
    sc.trigger()
    return {"status": "triggered"}
