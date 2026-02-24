# =============== PQ Mode Strategy ===============
#
# PQ 模式策略：根據配置輸出固定的 P/Q 值

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from csp_lib.controller.core import Command, ConfigMixin, ExecutionConfig, ExecutionMode, Strategy, StrategyContext


@dataclass
class PQModeConfig(ConfigMixin):
    """
    PQ 模式配置

    Attributes:
        p: 有功功率目標值 (kW)
        q: 無功功率目標值 (kVar)
    """

    p: float = 0.0
    q: float = 0.0


class PQModeStrategy(Strategy):
    """
    PQ 模式策略

    根據配置輸出固定的 P/Q 值。
    每秒執行一次 (PERIODIC)。

    Usage:
        config = PQModeConfig(p=100, q=50)
        strategy = PQModeStrategy(config)
    """

    def __init__(self, config: Optional[PQModeConfig] = None):
        """
        初始化 PQ 模式策略

        Args:
            config: PQ 配置，若為 None 則使用預設值 (0, 0)
        """
        self._config = config or PQModeConfig()

    @property
    def config(self) -> PQModeConfig:
        """當前配置"""
        return self._config

    @property
    def execution_config(self) -> ExecutionConfig:
        """回傳策略的執行配置"""
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        """執行策略邏輯"""
        return Command(p_target=self._config.p, q_target=self._config.q)

    def update_config(self, config: PQModeConfig) -> None:
        """
        更新配置

        Args:
            config: 新的 PQ 配置
        """
        self._config = config

    def __str__(self) -> str:
        return f"PQModeStrategy(P={self._config.p}, Q={self._config.q})"
