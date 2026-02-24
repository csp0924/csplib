# =============== Modbus Config ===============
#
# Modbus 連線設定模組
#
# 提供 TCP 與 RTU 模式的設定類別：
#   - ModbusTcpConfig: TCP/IP 連線設定
#   - ModbusRtuConfig: RTU 串口連線設定

from __future__ import annotations

from dataclasses import dataclass

from .enums import ByteOrder, Parity, RegisterOrder
from .exceptions import ModbusConfigError


@dataclass(frozen=True)
class ModbusTcpConfig:
    """
    Modbus TCP 連線設定

    使用 frozen dataclass 確保設定不可變。

    Note:
        unit_id 已移至設備層級 (DeviceConfig)，
        讓多個設備可共用同一個 Client 連線。

    Attributes:
        host: 目標主機位址
        port: 連接埠號，預設 502
        timeout: 通訊逾時秒數，預設 0.5
        byte_order: 位元組順序，預設大端序
        register_order: 暫存器順序，預設高位優先
    """

    host: str
    port: int = 502
    timeout: float = 0.5
    byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    register_order: RegisterOrder = RegisterOrder.HIGH_FIRST

    def __post_init__(self) -> None:
        """驗證設定值的合理性"""
        if not self.host:
            raise ModbusConfigError("host 不可為空")
        if not 1 <= self.port <= 65535:
            raise ModbusConfigError(f"port 必須在 1-65535 範圍內，收到: {self.port}")
        if self.timeout <= 0:
            raise ModbusConfigError(f"timeout 必須為正數，收到: {self.timeout}")


@dataclass(frozen=True)
class ModbusRtuConfig:
    """
    Modbus RTU 連線設定

    使用 frozen dataclass 確保設定不可變。

    Note:
        unit_id 已移至設備層級 (DeviceConfig)，
        讓多個設備可共用同一個串口連線。

    Attributes:
        port: 串口名稱 (e.g., "COM1", "/dev/ttyUSB0")
        baudrate: 鮑率，預設 9600
        parity: 校驗位元，預設無校驗
        stopbits: 停止位元數，預設 1
        bytesize: 資料位元數，預設 8
        timeout: 通訊逾時秒數，預設 0.5
        byte_order: 位元組順序，預設大端序
        register_order: 暫存器順序，預設高位優先
    """

    port: str
    baudrate: int = 9600
    parity: Parity = Parity.NONE
    stopbits: int = 1
    bytesize: int = 8
    timeout: float = 0.5
    byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    register_order: RegisterOrder = RegisterOrder.HIGH_FIRST

    def __post_init__(self) -> None:
        """驗證設定值的合理性"""
        if not self.port:
            raise ModbusConfigError("port 不可為空")
        if self.baudrate <= 0:
            raise ModbusConfigError(f"baudrate 必須為正整數，收到: {self.baudrate}")
        if self.stopbits not in (1, 2):
            raise ModbusConfigError(f"stopbits 必須為 1 或 2，收到: {self.stopbits}")
        if self.bytesize not in (5, 6, 7, 8):
            raise ModbusConfigError(f"bytesize 必須為 5, 6, 7 或 8，收到: {self.bytesize}")
        if self.timeout <= 0:
            raise ModbusConfigError(f"timeout 必須為正數，收到: {self.timeout}")


__all__ = [
    "ModbusTcpConfig",
    "ModbusRtuConfig",
]
