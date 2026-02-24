# =============== Controller - Protocol ===============
#
# 併網控制器抽象介面
# - GridControllerProtocol: 協定定義
# - GridControllerBase: 抽象基底類別

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .core import Command, Strategy, StrategyContext


@runtime_checkable
class GridControllerProtocol(Protocol):
    """
    併網控制器協定

    定義 GridController 必須實作的介面，用於型別檢查。
    """

    def set_strategy(self, strategy: Strategy | None) -> None:
        """設定/切換策略"""
        ...

    async def start(self) -> None:
        """啟動控制器"""
        ...

    async def stop(self) -> None:
        """停止控制器"""
        ...


class GridControllerBase(ABC):
    """
    併網控制器抽象基底類別

    提供 StrategyExecutor 整合的基礎框架。
    子類別需實作 _build_context() 和 _send_command() 方法。

    Usage:
        class MyGridController(GridControllerBase):
            def _build_context(self) -> StrategyContext:
                return StrategyContext(soc=self._bms.latest_values.get("soc"))

            async def _send_command(self, command: Command) -> None:
                await self._pcs.set_pcs_pq(command.p_target, command.q_target)
    """

    @abstractmethod
    def _build_context(self) -> StrategyContext:
        """
        建構策略執行上下文

        子類別實作此方法，從設備讀取即時資料建構 StrategyContext。

        Returns:
            StrategyContext: 策略執行所需的上下文
        """
        pass

    @abstractmethod
    async def _send_command(self, command: Command) -> None:
        """
        發送命令到設備

        子類別實作此方法，將策略輸出的 Command 寫入 PCS。

        Args:
            command: 策略輸出的命令
        """
        pass


__all__ = [
    "GridControllerProtocol",
    "GridControllerBase",
]
