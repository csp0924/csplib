# =============== Bypass Strategy ===============
#
# 旁路策略：什麼都不做，用於手動控制模式

from __future__ import annotations

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext


class BypassStrategy(Strategy):
    """
    旁路策略 (Bypass Mode)

    完全不發送任何指令，用於手動控制模式。
    GridController 的 command loop 會跳過此策略，
    使用者可透過外部方式直接控制設備。

    使用情境：
        - 手動調試設備
        - 臨時接管控制權
        - 維護模式
    """

    @property
    def suppress_heartbeat(self) -> bool:
        """旁路模式暫停心跳，讓設備知道控制器已釋放控制權"""
        return True

    @property
    def execution_config(self) -> ExecutionConfig:
        # TRIGGERED 模式，不會主動執行
        return ExecutionConfig(mode=ExecutionMode.TRIGGERED, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        # 維持上一次的命令狀態
        return context.last_command

    def __str__(self) -> str:
        return "BypassStrategy()"
