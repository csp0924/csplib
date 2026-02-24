# =============== Equipment Device - Config ===============
#
# 設備設定

from __future__ import annotations

from dataclasses import dataclass

from csp_lib.core.errors import ConfigurationError


@dataclass(frozen=True)
class DeviceConfig:
    """
    設備設定

    Attributes:
        device_id: 設備唯一識別碼
        unit_id: Modbus 設備位址 (0-255)
        address_offset: 位址偏移（PLC 1-based: offset=1）
        read_interval: 讀取間隔（秒）
        reconnect_interval: 重連間隔（秒）
        disconnect_threshold: 連續失敗次數閾值，達到後視為斷線
        max_concurrent_reads: 最大並行讀取數（0=不限制）
    """

    device_id: str
    unit_id: int = 1
    address_offset: int = 0
    read_interval: float = 1.0
    reconnect_interval: float = 5.0
    disconnect_threshold: int = 5
    max_concurrent_reads: int = 1

    def __post_init__(self) -> None:
        if not self.device_id:
            raise ConfigurationError("device_id 不可為空")
        if not 0 <= self.unit_id <= 255:
            raise ConfigurationError(f"unit_id 必須在 0-255 範圍內，收到: {self.unit_id}")
        if self.read_interval <= 0:
            raise ConfigurationError(f"read_interval 必須 > 0，收到: {self.read_interval}")
        if self.disconnect_threshold < 1:
            raise ConfigurationError(f"disconnect_threshold 必須 >= 1，收到: {self.disconnect_threshold}")
        if self.max_concurrent_reads < 0:
            raise ConfigurationError(f"max_concurrent_reads 必須 >= 0，收到: {self.max_concurrent_reads}")


__all__ = [
    "DeviceConfig",
]
