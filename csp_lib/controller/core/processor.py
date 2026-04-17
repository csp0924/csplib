"""
CommandProcessor — Post-Protection 命令處理器 Protocol

定義在 ProtectionGuard 和 CommandRouter 之間的處理管線。
典型用途：功率補償、命令日誌、審計追蹤等。

執行流程::

    Strategy.execute()
      → ProtectionGuard.apply()
      → [CommandProcessor 1] → [CommandProcessor 2] → ...
      → CommandRouter.route()

Usage::

    from csp_lib.controller.core import is_no_change

    class MyCompensator:
        async def process(self, command, context):
            # 策略要求「此軸不變更」（NO_CHANGE）時補償器 bypass
            if is_no_change(command.p_target):
                return command
            compensated_p = self._compensate(command.p_target)
            return command.with_p(compensated_p)

    config = SystemControllerConfig(
        post_protection_processors=[MyCompensator()],
    )

Note:
    ``command.p_target`` / ``q_target`` 可能為 ``NO_CHANGE`` sentinel。若 processor
    對值做計算（功率補償、限幅等），入口應使用 ``is_no_change(...)`` 守衛並原封
    回傳 command，避免把 sentinel 當 float 餵進內部狀態（積分器、EMA 等）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .command import Command
from .context import StrategyContext


@runtime_checkable
class CommandProcessor(Protocol):
    """
    Post-Protection 命令處理器

    在 ProtectionGuard 和 CommandRouter 之間對命令做額外處理。
    實作此 Protocol 的物件可在 SystemControllerConfig 中註冊。

    方法語義：
    - 輸入：經保護鏈處理後的 Command 和當前 StrategyContext
    - 輸出：處理後的 Command（可修改 p_target / q_target）
    - 拋出例外時：SystemController 會 log 並跳過此 processor，繼續後續處理
    """

    async def process(self, command: Command, context: StrategyContext) -> Command:
        """
        處理命令

        Args:
            command: 經保護鏈處理後的命令
            context: 當前策略上下文

        Returns:
            處理後的命令
        """
        ...


__all__ = ["CommandProcessor"]
