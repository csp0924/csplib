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


class RegisterNotWritableError(WriteRejectedError):
    """Logged when EMS attempts to write a register whose ``writable`` flag is ``False``.

    預設所有 HOLDING register 的 ``writable=False``；register 擁有者必須
    顯式 opt-in 允許 EMS 寫入。WritePipeline 在解碼後、validator chain
    之前即時檢查此旗標，不符者直接拒絕並記錄 warning（**不 raise，也不向
    Modbus client 回傳 exception**；client 端看到的是寫入後讀回仍為舊值）。

    此例外類別作為日誌訊息與 audit record 的載體存在。若需向 client 回傳
    Modbus exception code，需於 DataBlock/管線層額外接線。

    Attributes:
        register_name: Logical name of the rejected register.
        address: The register address that was targeted.
    """

    def __init__(self, register_name: str, address: int) -> None:
        self.register_name = register_name
        super().__init__(
            address,
            f"register '{register_name}' is not writable (writable=False)",
        )


__all__ = [
    "GatewayError",
    "RegisterConflictError",
    "RegisterNotWritableError",
    "WriteRejectedError",
]
