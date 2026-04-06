# =============== CAN - Exceptions ===============
#
# CAN Bus 例外層次結構

from __future__ import annotations


class CANError(Exception):
    """CAN Bus 基礎例外"""

    def __init__(
        self,
        message: str = "",
        *,
        can_id: int | None = None,
        bus_index: int | None = None,
    ) -> None:
        self.can_id = can_id
        self.bus_index = bus_index
        parts: list[str] = []
        if bus_index is not None:
            parts.append(f"bus={bus_index}")
        if can_id is not None:
            parts.append(f"can_id=0x{can_id:03X}")
        prefix = f"[{', '.join(parts)}] " if parts else ""
        super().__init__(f"{prefix}{message}")


class CANConnectionError(CANError):
    """CAN Bus 連線錯誤"""


class CANTimeoutError(CANError):
    """CAN Bus 逾時錯誤"""


class CANSendError(CANError):
    """CAN Bus 發送錯誤"""


__all__ = [
    "CANError",
    "CANConnectionError",
    "CANTimeoutError",
    "CANSendError",
]
