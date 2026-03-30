# =============== Modbus Gateway - Errors ===============
#
# Gateway 專用例外層次結構
#
# 提供可程式化的例外類別：
#   - GatewayError: Gateway 層基礎例外
#   - RegisterConflictError: 暫存器位址空間衝突
#   - WriteRejectedError: 寫入被驗證鏈拒絕

from __future__ import annotations


class GatewayError(Exception):
    """Base exception for all modbus_gateway errors."""


class RegisterConflictError(GatewayError):
    """Raised when register definitions overlap in address space.

    Attributes:
        name_a: Name of the first conflicting register.
        name_b: Name of the second conflicting register.
        overlap_start: Start address of the overlap region.
        overlap_end: End address of the overlap region.
    """

    def __init__(self, name_a: str, name_b: str, overlap_start: int, overlap_end: int) -> None:
        self.name_a = name_a
        self.name_b = name_b
        self.overlap_start = overlap_start
        self.overlap_end = overlap_end
        super().__init__(
            f"Register overlap: '{name_a}' and '{name_b}' conflict at addresses {overlap_start}-{overlap_end}"
        )


class WriteRejectedError(GatewayError):
    """Raised when a write is rejected by the validation chain.

    Attributes:
        address: The register address that was targeted.
        reason: Human-readable rejection reason.
    """

    def __init__(self, address: int, reason: str) -> None:
        self.address = address
        self.reason = reason
        super().__init__(f"Write to address {address} rejected: {reason}")


__all__ = [
    "GatewayError",
    "RegisterConflictError",
    "WriteRejectedError",
]
