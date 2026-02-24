# =============== Schedule Strategy ===============
#
# 排程策略：根據外部排程動態切換內部策略

from __future__ import annotations

from typing import Optional

from csp_lib.controller.core import Command, ExecutionConfig, Strategy, StrategyContext
from csp_lib.core import get_logger

from .stop_strategy import StopStrategy

logger = get_logger(__name__)


class ScheduleStrategy(Strategy):
    """
    排程策略

    根據外部排程動態切換內部策略。當無排程時使用 StopStrategy 作為預設。

    擴充性設計：
    - 可在 execute() 中呼叫多個策略的 execute() 並自行組合 Command
    - 例如：P 來自 PVSmooth，Q 來自另一個策略

    Usage:
        schedule = ScheduleStrategy()

        # 由外部排程更新器呼叫
        await schedule.update_schedule(pq_strategy)  # 切換到 PQ 模式
        await schedule.update_schedule(pv_strategy)  # 切換到 PVSmooth
        await schedule.update_schedule(None)         # 無排程 → StopStrategy
    """

    def __init__(self, fallback: Optional[Strategy] = None):
        """
        初始化排程策略

        Args:
            fallback: 無排程時的預設策略，若為 None 則使用 StopStrategy
        """
        self._current_strategy: Optional[Strategy] = None
        self._fallback = fallback or StopStrategy()

    @property
    def current_strategy(self) -> Strategy:
        """當前執行的策略"""
        return self._current_strategy or self._fallback

    @property
    def has_schedule(self) -> bool:
        """是否有排程"""
        return self._current_strategy is not None

    @property
    def execution_config(self) -> ExecutionConfig:
        # 使用當前策略的執行配置
        return self.current_strategy.execution_config

    async def update_schedule(self, strategy: Optional[Strategy]) -> None:
        """
        更新排程策略

        會自動呼叫舊策略的 on_deactivate() 和新策略的 on_activate()

        Args:
            strategy: 新的策略，None 表示使用 fallback (停止)
        """
        old_strategy = self._current_strategy

        if old_strategy is not None:
            logger.info(f"ScheduleStrategy: 停用 {old_strategy}")
            await old_strategy.on_deactivate()

        self._current_strategy = strategy

        if strategy is not None:
            logger.info(f"ScheduleStrategy: 啟用 {strategy}")
            await strategy.on_activate()
        else:
            logger.info(f"ScheduleStrategy: 使用 fallback ({self._fallback})")

    def execute(self, context: StrategyContext) -> Command:
        """
        執行當前策略
        """
        active = self.current_strategy
        return active.execute(context)

    async def on_activate(self) -> None:
        """啟用排程策略"""
        logger.info("ScheduleStrategy: 排程策略啟用")
        await self.current_strategy.on_activate()

    async def on_deactivate(self) -> None:
        """停用排程策略"""
        logger.info("ScheduleStrategy: 排程策略停用")
        if self._current_strategy is not None:
            await self._current_strategy.on_deactivate()

    def __str__(self) -> str:
        if self._current_strategy:
            return f"ScheduleStrategy(current={self._current_strategy})"
        return f"ScheduleStrategy(fallback={self._fallback})"
