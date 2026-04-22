# =============== Manager State - Config ===============
#
# 狀態同步配置
#
# 定義狀態同步相關參數：
#   - StateSyncConfig: TTL 設定

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StateSyncConfig:
    """
    狀態同步配置

    Attributes:
        state_ttl: 設備狀態 Hash TTL（秒）
        online_ttl: 連線狀態 TTL（秒）
        key_prefix: Redis key 前綴（預設 ``"device"``）。多站共用 Redis 時可用
            站 ID 做 prefix 避免衝突，例如 ``"taiwan-s1.device"``。
            Key 實際格式：``"{key_prefix}:{device_id}:state"`` 等。
        channel_prefix: Pub/Sub channel 前綴（預設 ``"channel:device"``）。同上，
            可改為 ``"taiwan-s1.channel:device"`` 之類。
    """

    state_ttl: int = 60
    online_ttl: int = 60
    key_prefix: str = "device"
    channel_prefix: str = "channel:device"

    def __post_init__(self) -> None:
        if self.state_ttl <= 0:
            raise ValueError(f"state_ttl 必須大於 0，收到: {self.state_ttl}")
        if self.online_ttl <= 0:
            raise ValueError(f"online_ttl 必須大於 0，收到: {self.online_ttl}")
        if not self.key_prefix:
            raise ValueError("key_prefix 不可為空字串")
        if not self.channel_prefix:
            raise ValueError("channel_prefix 不可為空字串")


__all__ = [
    "StateSyncConfig",
]
