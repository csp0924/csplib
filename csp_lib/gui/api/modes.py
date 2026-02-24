"""Mode management API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from csp_lib.integration import SystemController

from ..dependencies import get_system_controller

router = APIRouter(tags=["modes"])


class ModeNameRequest(BaseModel):
    name: str


class ModeConfigRequest(BaseModel):
    config: dict[str, Any]


@router.get("/modes")
def get_modes(sc: SystemController = Depends(get_system_controller)) -> dict[str, Any]:
    """Get mode manager state."""
    mm = sc.mode_manager
    modes_info: list[dict[str, Any]] = []
    for name, mode_def in mm.registered_modes.items():
        if name.startswith("__"):
            continue
        modes_info.append(
            {
                "name": mode_def.name,
                "priority": mode_def.priority,
                "description": mode_def.description,
                "strategy_type": type(mode_def.strategy).__name__,
            }
        )

    effective = mm.effective_mode
    return {
        "registered_modes": modes_info,
        "base_mode_names": mm.base_mode_names,
        "active_override_names": mm.active_override_names,
        "effective_mode": effective.name if effective else None,
    }


@router.get("/modes/{name}/config")
def get_mode_config(
    name: str,
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, Any]:
    """Get a mode's strategy configuration (if it supports config)."""
    mm = sc.mode_manager
    modes = mm.registered_modes
    if name not in modes:
        raise HTTPException(status_code=404, detail=f"Mode '{name}' not found")

    strategy = modes[name].strategy
    if hasattr(strategy, "config") and hasattr(strategy.config, "to_dict"):
        return strategy.config.to_dict()
    return {"error": "Strategy does not support configuration export"}


@router.put("/modes/{name}/config")
def update_mode_config(
    name: str,
    body: ModeConfigRequest,
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, str]:
    """Update a mode's strategy configuration."""
    mm = sc.mode_manager
    modes = mm.registered_modes
    if name not in modes:
        raise HTTPException(status_code=404, detail=f"Mode '{name}' not found")

    strategy = modes[name].strategy
    if not hasattr(strategy, "update_config"):
        raise HTTPException(status_code=400, detail="Strategy does not support config update")

    try:
        strategy.update_config(body.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"status": "ok"}


@router.post("/modes/base")
async def set_base_mode(
    body: ModeNameRequest,
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, str]:
    """Set the base mode (replaces all existing base modes)."""
    try:
        await sc.set_base_mode(body.name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"status": "ok"}


@router.post("/modes/base/add")
async def add_base_mode(
    body: ModeNameRequest,
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, str]:
    """Add a base mode (multi-base coexistence)."""
    try:
        await sc.add_base_mode(body.name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"status": "ok"}


@router.post("/modes/base/remove")
async def remove_base_mode(
    body: ModeNameRequest,
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, str]:
    """Remove a base mode."""
    try:
        await sc.remove_base_mode(body.name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"status": "ok"}


@router.post("/modes/override/push")
async def push_override(
    body: ModeNameRequest,
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, str]:
    """Push an override mode."""
    try:
        await sc.push_override(body.name)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"status": "ok"}


@router.post("/modes/override/pop")
async def pop_override(
    body: ModeNameRequest,
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, str]:
    """Pop an override mode."""
    try:
        await sc.pop_override(body.name)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"status": "ok"}


@router.get("/protection")
def get_protection_status(
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, Any]:
    """Get the latest protection status."""
    result = sc.protection_status
    if result is None:
        return {"status": "no_data"}

    return {
        "was_modified": result.was_modified,
        "triggered_rules": result.triggered_rules,
        "original_command": {
            "p_target": result.original_command.p_target,
            "q_target": result.original_command.q_target,
        },
        "protected_command": {
            "p_target": result.protected_command.p_target,
            "q_target": result.protected_command.q_target,
        },
    }
