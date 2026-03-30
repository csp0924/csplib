# =============== Modbus Gateway - Validators ===============
#
# 內建 WriteValidator 實作
#
# 提供可組合的寫入驗證器：
#   - AddressWhitelistValidator: 只允許白名單中的暫存器被寫入

from __future__ import annotations

from typing import Any

from csp_lib.core import get_logger

logger = get_logger(__name__)


class AddressWhitelistValidator:
    """Rejects writes to registers not in the whitelist.

    Satisfies the :class:`~csp_lib.modbus_gateway.protocol.WriteValidator`
    protocol.

    Args:
        allowed: Set of register names that are allowed to be written.

    Example::

        validator = AddressWhitelistValidator({"active_power_setpoint", "reactive_power_setpoint"})
        assert validator.validate("active_power_setpoint", 100) is True
        assert validator.validate("firmware_version", 42) is False
    """

    def __init__(self, allowed: set[str]) -> None:
        self._allowed: frozenset[str] = frozenset(allowed)

    def validate(self, register_name: str, value: Any) -> bool:
        """Check whether the write should be accepted.

        Args:
            register_name: Logical name of the target register.
            value: The proposed write value (already decoded).

        Returns:
            ``True`` if *register_name* is in the whitelist, ``False`` otherwise.
        """
        if register_name not in self._allowed:
            logger.debug(f"Write rejected by whitelist: {register_name}")
            return False
        return True


__all__ = [
    "AddressWhitelistValidator",
]
