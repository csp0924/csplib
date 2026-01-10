# =============== Modbus Data Types - String ===============
#
# 字串類型實作
#
# 支援 ASCII 與 UTF-8 編碼的動態長度字串

from __future__ import annotations

from ..enums import ByteOrder, RegisterOrder
from ..exceptions import ModbusConfigError, ModbusDecodeError, ModbusEncodeError
from .base import ModbusDataType


class ModbusString(ModbusDataType):
    """
    Modbus 字串類型

    將字串編碼為暫存器，每個暫存器可存放 2 個位元組。
    解碼時會自動去除尾部的 null 字元與空白。

    Args:
        max_length: 最大字元數
        encoding: 字元編碼，預設 "ascii"

    Raises:
        ModbusConfigError: max_length 非正整數

    使用範例：
        >>> name = ModbusString(16)
        >>> name.register_count
        8
    """

    def __init__(self, max_length: int, encoding: str = "ascii") -> None:
        if max_length <= 0:
            raise ModbusConfigError(f"max_length 必須為正整數，收到: {max_length}")

        self._max_length = max_length
        self._encoding = encoding
        # 每個暫存器 2 bytes，向上取整
        self._register_count = (max_length + 1) // 2

    @property
    def register_count(self) -> int:
        return self._register_count

    @property
    def max_length(self) -> int:
        """最大字元數"""
        return self._max_length

    @property
    def encoding(self) -> str:
        """字元編碼"""
        return self._encoding

    def encode(
        self,
        value: str,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, str):
            raise ModbusEncodeError(
                f"ModbusString 需要字串，收到: {type(value).__name__}"
            )

        # 編碼為 bytes
        try:
            encoded = value.encode(self._encoding)
        except UnicodeEncodeError as e:
            raise ModbusEncodeError(
                f"無法使用 {self._encoding} 編碼字串: {e}"
            ) from e

        if len(encoded) > self._max_length:
            raise ModbusEncodeError(
                f"字串長度超過上限 {self._max_length}，實際: {len(encoded)}"
            )

        # 補齊到偶數長度 (每個暫存器 2 bytes)
        padded_length = self._register_count * 2
        encoded = encoded.ljust(padded_length, b"\x00")

        # 將每 2 bytes 轉換為一個暫存器值
        registers = []
        for i in range(0, padded_length, 2):
            if byte_order == ByteOrder.BIG_ENDIAN:
                # 高位元組在前
                reg_value = (encoded[i] << 8) | encoded[i + 1]
            else:
                # 低位元組在前
                reg_value = encoded[i] | (encoded[i + 1] << 8)
            registers.append(reg_value)

        # 根據 register_order 調整暫存器順序
        if register_order == RegisterOrder.LOW_FIRST:
            registers.reverse()

        return registers

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> str:
        if len(registers) < self._register_count:
            raise ModbusDecodeError(
                f"ModbusString({self._max_length}) 需要 {self._register_count} 個暫存器，"
                f"收到: {len(registers)}"
            )

        # 取得所需的暫存器並根據 register_order 還原順序
        regs = list(registers[: self._register_count])
        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()

        # 將暫存器還原為 bytes
        data = bytearray()
        for reg in regs:
            if byte_order == ByteOrder.BIG_ENDIAN:
                data.append((reg >> 8) & 0xFF)
                data.append(reg & 0xFF)
            else:
                data.append(reg & 0xFF)
                data.append((reg >> 8) & 0xFF)

        # 解碼為字串，去除尾部 null 字元
        try:
            decoded = bytes(data).decode(self._encoding)
        except UnicodeDecodeError as e:
            raise ModbusDecodeError(
                f"無法使用 {self._encoding} 解碼資料: {e}"
            ) from e

        # 去除尾部 null 字元與空白
        return decoded.rstrip("\x00").rstrip()


__all__ = ["ModbusString"]

