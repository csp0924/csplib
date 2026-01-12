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
# Clients
from .clients import (
    AsyncModbusClientBase,
    PymodbusRtuClient,
    PymodbusTcpClient,
    SharedPymodbusTcpClient,
)

# Codec
from .codec import ModbusCodec

# Config
from .config import (
    ModbusRtuConfig,
    ModbusTcpConfig,
)

# Enums
from .enums import (
    ByteOrder,
    FunctionCode,
    Parity,
    RegisterOrder,
)
from .exceptions import (
    ModbusConfigError,
    ModbusDecodeError,
    ModbusEncodeError,
    ModbusError,
)

# Types
from .types import (
    DynamicInt,
    DynamicUInt,
    Float32,
    Float64,
    Int16,
    Int32,
    Int64,
    ModbusDataType,
    ModbusString,
    UInt16,
    UInt32,
    UInt64,
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
