# =============== Modbus Data Types - Numeric ===============
#
# 固定長度數值類型實作
#
# 支援類型：
#   - Int16 / UInt16: 16-bit 有號/無號整數 (1 暫存器)
#   - Int32 / UInt32: 32-bit 有號/無號整數 (2 暫存器)
#   - Float32: IEEE 754 單精度浮點數 (2 暫存器)

from __future__ import annotations

import struct

from ..enums import ByteOrder, RegisterOrder
from ..exceptions import ModbusDecodeError, ModbusEncodeError
from .base import ModbusDataType


class Int16(ModbusDataType):
    """
    16-bit 有號整數

    範圍: -32768 ~ 32767
    暫存器數: 1
    """

    @property
    def register_count(self) -> int:
        return 1

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"Int16 需要整數，收到: {type(value).__name__}")
        if not -32768 <= value <= 32767:
            raise ModbusEncodeError(f"Int16 範圍為 -32768~32767，收到: {value}")

        # 編碼為 bytes，再轉換為無號整數作為暫存器值
        packed = struct.pack(f"{byte_order.value}h", value)
        return [struct.unpack(f"{byte_order.value}H", packed)[0]]

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < 1:
            raise ModbusDecodeError(f"Int16 需要 1 個暫存器，收到: {len(registers)}")

        # 將無號暫存器值轉換為有號整數
        packed = struct.pack(f"{byte_order.value}H", registers[0])
        return struct.unpack(f"{byte_order.value}h", packed)[0]


class UInt16(ModbusDataType):
    """
    16-bit 無號整數

    範圍: 0 ~ 65535
    暫存器數: 1
    """

    @property
    def register_count(self) -> int:
        return 1

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"UInt16 需要整數，收到: {type(value).__name__}")
        if not 0 <= value <= 65535:
            raise ModbusEncodeError(f"UInt16 範圍為 0~65535，收到: {value}")

        return [value]

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < 1:
            raise ModbusDecodeError(f"UInt16 需要 1 個暫存器，收到: {len(registers)}")

        return registers[0]


class Int32(ModbusDataType):
    """
    32-bit 有號整數

    範圍: -2147483648 ~ 2147483647
    暫存器數: 2
    """

    @property
    def register_count(self) -> int:
        return 2

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"Int32 需要整數，收到: {type(value).__name__}")
        if not -2147483648 <= value <= 2147483647:
            raise ModbusEncodeError(
                f"Int32 範圍為 -2147483648~2147483647，收到: {value}"
            )

        # 編碼為 4 bytes
        packed = struct.pack(f"{byte_order.value}i", value)

        # 分割為兩個 16-bit 暫存器
        high = struct.unpack(f"{byte_order.value}H", packed[0:2])[0]
        low = struct.unpack(f"{byte_order.value}H", packed[2:4])[0]

        if register_order == RegisterOrder.HIGH_FIRST:
            return [high, low]
        return [low, high]

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < 2:
            raise ModbusDecodeError(f"Int32 需要 2 個暫存器，收到: {len(registers)}")

        if register_order == RegisterOrder.HIGH_FIRST:
            high, low = registers[0], registers[1]
        else:
            low, high = registers[0], registers[1]

        # 組合為 4 bytes
        packed = struct.pack(f"{byte_order.value}HH", high, low)
        return struct.unpack(f"{byte_order.value}i", packed)[0]


class UInt32(ModbusDataType):
    """
    32-bit 無號整數

    範圍: 0 ~ 4294967295
    暫存器數: 2
    """

    @property
    def register_count(self) -> int:
        return 2

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"UInt32 需要整數，收到: {type(value).__name__}")
        if not 0 <= value <= 4294967295:
            raise ModbusEncodeError(f"UInt32 範圍為 0~4294967295，收到: {value}")

        # 編碼為 4 bytes
        packed = struct.pack(f"{byte_order.value}I", value)

        # 分割為兩個 16-bit 暫存器
        high = struct.unpack(f"{byte_order.value}H", packed[0:2])[0]
        low = struct.unpack(f"{byte_order.value}H", packed[2:4])[0]

        if register_order == RegisterOrder.HIGH_FIRST:
            return [high, low]
        return [low, high]

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < 2:
            raise ModbusDecodeError(f"UInt32 需要 2 個暫存器，收到: {len(registers)}")

        if register_order == RegisterOrder.HIGH_FIRST:
            high, low = registers[0], registers[1]
        else:
            low, high = registers[0], registers[1]

        # 組合為 4 bytes
        packed = struct.pack(f"{byte_order.value}HH", high, low)
        return struct.unpack(f"{byte_order.value}I", packed)[0]


