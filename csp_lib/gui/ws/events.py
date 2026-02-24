"""EventBridge: device events -> WebSocket JSON broadcasts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from csp_lib.equipment.device.events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    EVENT_VALUE_CHANGE,
    ConnectedPayload,
    DeviceAlarmPayload,
    DisconnectPayload,
    ReadCompletePayload,
    ValueChangePayload,
)

if TYPE_CHECKING:
    from csp_lib.integration import SystemController

    from .manager import WebSocketManager


class EventBridge:
    """
    Bridges device events to WebSocket broadcasts.

    Attaches handlers to all devices in the registry and converts
    event payloads to JSON dicts for WebSocket broadcasting.
    """

    def __init__(
        self,
        system_controller: SystemController,
        ws_manager: WebSocketManager,
        snapshot_interval: float = 5.0,
    ) -> None:
        self._sc = system_controller
        self._ws = ws_manager
        self._snapshot_interval = snapshot_interval
        self._cancel_fns: list[Callable[[], None]] = []
        self._snapshot_task: asyncio.Task[None] | None = None

    async def attach(self) -> None:
        """Register event handlers on all devices and start snapshot task."""
        for device in self._sc.registry.all_devices:
            self._attach_device(device)
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())

    async def detach(self) -> None:
        """Remove all event handlers and stop snapshot task."""
        for cancel in self._cancel_fns:
            cancel()
        self._cancel_fns.clear()

        if self._snapshot_task is not None:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass
            self._snapshot_task = None

    def _attach_device(self, device: Any) -> None:
        """Attach event handlers to a single device."""

        async def on_value_change(payload: ValueChangePayload) -> None:
            await self._ws.broadcast(
                {
                    "type": "value_change",
                    "device_id": payload.device_id,
                    "data": {
                        "point_name": payload.point_name,
                        "old_value": payload.old_value,
                        "new_value": payload.new_value,
                    },
                    "timestamp": payload.timestamp.isoformat(),
                }
            )

        async def on_alarm_triggered(payload: DeviceAlarmPayload) -> None:
            await self._ws.broadcast(
                {
                    "type": "alarm_triggered",
                    "device_id": payload.device_id,
                    "data": {
                        "code": payload.alarm_event.alarm.code,
                        "name": payload.alarm_event.alarm.name,
                        "level": payload.alarm_event.alarm.level.name,
                    },
                    "timestamp": payload.timestamp.isoformat(),
                }
            )

        async def on_alarm_cleared(payload: DeviceAlarmPayload) -> None:
            await self._ws.broadcast(
                {
                    "type": "alarm_cleared",
                    "device_id": payload.device_id,
                    "data": {
                        "code": payload.alarm_event.alarm.code,
                        "name": payload.alarm_event.alarm.name,
                        "level": payload.alarm_event.alarm.level.name,
                    },
                    "timestamp": payload.timestamp.isoformat(),
                }
            )

        async def on_connected(payload: ConnectedPayload) -> None:
            await self._ws.broadcast(
                {
                    "type": "connected",
                    "device_id": payload.device_id,
                    "data": {},
                    "timestamp": payload.timestamp.isoformat(),
                }
            )

        async def on_disconnected(payload: DisconnectPayload) -> None:
            await self._ws.broadcast(
                {
                    "type": "disconnected",
                    "device_id": payload.device_id,
                    "data": {
                        "reason": payload.reason,
                        "consecutive_failures": payload.consecutive_failures,
                    },
                    "timestamp": payload.timestamp.isoformat(),
                }
            )

        async def on_read_complete(payload: ReadCompletePayload) -> None:
            await self._ws.broadcast(
                {
                    "type": "read_complete",
                    "device_id": payload.device_id,
                    "data": {
                        "values": payload.values,
                        "duration_ms": payload.duration_ms,
                    },
                    "timestamp": payload.timestamp.isoformat(),
                }
            )

        self._cancel_fns.append(device.on(EVENT_VALUE_CHANGE, on_value_change))
        self._cancel_fns.append(device.on(EVENT_ALARM_TRIGGERED, on_alarm_triggered))
        self._cancel_fns.append(device.on(EVENT_ALARM_CLEARED, on_alarm_cleared))
        self._cancel_fns.append(device.on(EVENT_CONNECTED, on_connected))
        self._cancel_fns.append(device.on(EVENT_DISCONNECTED, on_disconnected))
        self._cancel_fns.append(device.on(EVENT_READ_COMPLETE, on_read_complete))

    async def _snapshot_loop(self) -> None:
        """Periodically broadcast full system state for newly connected clients."""
        while True:
            await asyncio.sleep(self._snapshot_interval)
            if self._ws.connection_count == 0:
                continue

            snapshot = self._build_snapshot()
            await self._ws.broadcast(snapshot)

    def _build_snapshot(self) -> dict[str, Any]:
        """Build a full system state snapshot."""
        devices: list[dict[str, Any]] = []
        for dev in self._sc.registry.all_devices:
            devices.append(
                {
                    "device_id": dev.device_id,
                    "is_connected": dev.is_connected,
                    "is_responsive": dev.is_responsive,
                    "is_protected": dev.is_protected,
                    "latest_values": dev.latest_values,
                    "active_alarm_count": len(dev.active_alarms),
                }
            )

        mm = self._sc.mode_manager
        effective = mm.effective_mode

        return {
            "type": "snapshot",
            "data": {
                "devices": devices,
                "mode": {
                    "base_mode_names": mm.base_mode_names,
                    "active_override_names": mm.active_override_names,
                    "effective_mode": effective.name if effective else None,
                },
                "auto_stop_active": self._sc.auto_stop_active,
                "is_running": self._sc.is_running,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
