# =============== Modbus Data Types - Base ===============
#
# 資料類型抽象基底類別
#
# 所有 Modbus 資料類型必須繼承此類別並實作：
#   - register_count: 所需暫存器數量
#   - encode(): 將 Python 值編碼為暫存器列表
#   - decode(): 將暫存器列表解碼為 Python 值

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..enums import ByteOrder, RegisterOrder


class ModbusDataType(ABC):
    """
    Modbus 資料類型抽象基底類別

    定義所有資料類型必須實作的介面。
    子類別包含固定長度類型 (Int16, UInt32 等) 與動態長度類型 (DynamicInt, ModbusString)。

    使用範例：
        >>> from csp_lib.modbus import UInt16, ModbusCodec
        >>> codec = ModbusCodec()
        >>> registers = codec.encode(UInt16(), 1234)
        >>> value = codec.decode(UInt16(), registers)
    """

    @property
    @abstractmethod
    def register_count(self) -> int:
        """
        所需的暫存器數量

        每個 Modbus 暫存器為 16 bits (2 bytes)。
        例如：
            - Int16 需要 1 個暫存器
            - Int32 需要 2 個暫存器
            - 動態長度類型依據初始化參數決定

        Returns:
            暫存器數量
        """

    @abstractmethod
    def encode(
        self,
        value: Any,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        """
        將 Python 值編碼為暫存器值列表

        Args:
            value: 要編碼的 Python 值
            byte_order: 位元組順序
            register_order: 暫存器順序

        Returns:
            暫存器值列表，每個元素為 0-65535 範圍的整數

        Raises:
            ModbusEncodeError: 編碼失敗時拋出
        """

    @abstractmethod
    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> Any:
        """
        將暫存器值列表解碼為 Python 值

        Args:
            registers: 暫存器值列表
            byte_order: 位元組順序
            register_order: 暫存器順序

        Returns:
            解碼後的 Python 值

        Raises:
            ModbusDecodeError: 解碼失敗時拋出
        """


__all__ = ["ModbusDataType"]
