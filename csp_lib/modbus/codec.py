# =============== Modbus Codec ===============
#
# 高階編解碼器
#
# 提供簡潔的 API 封裝資料類型的 encode/decode 操作：
#   - encode(): 編碼單一值
#   - decode(): 解碼單一值

from __future__ import annotations

from typing import Any

from .enums import ByteOrder, RegisterOrder
from .exceptions import ModbusDecodeError, ModbusEncodeError
from .types import ModbusDataType


class ModbusCodec:
    """
    Modbus 編解碼器

    封裝 byte_order 與 register_order 設定，
    提供簡潔的 encode/decode API。

    Args:
        byte_order: 位元組順序，預設大端序
        register_order: 暫存器順序，預設高位優先

    使用範例：
        >>> from csp_lib.modbus import ModbusCodec, UInt32
        >>> codec = ModbusCodec()
        >>> registers = codec.encode(UInt32(), 0x12345678)
        >>> print(registers)  # [0x1234, 0x5678]
        >>> value = codec.decode(UInt32(), registers)
        >>> print(value)  # 305419896
    """

    def encode(
        self,
        data_type: ModbusDataType,
        value: Any,
        byte_order: ByteOrder | None = None,
        register_order: RegisterOrder | None = None,
    ) -> list[int]:
        """
        編碼單一值

        Args:
            data_type: 資料類型實例
            value: 要編碼的值
            byte_order: 位元組順序
            register_order: 暫存器順序

        Returns:
            暫存器值列表

        Raises:
            ModbusEncodeError: 編碼失敗
        """
        try:
            return data_type.encode(
                value,
                byte_order or ByteOrder.BIG_ENDIAN,
                register_order or RegisterOrder.HIGH_FIRST,
            )
        except ModbusEncodeError as e:
            raise e
        except Exception as e:
            raise ModbusEncodeError(f"編碼失敗: {e}") from e

    def decode(
        self,
        data_type: ModbusDataType,
        registers: list[int],
        byte_order: ByteOrder | None = None,
        register_order: RegisterOrder | None = None,
    ) -> Any:
        """
        解碼暫存器列表

        Args:
            data_type: 資料類型實例
            registers: 暫存器值列表
            byte_order: 位元組順序
            register_order: 暫存器順序

        Returns:
            Python 值

        Raises:
            ModbusDecodeError: 解碼失敗
        """
        try:
            return data_type.decode(
                registers,
                byte_order or ByteOrder.BIG_ENDIAN,
                register_order or RegisterOrder.HIGH_FIRST,
            )
        except ModbusDecodeError as e:
            raise e
        except Exception as e:
            raise ModbusDecodeError(f"解碼失敗: {e}") from e


__all__ = [
    "ModbusCodec",
]
