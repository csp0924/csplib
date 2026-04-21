# =============== Controller - Protocol ===============
#
# 併網控制器抽象介面
# - GridControllerProtocol: 協定定義（生命週期介面，所有 controller 共通）
# - StrategyAwareGridControllerProtocol: 擴充協定，要求 set_strategy（單策略控制器用）
# - GridControllerBase: 抽象基底類別

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .core import Command, Strategy, StrategyContext


@runtime_checkable
class GridControllerProtocol(Protocol):
    """
    併網控制器協定（生命週期介面）

    定義 GridController 的最小共通介面：啟動與停止。
    所有併網控制器實作（單策略 GridController 或 mode-based SystemController）
    都應結構性符合此協定，用於型別檢查與統一生命週期管理。

    Note:
        v0.9.x 前此協定曾要求 ``set_strategy``。為了讓 mode-based 的
        ``SystemController``（使用 ``register_mode`` / ``set_base_mode``）
        也能結構性滿足此協定，已將 ``set_strategy`` 移至
        :class:`StrategyAwareGridControllerProtocol`。單策略控制器請改
        針對該擴充協定做型別檢查。
    """

    async def start(self) -> None:
        """啟動控制器"""
        ...

    async def stop(self) -> None:
        """停止控制器"""
        ...


@runtime_checkable
class StrategyAwareGridControllerProtocol(GridControllerProtocol, Protocol):
    """
    支援單一策略切換的併網控制器擴充協定

    在 :class:`GridControllerProtocol` 的生命週期介面上，進一步要求
    ``set_strategy`` 方法，適用於經典的單策略 GridController
    （繼承 :class:`GridControllerBase` 並自行處理單一策略切換）。

    Mode-based 控制器（如 ``SystemController``）不實作 ``set_strategy``，
    改用 ``register_mode`` + ``set_base_mode`` 管理多模式策略，因此
    不符合此擴充協定。
    """

    def set_strategy(self, strategy: Strategy | None) -> None:
        """設定/切換策略"""
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

        Note:
            v0.8.0 起 ``command.p_target`` / ``q_target`` 可能為 ``NO_CHANGE``
            sentinel。推薦的實作方式：
              - 在 SystemController 架構下，此類 sentinel 會在 ``CommandRouter``
                層被過濾（不會觸發設備寫入），子類別無需額外處理。
              - 若直接實作 ``_send_command``（不經 CommandRouter），建議使用
                ``command.effective_p(fallback)`` / ``effective_q(fallback)``
                取得有效浮點值，或明確 ``is_no_change(...)`` 守衛跳過該軸。

        Args:
            command: 策略輸出的命令
        """
        pass


__all__ = [
    "GridControllerProtocol",
    "StrategyAwareGridControllerProtocol",
    "GridControllerBase",
]
