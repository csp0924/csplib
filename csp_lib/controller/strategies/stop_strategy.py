# =============== Stop Strategy ===============
#
# 停止策略：輸出 P=0, Q=0

from __future__ import annotations

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext


class StopStrategy(Strategy):
    """
    停止策略

    輸出 P=0, Q=0，用於停機狀態或無排程時的預設策略。
    每秒執行一次。
    """

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(p_target=0.0, q_target=0.0)
