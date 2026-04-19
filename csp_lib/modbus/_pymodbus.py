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
        ImportError: 若 pymodbus 完全未安裝，或 pymodbus 有裝但版本與
            本套件不相容（例如 3.13 移除了內部 ``pymodbus.datastore.store``
            路徑）。兩種情況會給出不同的訊息，方便使用者判斷要 pip install
            還是 pin 版本。
    """
    global _ModbusTcpServer, _ModbusDeviceContext, _ModbusServerContext, _BaseModbusDataBlock

    if _ModbusTcpServer is not None:
        return

    # 先確認 pymodbus 本身是否安裝；若沒裝才說「請 pip install」
    try:
        import pymodbus
    except ImportError as e:
        raise ImportError(
            "pymodbus server requires 'pymodbus' package. Install with: pip install 'csp0924_lib[modbus]'"
        ) from e

    # 有裝 pymodbus 但拿不到必要 symbol → 版本不相容（API drift）
    try:
        from pymodbus.datastore import ModbusDeviceContext, ModbusServerContext
        from pymodbus.datastore.store import BaseModbusDataBlock
        from pymodbus.server import ModbusTcpServer
    except ImportError as e:
        version = getattr(pymodbus, "__version__", "unknown")
        raise ImportError(
            f"pymodbus {version} is installed but a required server symbol could not be imported: {e}. "
            "csp_lib supports pymodbus>=3.0.0,<3.13. "
            "Either pin pymodbus to a supported version or upgrade csp_lib."
        ) from e

    _ModbusTcpServer = ModbusTcpServer
    _ModbusDeviceContext = ModbusDeviceContext
    _ModbusServerContext = ModbusServerContext
    _BaseModbusDataBlock = BaseModbusDataBlock


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