class UInt64(ModbusDataType):
    """
    64-bit 無號整數

    範圍: 0 ~ 18446744073709551615
    暫存器數: 4
    """

    @property
    def register_count(self) -> int:
        return 4

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"UInt64 需要整數，收到: {type(value).__name__}")
        if not 0 <= value <= 18446744073709551615:
            raise ModbusEncodeError(f"UInt64 範圍為 0~18446744073709551615，收到: {value}")

        # 編碼為 8 bytes
        packed = struct.pack(f"{byte_order.value}Q", value)

        # 分割為四個 16-bit 暫存器
        regs = [
            struct.unpack(f"{byte_order.value}H", packed[0:2])[0],
            struct.unpack(f"{byte_order.value}H", packed[2:4])[0],
            struct.unpack(f"{byte_order.value}H", packed[4:6])[0],
            struct.unpack(f"{byte_order.value}H", packed[6:8])[0],
        ]

        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()
        return regs

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < 4:
            raise ModbusDecodeError(f"Uint64 需要 4 個暫存器，收到: {len(registers)}")

        regs = list(registers[:4])
        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()

        # 組合為 8 bytes
        packed = struct.pack(
            f"{byte_order.value}HHHH",
            regs[0], regs[1], regs[2], regs[3]
        )
        return struct.unpack(f"{byte_order.value}Q", packed)[0]


class Int64(ModbusDataType):
    """
    64-bit 有號整數

    範圍: -9223372036854775808 ~ 9223372036854775807
    暫存器數: 4
    """

    @property
    def register_count(self) -> int:
        return 4

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"Int64 需要整數，收到: {type(value).__name__}")
        if not -9223372036854775808 <= value <= 9223372036854775807:
            raise ModbusEncodeError(
                f"Int64 範圍為 -9223372036854775808~9223372036854775807，收到: {value}"
            )

        # 編碼為 8 bytes
        packed = struct.pack(f"{byte_order.value}q", value)

        # 分割為四個 16-bit 暫存器
        regs = [
            struct.unpack(f"{byte_order.value}H", packed[0:2])[0],
            struct.unpack(f"{byte_order.value}H", packed[2:4])[0],
            struct.unpack(f"{byte_order.value}H", packed[4:6])[0],
            struct.unpack(f"{byte_order.value}H", packed[6:8])[0],
        ]

        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()
        return regs

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < 4:
            raise ModbusDecodeError(f"Int64 需要 4 個暫存器，收到: {len(registers)}")

        regs = list(registers[:4])
        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()

        # 組合為 8 bytes
        packed = struct.pack(
            f"{byte_order.value}HHHH",
            regs[0], regs[1], regs[2], regs[3]
        )
        return struct.unpack(f"{byte_order.value}q", packed)[0]


class Float32(ModbusDataType):
    """
    IEEE 754 單精度浮點數

    暫存器數: 2
    """

    @property
    def register_count(self) -> int:
        return 2

    def encode(
        self,
        value: float,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, (int, float)):
            raise ModbusEncodeError(f"Float32 需要數值，收到: {type(value).__name__}")

        # 編碼為 IEEE 754 單精度
        packed = struct.pack(f"{byte_order.value}f", float(value))

        # 分割為兩個 16-bit 暫存器
        high = struct.unpack(f"{byte_order.value}H", packed[0:2])[0]
        low = struct.unpack(f"{byte_order.value}H", packed[2:4])[0]

        if register_order == RegisterOrder.HIGH_FIRST:
            return [high, low]
        return [low, high]

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> float:
        if len(registers) < 2:
            raise ModbusDecodeError(f"Float32 需要 2 個暫存器，收到: {len(registers)}")

        if register_order == RegisterOrder.HIGH_FIRST:
            high, low = registers[0], registers[1]
        else:
            low, high = registers[0], registers[1]

        # 組合為 4 bytes 並解碼
        packed = struct.pack(f"{byte_order.value}HH", high, low)
        return struct.unpack(f"{byte_order.value}f", packed)[0]


class Float64(ModbusDataType):
    """
    IEEE 754 雙精度浮點數

    暫存器數: 4
    """

    @property
    def register_count(self) -> int:
        return 4

    def encode(
        self,
        value: float,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, (int, float)):
            raise ModbusEncodeError(f"Float64 需要數值，收到: {type(value).__name__}")

        # 編碼為 IEEE 754 雙精度
        packed = struct.pack(f"{byte_order.value}d", float(value))

        # 分割為四個 16-bit 暫存器
        regs = [
            struct.unpack(f"{byte_order.value}H", packed[0:2])[0],
            struct.unpack(f"{byte_order.value}H", packed[2:4])[0],
            struct.unpack(f"{byte_order.value}H", packed[4:6])[0],
            struct.unpack(f"{byte_order.value}H", packed[6:8])[0],
        ]

        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()
        return regs

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> float:
        if len(registers) < 4:
            raise ModbusDecodeError(f"Float64 需要 4 個暫存器，收到: {len(registers)}")

        regs = list(registers[:4])
        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()

        # 組合為 8 bytes 並解碼
        packed = struct.pack(
            f"{byte_order.value}HHHH",
            regs[0], regs[1], regs[2], regs[3]
        )
        return struct.unpack(f"{byte_order.value}d", packed)[0]


__all__ = [
    "Int16",
    "UInt16",
    "Int32",
    "UInt32",
    "Int64",
    "UInt64",
    "Float32",
    "Float64"
]
