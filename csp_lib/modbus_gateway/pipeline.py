"""
Write processing pipeline.

處理 EMS 寫入的完整管線：
  1. 解碼 raw registers → physical value
  2. WriteValidator chain — 全部 accept 才繼續
  3. WriteRule clamp/reject — 範圍限制
  4. 更新 GatewayRegisterMap
  5. 收集變更 → 供 DataBlock dispatch hooks
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from csp_lib.core import get_logger
from csp_lib.modbus import ModbusCodec
from csp_lib.modbus_gateway.config import RegisterType

logger = get_logger(__name__)


class WritePipeline:
    """
    Write processing pipeline.

    Processes an incoming write through:
    1. Decode raw registers → physical value
    2. WriteValidator chain (all must accept)
    3. WriteRule clamp/reject (per-register rules)
    4. Register update
    5. Return changes list for hook dispatch

    The pipeline is constructed by ModbusGatewayServer and passed to GatewayDataBlock.
    """

    def __init__(
        self,
        register_map: Any,  # GatewayRegisterMap (avoid circular import)
        write_rules: Mapping[str, Any] | None = None,
    ) -> None:
        self._register_map = register_map
        self._write_rules: dict[str, Any] = dict(write_rules) if write_rules else {}
        self._validators: list[Any] = []  # WriteValidator instances
        self._hooks: list[Any] = []  # WriteHook instances
        self._codec = ModbusCodec()
        self._default_byte_order = register_map.default_byte_order
        self._default_register_order = register_map.default_register_order

    def add_validator(self, validator: Any) -> None:
        """Add a write validator."""
        self._validators.append(validator)

    def add_hook(self, hook: Any) -> None:
        """Add a write hook."""
        self._hooks.append(hook)

    @property
    def hooks(self) -> list[Any]:
        """All registered hooks."""
        return list(self._hooks)

    def process_write(self, address: int, values: list[int]) -> list[tuple[str, Any, Any]]:
        """
        Process a raw write from pymodbus (called from server thread).

        Args:
            address: Starting register address
            values: Raw register values (list of uint16)

        Returns:
            List of (register_name, old_value, new_value) for successful writes.
            Empty list if all writes were rejected.
        """
        # Find affected register definitions
        affected = self._register_map.find_affected_registers(address, len(values), RegisterType.HOLDING)
        if not affected:
            return []

        changes: list[tuple[str, Any, Any]] = []

        for reg_def in affected:
            # Decode new physical value from the raw write
            reg_start = reg_def.address
            reg_count = reg_def.data_type.register_count
            # Extract the portion of values that covers this register
            offset = reg_start - address
            if offset < 0 or offset + reg_count > len(values):
                continue  # Partial write doesn't fully cover this register
            raw_slice = values[offset : offset + reg_count]

            # Decode to physical value
            bo = reg_def.byte_order or self._default_byte_order
            ro = reg_def.register_order or self._default_register_order
            decoded = self._codec.decode(reg_def.data_type, raw_slice, bo, ro)
            physical = decoded / reg_def.scale if reg_def.scale != 1.0 else decoded

            # Read old value
            old_value = self._register_map.get_value(reg_def.name)

            # 1. Validator chain
            rejected = False
            for validator in self._validators:
                if not validator.validate(reg_def.name, physical):
                    logger.debug(f"Write rejected by {type(validator).__name__}: {reg_def.name}={physical}")
                    rejected = True
                    break
            if rejected:
                continue

            # 2. WriteRule clamp/reject
            rule = self._write_rules.get(reg_def.name)
            if rule is not None:
                physical, rule_rejected = self._apply_rule(rule, reg_def.name, physical)
                if rule_rejected:
                    continue

            # 3. Update register
            self._register_map.set_value(reg_def.name, physical)
            new_value = physical

            if old_value != new_value:
                changes.append((reg_def.name, old_value, new_value))

        return changes

    def _apply_rule(self, rule: Any, name: str, value: float) -> tuple[float, bool]:
        """Apply a WriteRule-compatible object to a value.

        Args:
            rule: Any object implementing the ``WriteRule`` protocol (has an ``apply`` method).
            name: Logical register name (for logging).
            value: The proposed write value.

        Returns:
            Tuple of (possibly_transformed_value, rejected).
        """
        return rule.apply(name, value)


__all__ = ["WritePipeline"]
