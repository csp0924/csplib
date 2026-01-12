# =============== Strategy Module ===============
#
# 策略抽象基礎類別
# - Strategy: 策略抽象基礎類別

from __future__ import annotations

from abc import ABC, abstractmethod

from .command import Command
from .context import StrategyContext
from .execution import ExecutionConfig


class Strategy(ABC):
    """
    策略抽象基礎類別

    所有策略必須繼承此類別並實作：
    - execution_config: 回傳執行配置
    - execute(): 執行策略邏輯並回傳 Command

    可選覆寫：
    - on_activate(): 策略啟用時呼叫
    - on_deactivate(): 策略停用時呼叫

    擴充性設計：
    - 策略可在 execute() 中呼叫其他策略的 execute() 取得 Command
    - 自行組合多個 Command 達成複合策略效果
    """

    @property
    @abstractmethod
    def execution_config(self) -> ExecutionConfig:
        """回傳策略的執行配置"""
        pass

    @abstractmethod
    def execute(self, context: StrategyContext) -> Command:
        """
        執行策略邏輯

        Args:
            context: 執行時上下文，包含 last_command、soc 等狀態

        Returns:
            Command: 策略輸出命令
        """
        pass

    def on_activate(self) -> None:
        """
        策略啟用時呼叫 (可選覆寫)

        用途：初始化內部狀態、記錄日誌等
        """
        pass

    def on_deactivate(self) -> None:
        """
        策略停用時呼叫 (可選覆寫)

        用途：清理資源、保存狀態等
        """
        pass

    def __str__(self) -> str:
        return f"{self.__class__.__name__}"

    def __repr__(self) -> str:
        return self.__str__()
