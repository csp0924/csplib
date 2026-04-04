"""Capabilities API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from csp_lib.integration import DeviceRegistry

from ..dependencies import get_registry

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities")
def list_capabilities(registry: DeviceRegistry = Depends(get_registry)) -> dict[str, list[str]]:
    """回傳 capability_name → device_ids 映射"""
    return registry.get_capability_map()


@router.get("/capabilities/{capability_name}/health")
def capability_health(
    capability_name: str,
    registry: DeviceRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """回傳指定 capability 的健康狀態"""
    result = registry.capability_health(capability_name)
    if result["total_devices"] == 0:
        raise HTTPException(status_code=404, detail=f"No devices with capability '{capability_name}'")
    return result
