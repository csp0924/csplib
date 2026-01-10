# =============== Modbus Data Types - Dynamic ===============
#
# 動態長度整數類型實作
#
# 支援任意 16 的倍數位元寬度：
#   - DynamicInt: 動態長度有號整數
#   - DynamicUInt: 動態長度無號整數
#
# 使用範例：
#   uint48 = DynamicUInt(48)  # 48-bit 無號整數，需要 3 個暫存器

from __future__ import annotations

from ..enums import ByteOrder, RegisterOrder
from ..exceptions import ModbusConfigError, ModbusDecodeError, ModbusEncodeError
from .base import ModbusDataType


class DynamicInt(ModbusDataType):
    """
    動態長度有號整數

    支援任意 16 的倍數位元寬度。

    Args:
        bit_width: 位元寬度，必須為 16 的倍數

    Raises:
        ModbusConfigError: bit_width 非 16 的倍數

    使用範例：
        >>> int48 = DynamicInt(48)
        >>> int48.register_count
        3
    """

    def __init__(self, bit_width: int) -> None:
        if bit_width <= 0:
            raise ModbusConfigError(f"bit_width 必須為正整數，收到: {bit_width}")
        if bit_width % 16 != 0:
            raise ModbusConfigError(f"bit_width 必須為 16 的倍數，收到: {bit_width}")

        self._bit_width = bit_width
        self._register_count = bit_width // 16

        # 計算有號整數範圍
        self._max_value = (1 << (bit_width - 1)) - 1
        self._min_value = -(1 << (bit_width - 1))

    @property
    def register_count(self) -> int:
        return self._register_count

    @property
    def bit_width(self) -> int:
        """位元寬度"""
        return self._bit_width

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(
                f"DynamicInt({self._bit_width}) 需要整數，收到: {type(value).__name__}"
            )
        if not self._min_value <= value <= self._max_value:
            raise ModbusEncodeError(
                f"DynamicInt({self._bit_width}) 範圍為 "
                f"{self._min_value}~{self._max_value}，收到: {value}"
            )

        # 處理負數：轉換為補數表示
        if value < 0:
            value = (1 << self._bit_width) + value

        # 將整數分割為多個 16-bit 暫存器 (LSW first)
        registers = []
        for _ in range(self._register_count):
            registers.append(value & 0xFFFF)
            value >>= 16

        # 預設 LSW first，若 HIGH_FIRST 則反轉為 MSW first
        if register_order == RegisterOrder.HIGH_FIRST:
            registers.reverse()


        return registers

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < self._register_count:
            raise ModbusDecodeError(
                f"DynamicInt({self._bit_width}) 需要 {self._register_count} 個暫存器，"
                f"收到: {len(registers)}"
            )

        regs = list(registers[: self._register_count])

        # 還原順序：若 HIGH_FIRST 則反轉回 LSW first 以便組合
        if register_order == RegisterOrder.HIGH_FIRST:
            regs.reverse()

        # 組合為整數 (從 LSW 開始)
        value = 0
        for i, reg in enumerate(regs):
            value |= reg << (16 * i)

        # 處理負數：從補數還原
        if value >= (1 << (self._bit_width - 1)):
            value -= 1 << self._bit_width

        return value


class DynamicUInt(ModbusDataType):
    """
    動態長度無號整數

    支援任意 16 的倍數位元寬度。

    Args:
        bit_width: 位元寬度，必須為 16 的倍數

    Raises:
        ModbusConfigError: bit_width 非 16 的倍數

    使用範例：
        >>> uint48 = DynamicUInt(48)
        >>> uint48.register_count
        3
    """

    def __init__(self, bit_width: int) -> None:
        if bit_width <= 0:
            raise ModbusConfigError(f"bit_width 必須為正整數，收到: {bit_width}")
        if bit_width % 16 != 0:
            raise ModbusConfigError(f"bit_width 必須為 16 的倍數，收到: {bit_width}")

        self._bit_width = bit_width
        self._register_count = bit_width // 16

        # 計算無號整數範圍
        self._max_value = (1 << bit_width) - 1

    @property
    def register_count(self) -> int:
        return self._register_count

    @property
    def bit_width(self) -> int:
        """位元寬度"""
        return self._bit_width

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(
                f"DynamicUInt({self._bit_width}) 需要整數，收到: {type(value).__name__}"
            )
        if not 0 <= value <= self._max_value:
            raise ModbusEncodeError(
                f"DynamicUInt({self._bit_width}) 範圍為 0~{self._max_value}，收到: {value}"
            )

        # 將整數分割為多個 16-bit 暫存器 (LSW first)
        registers = []
        for _ in range(self._register_count):
            registers.append(value & 0xFFFF)
            value >>= 16

        # 預設 LSW first，若 HIGH_FIRST 則反轉為 MSW first
        if register_order == RegisterOrder.HIGH_FIRST:
            registers.reverse()

        return registers

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < self._register_count:
            raise ModbusDecodeError(
                f"DynamicUInt({self._bit_width}) 需要 {self._register_count} 個暫存器，"
                f"收到: {len(registers)}"
            )

        regs = list(registers[: self._register_count])

        # 還原順序：若 HIGH_FIRST 則反轉回 LSW first 以便組合
        if register_order == RegisterOrder.HIGH_FIRST:
            regs.reverse()

        # 組合為整數 (從 LSW 開始)
        value = 0
        for i, reg in enumerate(regs):
            value |= reg << (16 * i)

        return value


__all__ = [
    "DynamicInt",
    "DynamicUInt",
]
