# =============== Modbus Data Layer Module ===============
#
# Modbus 資料層模組
#
# 提供資料類型定義與編解碼功能，以及 pymodbus 非同步客戶端封裝。
#
# 安裝方式：
#     uv pip install csp_lib[modbus]
#
# Usage:
#     from csp_lib.modbus import (
#         # Config
#         ModbusTcpConfig, ModbusRtuConfig,
#         # Enums
#         ByteOrder, RegisterOrder, FunctionCode, Parity,
#         # Types
#         Int16, UInt16, Int32, UInt32, Float32,
#         DynamicInt, DynamicUInt,
#         ModbusString,
#         # Codec
#         ModbusCodec,
#         # Client (async)
#         AsyncModbusClientBase,
#         PymodbusTcpClient,
#         PymodbusRtuClient,
#     )

# Exceptions
from .exceptions import (
    ModbusError,
    ModbusEncodeError,
    ModbusDecodeError,
    ModbusConfigError,
)

# Enums
from .enums import (
    ByteOrder,
    RegisterOrder,
    Parity,
    FunctionCode,
)

# Config
from .config import (
    ModbusTcpConfig,
    ModbusRtuConfig,
)

# Types
from .types import (
    ModbusDataType,
    Int16,
    UInt16,
    Int32,
    UInt32,
    Float32,
    Int64,
    UInt64,
    Float64,
    DynamicInt,
    DynamicUInt,
    ModbusString,
)

# Codec
from .codec import ModbusCodec

# Clients
from .clients import (
    AsyncModbusClientBase,
    PymodbusTcpClient,
    PymodbusRtuClient,
    SharedPymodbusTcpClient,
)

__all__ = [
    # Exceptions
    "ModbusError",
    "ModbusEncodeError",
    "ModbusDecodeError",
    "ModbusConfigError",
    # Enums
    "ByteOrder",
    "RegisterOrder",
    "Parity",
    "FunctionCode",
    # Config
    "ModbusTcpConfig",
    "ModbusRtuConfig",
    # Types - Base
    "ModbusDataType",
    # Types - Numeric
    "Int16",
    "UInt16",
    "Int32",
    "UInt32",
    "Float32",
    "Int64",
    "UInt64",
    "Float64",
    # Types - Dynamic
    "DynamicInt",
    "DynamicUInt",
    # Types - String
    "ModbusString",
    # Codec
    "ModbusCodec",
    # Clients
    "AsyncModbusClientBase",
    "PymodbusTcpClient",
    "PymodbusRtuClient",
    "SharedPymodbusTcpClient",
]
