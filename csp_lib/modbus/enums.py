# =============== Modbus Enums ===============
#
# Modbus 模組列舉與常數定義
#
# 包含：
#   - ByteOrder: 位元組順序 (大端/小端)
#   - RegisterOrder: 暫存器順序 (高位優先/低位優先)
#   - FunctionCode: Modbus 功能碼
#   - Parity: 串口校驗位元

from __future__ import annotations

from enum import Enum, IntEnum


class ByteOrder(Enum):
    """
    位元組順序

    定義多位元組資料在單一暫存器內的排列方式。
    Modbus 標準使用大端序 (Big-Endian)。

    Attributes:
        BIG_ENDIAN: 大端序，高位元組在前 (Modbus 預設)
        LITTLE_ENDIAN: 小端序，低位元組在前
    """

    BIG_ENDIAN = ">"
    LITTLE_ENDIAN = "<"


class RegisterOrder(Enum):
    """
    暫存器順序

    定義多暫存器資料的排列方式。
    例如 32-bit 整數需要 2 個暫存器，此設定決定高低位暫存器順序。

    Attributes:
        HIGH_FIRST: 高位暫存器在前 (常見，如 AB CD)
        LOW_FIRST: 低位暫存器在前 (如 CD AB)
    """

    HIGH_FIRST = "high"
    LOW_FIRST = "low"


class Parity(Enum):
    """
    串口校驗位元

    用於 RTU 模式的串口通訊設定。

    Attributes:
        NONE: 無校驗
        EVEN: 偶校驗
        ODD: 奇校驗
    """

    NONE = "N"
    EVEN = "E"
    ODD = "O"


class FunctionCode(IntEnum):
    """
    Modbus 功能碼

    定義標準 Modbus 功能碼，用於識別請求類型。

    讀取功能：
        - READ_COILS (0x01): 讀取線圈狀態
        - READ_DISCRETE_INPUTS (0x02): 讀取離散輸入
        - READ_HOLDING_REGISTERS (0x03): 讀取保持暫存器
        - READ_INPUT_REGISTERS (0x04): 讀取輸入暫存器

    寫入功能：
        - WRITE_SINGLE_COIL (0x05): 寫入單一線圈
        - WRITE_SINGLE_REGISTER (0x06): 寫入單一暫存器
        - WRITE_MULTIPLE_COILS (0x0F): 寫入多個線圈
        - WRITE_MULTIPLE_REGISTERS (0x10): 寫入多個暫存器
    """

    # 讀取功能碼
    READ_COILS = 0x01
    READ_DISCRETE_INPUTS = 0x02
    READ_HOLDING_REGISTERS = 0x03
    READ_INPUT_REGISTERS = 0x04

    # 寫入功能碼
    WRITE_SINGLE_COIL = 0x05
    WRITE_SINGLE_REGISTER = 0x06
    WRITE_MULTIPLE_COILS = 0x0F
    WRITE_MULTIPLE_REGISTERS = 0x10


__all__ = [
    "ByteOrder",
    "RegisterOrder",
    "Parity",
    "FunctionCode",
]
