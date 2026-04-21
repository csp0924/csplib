# =============== Modbus Clients Module ===============
#
# Client 子模組匯出
#
# 提供 pymodbus 非同步客戶端：
#   - PymodbusTcpClient: TCP 客戶端 (獨立連線，支援多工)
#   - SharedPymodbusTcpClient: TCP 共用連線客戶端 (TCP-RS485 轉換器用)
#   - PymodbusRtuClient: RTU 客戶端 (含 ModbusRequestQueue)
#
# 版本相容性：
#   - 支援 pymodbus >= 3.0.0
#   - 自動適配 3.10.0+ API 變更 (slave → device_id)

from .base import AsyncModbusClientBase
from .client import PymodbusRtuClient, PymodbusTcpClient, SharedPymodbusTcpClient
from .queue import (
    CircuitBreakerState,
    ModbusRequestQueue,
    RequestPriority,
    RequestQueueConfig,
)

__all__ = [
    # Base
    "AsyncModbusClientBase",
    # Queue
    "RequestQueueConfig",
    "RequestPriority",
    "CircuitBreakerState",
    "ModbusRequestQueue",
    # Clients
    "PymodbusTcpClient",
    "SharedPymodbusTcpClient",
    "PymodbusRtuClient",
]
