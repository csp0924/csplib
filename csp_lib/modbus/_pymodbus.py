"""Shared pymodbus lazy import utilities.

Centralizes pymodbus optional dependency management for server components.
Both modbus_server and modbus_gateway import from here instead of
duplicating the lazy-import pattern.
"""

from __future__ import annotations

_ModbusTcpServer: type | None = None
_ModbusDeviceContext: type | None = None
_ModbusServerContext: type | None = None
_BaseModbusDataBlock: type | None = None


def ensure_pymodbus_server() -> None:
    """Ensure pymodbus server components are imported.

    Raises:
        ImportError: If pymodbus is not installed.
    """
    global _ModbusTcpServer, _ModbusDeviceContext, _ModbusServerContext, _BaseModbusDataBlock

    if _ModbusTcpServer is not None:
        return

    try:
        from pymodbus.datastore import ModbusDeviceContext, ModbusServerContext
        from pymodbus.datastore.store import BaseModbusDataBlock
        from pymodbus.server import ModbusTcpServer

        _ModbusTcpServer = ModbusTcpServer
        _ModbusDeviceContext = ModbusDeviceContext
        _ModbusServerContext = ModbusServerContext
        _BaseModbusDataBlock = BaseModbusDataBlock
    except ImportError as e:
        raise ImportError(
            "pymodbus server requires 'pymodbus' package. Install with: pip install csp_lib[modbus]"
        ) from e


def get_ModbusTcpServer() -> type:
    """Return the ``ModbusTcpServer`` class, importing lazily if needed."""
    ensure_pymodbus_server()
    return _ModbusTcpServer  # type: ignore[return-value]


def get_BaseModbusDataBlock() -> type:
    """Return the ``BaseModbusDataBlock`` class, importing lazily if needed."""
    ensure_pymodbus_server()
    return _BaseModbusDataBlock  # type: ignore[return-value]


def get_ModbusDeviceContext() -> type:
    """Return the ``ModbusDeviceContext`` class, importing lazily if needed."""
    ensure_pymodbus_server()
    return _ModbusDeviceContext  # type: ignore[return-value]


def get_ModbusServerContext() -> type:
    """Return the ``ModbusServerContext`` class, importing lazily if needed."""
    ensure_pymodbus_server()
    return _ModbusServerContext  # type: ignore[return-value]


__all__ = [
    "ensure_pymodbus_server",
    "get_BaseModbusDataBlock",
    "get_ModbusDeviceContext",
    "get_ModbusServerContext",
    "get_ModbusTcpServer",
]
