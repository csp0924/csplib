"""
ModbusGatewayServer — Modbus TCP Gateway 主 orchestrator

對外暴露系統狀態讓 EMS/SCADA 透過 Modbus TCP 讀寫。
整合 RegisterMap, WritePipeline, DataSyncSource, Watchdog。

Usage::

    config = GatewayServerConfig(port=502, unit_id=1)
    registers = [
        GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING),
        GatewayRegisterDef("soc", 100, UInt16(), RegisterType.INPUT, scale=10),
    ]
    async with ModbusGatewayServer(config, registers) as gw:
        gw.add_hook(CallbackHook(on_write))
        await gw.serve()
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .config import GatewayRegisterDef, GatewayServerConfig, RegisterType
from .hooks import StatePersistHook
from .pipeline import WritePipeline
from .register_map import GatewayRegisterMap
from .watchdog import CommunicationWatchdog

logger = get_logger(__name__)


class ModbusGatewayServer(AsyncLifecycleMixin):
    """
    Modbus TCP Gateway Server.

    Exposes system state to external EMS/SCADA via Modbus TCP.
    Manages the full lifecycle: register map, pymodbus server,
    write pipeline, data sync sources, and communication watchdog.
    """

    def __init__(
        self,
        config: GatewayServerConfig,
        register_defs: Sequence[GatewayRegisterDef],
        *,
        write_rules: Mapping[str, Any] | None = None,
        validators: Sequence[Any] = (),  # WriteValidator instances
        hooks: Sequence[Any] = (),  # WriteHook instances
        sync_sources: Sequence[Any] = (),  # DataSyncSource instances
    ) -> None:
        self._config = config
        self._register_defs = list(register_defs)
        self._write_rules: dict[str, Any] = dict(write_rules) if write_rules else {}

        # Build register map
        self._register_map = GatewayRegisterMap(config, register_defs)

        # Build pipeline
        self._pipeline = WritePipeline(self._register_map, self._write_rules)
        for v in validators:
            self._pipeline.add_validator(v)
        for h in hooks:
            self._pipeline.add_hook(h)

        # Sync sources
        self._sync_sources: list[Any] = list(sync_sources)

        # Watchdog
        self._watchdog = CommunicationWatchdog(config.watchdog)

        # pymodbus server (created in _on_start)
        self._server: Any = None
        self._serve_event: asyncio.Event = asyncio.Event()

    # ─────────────────────── Public API ───────────────────────

    @property
    def config(self) -> GatewayServerConfig:
        return self._config

    @property
    def register_map(self) -> GatewayRegisterMap:
        return self._register_map

    @property
    def watchdog(self) -> CommunicationWatchdog:
        return self._watchdog

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def add_validator(self, validator: Any) -> None:
        """Add a write validator to the pipeline."""
        self._pipeline.add_validator(validator)

    def add_hook(self, hook: Any) -> None:
        """Add a write hook to the pipeline."""
        self._pipeline.add_hook(hook)

    def add_sync_source(self, source: Any) -> None:
        """Add a data sync source."""
        self._sync_sources.append(source)

    def set_register(self, name: str, value: Any) -> None:
        """Set a register value programmatically."""
        self._register_map.set_value(name, value)

    def get_register(self, name: str) -> Any:
        """Get a register value programmatically."""
        return self._register_map.get_value(name)

    def get_all_registers(self) -> dict[str, Any]:
        """Get all register values."""
        return self._register_map.get_all_values()

    async def serve(self) -> None:
        """Block until the server is stopped (via stop() or context manager exit)."""
        await self._serve_event.wait()

    # ─────────────────────── Lifecycle ───────────────────────

    async def _on_start(self) -> None:
        """Start pymodbus server, sync sources, and watchdog."""
        from .datablock import create_empty_datablock, create_hr_datablock, create_ir_datablock

        loop = asyncio.get_running_loop()

        # Lazy import pymodbus
        from csp_lib.modbus._pymodbus import get_ModbusDeviceContext, get_ModbusServerContext, get_ModbusTcpServer

        ModbusTcpServer = get_ModbusTcpServer()
        ModbusDeviceContext = get_ModbusDeviceContext()
        ModbusServerContext = get_ModbusServerContext()

        # Create DataBlocks
        hr_block = create_hr_datablock(self._register_map, self._pipeline, self._watchdog, loop)
        ir_block = create_ir_datablock(self._register_map, self._watchdog)
        empty_block = create_empty_datablock()

        # Create pymodbus context
        device_ctx = ModbusDeviceContext(
            di=empty_block,
            co=empty_block,
            hr=hr_block,
            ir=ir_block,
        )
        server_ctx = ModbusServerContext(
            devices={self._config.unit_id: device_ctx},
            single=False,
        )

        # Create and start pymodbus server
        self._server = ModbusTcpServer(
            context=server_ctx,
            address=(self._config.host, self._config.port),
        )
        await self._server.serve_forever(background=True)

        # Restore persisted state (if StatePersistHook registered)
        for hook in self._pipeline.hooks:
            if isinstance(hook, StatePersistHook):
                await hook.restore_all(self._register_map)
                break

        # Start sync sources
        for source in self._sync_sources:
            await source.start(self._update_register_callback)

        # Start watchdog
        await self._watchdog.start()

        self._serve_event.clear()

        if self._config.host == "0.0.0.0":
            logger.warning(
                "Gateway bound to 0.0.0.0 (all interfaces); consider binding to a specific interface for security"
            )

        logger.info(
            f"ModbusGatewayServer started on {self._config.host}:{self._config.port} "
            f"(unit_id={self._config.unit_id}, {len(self._register_defs)} registers)"
        )

    async def _on_stop(self) -> None:
        """Stop watchdog, sync sources, and pymodbus server."""
        # Stop watchdog
        await self._watchdog.stop()

        # Stop sync sources
        for source in self._sync_sources:
            try:
                await source.stop()
            except Exception:
                logger.opt(exception=True).warning(f"Failed to stop sync source {type(source).__name__}")

        # Stop pymodbus server
        if self._server is not None:
            await self._server.shutdown()
            self._server = None

        self._serve_event.set()
        logger.info("ModbusGatewayServer stopped")

    # ─────────────────────── Internal ───────────────────────

    async def _update_register_callback(self, register_name: str, value: Any) -> None:
        """Callback for DataSyncSource to update registers.

        Sync sources may only write INPUT registers; HOLDING registers belong to
        the EMS command space and are mutable only via the Modbus WritePipeline.
        """
        reg_def = self._register_map.get_register_def(register_name)

        if reg_def.register_type == RegisterType.HOLDING:
            logger.error(
                f"sync source attempted to write HOLDING register "
                f"'{register_name}' — rejected (sync sources may only write INPUT registers)"
            )
            raise PermissionError(f"Sync sources cannot write HOLDING register '{register_name}'.")

        self._register_map.set_value(register_name, value)


__all__ = ["ModbusGatewayServer"]
