# =============== Equipment Processing - Decoder ===============
#
# 解碼器 - 橋接 csp_lib.modbus
#
# 將 Modbus 暫存器列表解碼為 Python 值

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from csp_lib.modbus import ByteOrder, ModbusDataType, RegisterOrder


@dataclass
class ModbusDecoder:
    """
    Modbus 資料類型解碼器

    將暫存器列表解碼為 Python 值，橋接 csp_lib.modbus 類型系統。

    Attributes:
        data_type: Modbus 資料類型
        byte_order: 位元組順序
        register_order: 暫存器順序
    """

    data_type: ModbusDataType
    byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    register_order: RegisterOrder = RegisterOrder.HIGH_FIRST

    def apply(self, value: Iterable[Any]) -> Any:
        if not isinstance(value, (list, tuple)):
            raise TypeError(f"ModbusDecoder 需要暫存器列表，收到: {type(value).__name__}")

        if len(value) != self.data_type.register_count:
            raise ValueError(f"ModbusDecoder 需要 {self.data_type.register_count} 個暫存器，收到: {len(value)}")

        return self.data_type.decode(
            list(value),
            byte_order=self.byte_order,
            register_order=self.register_order,
        )


@dataclass
class ModbusEncoder:
    """
    Modbus 資料類型編碼器

    將 Python 值編碼為暫存器列表，用於寫入操作。

    Attributes:
        data_type: Modbus 資料類型
        byte_order: 位元組順序
        register_order: 暫存器順序
    """

    data_type: ModbusDataType
    byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    register_order: RegisterOrder = RegisterOrder.HIGH_FIRST

    def apply(self, value: Any) -> list[int]:
        return self.data_type.encode(
            value,
            byte_order=self.byte_order,
            register_order=self.register_order,
        )


__all__ = [
    "ModbusDecoder",
    "ModbusEncoder",
]
