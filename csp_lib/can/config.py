# =============== CAN - Config ===============
#
# CAN Bus 配置與訊框資料結構

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CANBusConfig:
    """
    CAN Bus 配置

    Attributes:
        interface: python-can 介面名稱 ("socketcan", "virtual", "tcp")
        channel: 通道名稱 ("can0", "192.168.1.100:5000")
        bitrate: 位元率
        receive_own_messages: 是否接收自己發送的訊息
    """

    interface: str
    channel: str
    bitrate: int = 500_000
    receive_own_messages: bool = False


@dataclass(frozen=True, slots=True)
class CANFrame:
    """
    CAN 訊框

    Attributes:
        can_id: CAN 訊框 ID
        data: 訊框資料（最多 8 bytes）
        timestamp: 時間戳
        is_remote: 是否為遠端請求訊框
    """

    can_id: int
    data: bytes
    timestamp: float = 0.0
    is_remote: bool = False


__all__ = [
    "CANBusConfig",
    "CANFrame",
]
