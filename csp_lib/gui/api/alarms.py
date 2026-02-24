"""Alarm API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from csp_lib.integration import DeviceRegistry

from ..dependencies import get_registry

router = APIRouter(tags=["alarms"])


def _serialize_alarm(device_id: str, alarm_state: Any) -> dict[str, Any]:
    """Serialize an alarm state with device context."""
    d = alarm_state.definition
    return {
        "device_id": device_id,
        "code": d.code,
        "name": d.name,
        "level": d.level.name,
        "is_active": alarm_state.is_active,
        "activated_at": alarm_state.activated_at.isoformat() if alarm_state.activated_at else None,
        "duration": alarm_state.duration,
    }


@router.get("/alarms")
def list_all_alarms(registry: DeviceRegistry = Depends(get_registry)) -> list[dict[str, Any]]:
    """Get all active alarms across all devices."""
    alarms: list[dict[str, Any]] = []
    for device in registry.all_devices:
        for alarm in device.active_alarms:
            alarms.append(_serialize_alarm(device.device_id, alarm))
    return alarms


@router.get("/alarms/{device_id}")
def list_device_alarms(
    device_id: str,
    registry: DeviceRegistry = Depends(get_registry),
) -> list[dict[str, Any]]:
    """Get active alarms for a specific device."""
    device = registry.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return [_serialize_alarm(device_id, a) for a in device.active_alarms]


@router.post("/alarms/{device_id}/{code}/clear")
async def clear_alarm(
    device_id: str,
    code: str,
    registry: DeviceRegistry = Depends(get_registry),
) -> dict[str, str]:
    """Clear a specific alarm on a device."""
    device = registry.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    await device.clear_alarm(code)
    return {"status": "ok"}
