"""Strategy config YAML export/import."""

from __future__ import annotations

from typing import Any

import yaml  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from csp_lib.integration import SystemController

from ..dependencies import get_system_controller

router = APIRouter(tags=["config"])


def _build_export(sc: SystemController) -> dict[str, Any]:
    """Build the YAML export dict."""
    mm = sc.mode_manager
    modes_data: list[dict[str, Any]] = []
    for name, mode_def in mm.registered_modes.items():
        if name.startswith("__"):
            continue
        entry: dict[str, Any] = {
            "name": mode_def.name,
            "strategy_type": type(mode_def.strategy).__name__,
            "priority": int(mode_def.priority),
        }
        strategy = mode_def.strategy
        if hasattr(strategy, "config") and hasattr(strategy.config, "to_dict"):
            entry["config"] = strategy.config.to_dict()
        modes_data.append(entry)

    return {
        "version": "1.0",
        "modes": modes_data,
        "active_base_modes": mm.base_mode_names,
        "active_overrides": mm.active_override_names,
        "system": {
            "auto_stop_on_alarm": sc.config.auto_stop_on_alarm,
            "alarm_mode": sc.config.alarm_mode,
        },
    }


@router.get("/config/export")
def export_config(sc: SystemController = Depends(get_system_controller)) -> Response:
    """Export strategy configs and mode state as YAML."""
    data = _build_export(sc)
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    return Response(content=content, media_type="application/x-yaml")


@router.post("/config/import")
async def import_config(
    file: UploadFile,
    sc: SystemController = Depends(get_system_controller),
) -> dict[str, Any]:
    """Import strategy configs and mode state from YAML."""
    raw = await file.read()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from None

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="YAML root must be a mapping")

    errors: list[str] = []
    mm = sc.mode_manager
    registered = mm.registered_modes

    # Update strategy configs
    for mode_entry in data.get("modes", []):
        name = mode_entry.get("name")
        config = mode_entry.get("config")
        if name and config and name in registered:
            strategy = registered[name].strategy
            if hasattr(strategy, "update_config"):
                try:
                    strategy.update_config(config)
                except Exception as e:
                    errors.append(f"Failed to update config for '{name}': {e}")

    # Switch base modes
    base_modes = data.get("active_base_modes", [])
    if base_modes:
        try:
            await sc.set_base_mode(None)
            for bm in base_modes:
                await sc.add_base_mode(bm)
        except (KeyError, ValueError) as e:
            errors.append(f"Failed to set base modes: {e}")

    # Switch overrides
    overrides = data.get("active_overrides", [])
    current_overrides = mm.active_override_names
    for ov in current_overrides:
        try:
            await sc.pop_override(ov)
        except KeyError:
            pass
    for ov in overrides:
        try:
            await sc.push_override(ov)
        except (KeyError, ValueError) as e:
            errors.append(f"Failed to push override '{ov}': {e}")

    return {"status": "ok" if not errors else "partial", "errors": errors}
