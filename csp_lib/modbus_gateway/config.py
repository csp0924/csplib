# =============== Modbus Gateway - Config ===============
#
# Gateway 組態資料類別（frozen dataclass）
#
# 提供：
#   - RegisterType: 暫存器類型列舉（Holding / Input）
#   - GatewayRegisterDef: 單一暫存器定義
#   - WatchdogConfig: 通訊看門狗組態
#   - GatewayServerConfig: Gateway 伺服器整體組態

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from csp_lib.modbus import ByteOrder, ModbusDataType, RegisterOrder


class RegisterType(Enum):
    """Register type determines read/write capabilities.

    Attributes:
        HOLDING: Read (FC03) and write (FC06/FC16) capable.
        INPUT: Read-only (FC04).
    """

    HOLDING = "holding"
    INPUT = "input"


@dataclass(frozen=True, slots=True)
class GatewayRegisterDef:
    """Single register definition within the gateway address space.

    Attributes:
        name: Unique logical name for this register.
        address: Starting Modbus address (0-based).
        data_type: Modbus data type instance defining encoding/decoding.
        register_type: Whether this register is holding or input.
        scale: Scale factor applied on read/write (must not be zero).
        unit: Engineering unit string (e.g. "kW", "Hz").
        initial_value: Value to initialize the register with.
        description: Human-readable description.
        byte_order: Per-register byte order override (None = use server default).
        register_order: Per-register register order override (None = use server default).
    """

    name: str
    address: int
    data_type: ModbusDataType
    register_type: RegisterType = RegisterType.HOLDING
    scale: float = 1.0
    unit: str = ""
    initial_value: Any = 0
    description: str = ""
    byte_order: ByteOrder | None = None
    register_order: RegisterOrder | None = None

    def __post_init__(self) -> None:
        if self.address < 0:
            raise ValueError(f"address must be >= 0, got {self.address}")
        if self.scale == 0:
            raise ValueError("scale must not be zero")


@dataclass(frozen=True, slots=True)
class WatchdogConfig:
    """Communication watchdog configuration.

    The watchdog monitors EMS heartbeat activity. If no communication
    is received within ``timeout_seconds``, the gateway can take
    protective action (e.g. revert to safe defaults).

    Attributes:
        timeout_seconds: Maximum idle time before timeout (must be > 0).
        check_interval: How often to check for timeout (must be > 0).
        enabled: Whether the watchdog is active.
    """

    timeout_seconds: float = 60.0
    check_interval: float = 5.0
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be > 0, got {self.timeout_seconds}")
        if self.check_interval <= 0:
            raise ValueError(f"check_interval must be > 0, got {self.check_interval}")


@dataclass(frozen=True, slots=True)
class GatewayServerConfig:
    """Top-level ModbusGatewayServer configuration.

    Attributes:
        host: IP address to bind the Modbus TCP server.
        port: TCP port number (0-65535).
        unit_id: Modbus slave/unit ID (1-247).
        byte_order: Default byte order for all registers.
        register_order: Default register order for multi-register types.
        register_space_size: Total register address space size.
        watchdog: Communication watchdog configuration.
    """

    host: str = "0.0.0.0"
    port: int = 502
    unit_id: int = 1
    byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    register_order: RegisterOrder = RegisterOrder.HIGH_FIRST
    register_space_size: int = 10000
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)

    def __post_init__(self) -> None:
        if not (1 <= self.unit_id <= 247):
            raise ValueError(f"unit_id must be 1-247, got {self.unit_id}")
        if self.port < 0 or self.port > 65535:
            raise ValueError(f"port must be 0-65535, got {self.port}")


@dataclass(frozen=True, slots=True)
class WriteRule:
    """Write validation rule for a specific holding register.

    Defines constraints on values that EMS can write. Used by WritePipeline.

    Attributes:
        register_name: Target register name (must match a GatewayRegisterDef.name).
        min_value: Minimum allowed physical value. None = no lower bound.
        max_value: Maximum allowed physical value. None = no upper bound.
        clamp: If True, out-of-range values are clamped; if False, write is rejected.
    """

    register_name: str
    min_value: float | None = None
    max_value: float | None = None
    clamp: bool = False

    def __post_init__(self) -> None:
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError(f"min_value must be <= max_value, got min={self.min_value} max={self.max_value}")

    def apply(self, name: str, value: float) -> tuple[float, bool]:
        """Apply rule: return (possibly_clamped_value, rejected)."""
        if self.min_value is not None and value < self.min_value:
            return (self.min_value, False) if self.clamp else (value, True)
        if self.max_value is not None and value > self.max_value:
            return (self.max_value, False) if self.clamp else (value, True)
        return value, False


__all__ = [
    "GatewayRegisterDef",
    "GatewayServerConfig",
    "RegisterType",
    "WatchdogConfig",
    "WriteRule",
]
