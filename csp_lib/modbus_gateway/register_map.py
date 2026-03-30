# =============== Modbus Gateway - Register Map ===============
#
# Gateway 暫存器位址空間管理器
#
# 負責：
#   - 維護 Holding Register (HR) 與 Input Register (IR) 兩組獨立的原始暫存器陣列
#   - 將命名暫存器映射到位址
#   - 透過 ModbusCodec 進行編解碼
#   - 套用 scale factor (stored = physical * scale)
#   - 使用 threading.Lock 保障執行緒安全

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

from csp_lib.core import get_logger
from csp_lib.modbus import ModbusCodec
from csp_lib.modbus_gateway.config import GatewayRegisterDef, GatewayServerConfig, RegisterType
from csp_lib.modbus_gateway.errors import RegisterConflictError

logger = get_logger(__name__)


class GatewayRegisterMap:
    """Register address space manager for the gateway.

    Maintains two separate raw register arrays (one for Holding Registers,
    one for Input Registers), maps named registers to addresses, handles
    encode/decode via ``ModbusCodec``, and applies scale factors.

    Thread-safe: all public methods acquire ``threading.Lock`` before
    accessing the underlying register arrays.

    Args:
        config: Gateway server configuration providing defaults for byte
            order, register order, and address space size.
        register_defs: Sequence of register definitions to manage.

    Raises:
        RegisterConflictError: If any two register definitions overlap
            within the same address space.
        ValueError: If a register name is duplicated or address exceeds
            the configured space size.
    """

    def __init__(self, config: GatewayServerConfig, register_defs: Sequence[GatewayRegisterDef]) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._size = config.register_space_size
        self._hr_regs: list[int] = [0] * self._size
        self._ir_regs: list[int] = [0] * self._size
        self._defs: dict[str, GatewayRegisterDef] = {}
        self._codec = ModbusCodec()

        # Register all definitions (validates uniqueness and overlap)
        for reg_def in register_defs:
            self._register(reg_def)

        # Initialize registers with initial_value
        for reg_def in register_defs:
            if reg_def.initial_value is not None:
                self._set_value_unlocked(reg_def, reg_def.initial_value)

    # ------------------------------------------------------------------
    # Registration (called only from __init__, no lock needed)
    # ------------------------------------------------------------------

    def _register(self, reg_def: GatewayRegisterDef) -> None:
        """Register a definition, checking name uniqueness and address overlap.

        Args:
            reg_def: The register definition to add.

        Raises:
            ValueError: If the name is already registered or the address
                range exceeds the configured space size.
            RegisterConflictError: If the address range overlaps with an
                existing definition in the same register type.
        """
        if reg_def.name in self._defs:
            raise ValueError(f"Duplicate register name: {reg_def.name}")

        new_start = reg_def.address
        new_end = new_start + reg_def.data_type.register_count - 1

        # Validate address fits within space
        if new_end >= self._size:
            raise ValueError(f"Register '{reg_def.name}' address {new_start}-{new_end} exceeds space size {self._size}")

        # Check overlap within same register type
        for existing in self._defs.values():
            if existing.register_type != reg_def.register_type:
                continue
            ex_start = existing.address
            ex_end = ex_start + existing.data_type.register_count - 1
            if new_start <= ex_end and ex_start <= new_end:
                raise RegisterConflictError(
                    existing.name,
                    reg_def.name,
                    max(new_start, ex_start),
                    min(new_end, ex_end),
                )

        self._defs[reg_def.name] = reg_def

    # ------------------------------------------------------------------
    # Public API (thread-safe)
    # ------------------------------------------------------------------

    def set_value(self, name: str, physical_value: Any) -> None:
        """Set register value by name using physical units.

        The physical value is multiplied by the register's scale factor
        before being encoded and stored in the raw register array.

        Args:
            name: Logical register name.
            physical_value: Value in physical/engineering units.

        Raises:
            KeyError: If no register with the given name exists.
        """
        reg_def = self._defs[name]
        with self._lock:
            self._set_value_unlocked(reg_def, physical_value)

    def get_value(self, name: str) -> Any:
        """Get register value by name in physical units.

        The raw stored value is decoded and then divided by the scale
        factor to produce the physical value.

        Args:
            name: Logical register name.

        Returns:
            The current value in physical/engineering units.

        Raises:
            KeyError: If no register with the given name exists.
        """
        reg_def = self._defs[name]
        with self._lock:
            return self._get_value_unlocked(reg_def)

    def get_all_values(self) -> dict[str, Any]:
        """Get all register values as ``{name: physical_value}``.

        Returns:
            Dictionary mapping each register name to its current physical value.
        """
        with self._lock:
            return {name: self._get_value_unlocked(reg_def) for name, reg_def in self._defs.items()}

    # ------------------------------------------------------------------
    # Raw register access (thread-safe)
    # ------------------------------------------------------------------

    def get_hr_raw(self, address: int, count: int) -> list[int]:
        """Get raw holding register values.

        Args:
            address: Starting register address (0-based).
            count: Number of registers to read.

        Returns:
            List of raw 16-bit register values.
        """
        with self._lock:
            return self._hr_regs[address : address + count]

    def set_hr_raw(self, address: int, values: list[int]) -> None:
        """Set raw holding register values.

        Args:
            address: Starting register address (0-based).
            values: List of raw 16-bit register values to write.
        """
        with self._lock:
            self._hr_regs[address : address + len(values)] = values

    def get_ir_raw(self, address: int, count: int) -> list[int]:
        """Get raw input register values.

        Args:
            address: Starting register address (0-based).
            count: Number of registers to read.

        Returns:
            List of raw 16-bit register values.
        """
        with self._lock:
            return self._ir_regs[address : address + count]

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def find_affected_registers(
        self, address: int, count: int, register_type: RegisterType
    ) -> list[GatewayRegisterDef]:
        """Find all register definitions affected by a raw write.

        A register is considered affected if its address range overlaps
        with ``[address, address + count)``.

        Args:
            address: Starting address of the write.
            count: Number of registers being written.
            register_type: Which address space to search (HOLDING or INPUT).

        Returns:
            List of affected register definitions.
        """
        affected: list[GatewayRegisterDef] = []
        write_end = address + count - 1
        for reg_def in self._defs.values():
            if reg_def.register_type != register_type:
                continue
            reg_start = reg_def.address
            reg_end = reg_start + reg_def.data_type.register_count - 1
            if reg_start <= write_end and address <= reg_end:
                affected.append(reg_def)
        return affected

    def get_register_def(self, name: str) -> GatewayRegisterDef:
        """Look up a register definition by name.

        Args:
            name: Logical register name.

        Returns:
            The corresponding register definition.

        Raises:
            KeyError: If no register with the given name exists.
        """
        return self._defs[name]

    @property
    def register_defs(self) -> dict[str, GatewayRegisterDef]:
        """All register definitions as a shallow copy."""
        return dict(self._defs)

    # ------------------------------------------------------------------
    # Internal (caller must hold self._lock)
    # ------------------------------------------------------------------

    def _set_value_unlocked(self, reg_def: GatewayRegisterDef, physical_value: Any) -> None:
        """Encode and write a value to the correct register array.

        Applies scale factor: ``stored = physical_value * scale``.
        For integer data types the scaled value is rounded to the nearest
        integer before encoding.

        Args:
            reg_def: The target register definition.
            physical_value: Value in physical/engineering units.
        """
        scaled = float(physical_value) * reg_def.scale

        # Integer Modbus types (Int16, UInt16, etc.) require int values.
        # Round to nearest int when the scaled result is effectively whole.
        rounded = round(scaled)
        if abs(scaled - rounded) < 1e-9:
            scaled_value: int | float = rounded
        else:
            scaled_value = scaled

        bo = reg_def.byte_order or self._config.byte_order
        ro = reg_def.register_order or self._config.register_order
        encoded = self._codec.encode(reg_def.data_type, scaled_value, bo, ro)

        regs = self._hr_regs if reg_def.register_type == RegisterType.HOLDING else self._ir_regs
        regs[reg_def.address : reg_def.address + len(encoded)] = encoded

    def _get_value_unlocked(self, reg_def: GatewayRegisterDef) -> Any:
        """Decode a value from the correct register array.

        Applies inverse scale: ``physical = stored / scale``.

        Args:
            reg_def: The target register definition.

        Returns:
            The decoded value in physical/engineering units.
        """
        bo = reg_def.byte_order or self._config.byte_order
        ro = reg_def.register_order or self._config.register_order

        regs = self._hr_regs if reg_def.register_type == RegisterType.HOLDING else self._ir_regs
        count = reg_def.data_type.register_count
        raw = regs[reg_def.address : reg_def.address + count]

        decoded = self._codec.decode(reg_def.data_type, raw, bo, ro)
        if reg_def.scale != 1.0:
            return decoded / reg_def.scale
        return decoded


__all__ = [
    "GatewayRegisterMap",
]
