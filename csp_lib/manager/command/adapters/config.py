# =============== Manager Command Adapters - Config ===============
#
# 指令適配器配置
#
# 定義 Redis Pub/Sub 指令適配器的 channel 設定：
#   - CommandAdapterConfig: 指令/結果 channel 名稱

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandAdapterConfig:
    """
    指令適配器配置

    Attributes:
        command_channel: 接收指令的 Redis Pub/Sub channel
        result_channel: 發布結果的 Redis Pub/Sub channel
    """

    command_channel: str = "channel:commands:write"
    result_channel: str = "channel:commands:result"

    def __post_init__(self) -> None:
        if not self.command_channel:
            raise ValueError("command_channel 不可為空")
        if not self.result_channel:
            raise ValueError("result_channel 不可為空")


__all__ = [
    "CommandAdapterConfig",
]
