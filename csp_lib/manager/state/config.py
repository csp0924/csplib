# =============== Manager State - Config ===============
#
# 狀態同步配置
#
# 定義狀態同步相關參數：
#   - StateSyncConfig: TTL 設定

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateSyncConfig:
    """
    狀態同步配置

    Attributes:
        state_ttl: 設備狀態 Hash TTL（秒）
        online_ttl: 連線狀態 TTL（秒）
    """

    state_ttl: int = 60
    online_ttl: int = 60

    def __post_init__(self) -> None:
        if self.state_ttl <= 0:
            raise ValueError(f"state_ttl 必須大於 0，收到: {self.state_ttl}")
        if self.online_ttl <= 0:
            raise ValueError(f"online_ttl 必須大於 0，收到: {self.online_ttl}")


__all__ = [
    "StateSyncConfig",
]
