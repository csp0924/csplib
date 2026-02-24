"""Device API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from csp_lib.integration import DeviceRegistry

from ..dependencies import get_registry

router = APIRouter(tags=["devices"])


def _serialize_device(device: Any, registry: DeviceRegistry) -> dict[str, Any]:
    """Serialize a device to a JSON-compatible dict."""
    config = device.config
    return {
        "device_id": device.device_id,
        "is_connected": device.is_connected,
        "is_responsive": device.is_responsive,
        "is_protected": device.is_protected,
        "config": {
            "device_id": config.device_id,
            "unit_id": config.unit_id,
            "address_offset": config.address_offset,
            "read_interval": config.read_interval,
            "reconnect_interval": config.reconnect_interval,
            "disconnect_threshold": config.disconnect_threshold,
        },
        "traits": sorted(registry.get_traits(device.device_id)),
        "active_alarm_count": len(device.active_alarms),
    }


def _serialize_alarm_state(alarm_state: Any) -> dict[str, Any]:
    """Serialize an AlarmState to a JSON-compatible dict."""
    d = alarm_state.definition
    return {
        "code": d.code,
        "name": d.name,
        "level": d.level.name,
        "is_active": alarm_state.is_active,
        "activated_at": alarm_state.activated_at.isoformat() if alarm_state.activated_at else None,
        "duration": alarm_state.duration,
    }


@router.get("/devices")
def list_devices(registry: DeviceRegistry = Depends(get_registry)) -> list[dict[str, Any]]:
    """List all registered devices with status flags."""
    return [_serialize_device(dev, registry) for dev in registry.all_devices]


@router.get("/devices/by-trait/{trait}")
def get_devices_by_trait(
    trait: str,
    registry: DeviceRegistry = Depends(get_registry),
) -> list[dict[str, Any]]:
    """Get devices matching a trait."""
    return [_serialize_device(dev, registry) for dev in registry.get_devices_by_trait(trait)]


@router.get("/devices/{device_id}")
def get_device(
    device_id: str,
    registry: DeviceRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Get detailed device info including latest values and alarms."""
    device = registry.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    info = _serialize_device(device, registry)
    info["latest_values"] = device.latest_values
    info["active_alarms"] = [_serialize_alarm_state(a) for a in device.active_alarms]
    return info


@router.get("/devices/{device_id}/values")
def get_device_values(
    device_id: str,
    registry: DeviceRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Get latest point values for a device."""
    device = registry.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    return device.latest_values
