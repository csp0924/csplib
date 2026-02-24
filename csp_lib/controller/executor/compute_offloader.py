# =============== Controller Executor - Compute Offloader ===============
#
# 計算卸載器
#
# 將同步的策略運算卸載到執行緒池，避免阻塞 asyncio event loop。
# 適用於運算密集的策略（如 PVSmooth 的預測計算）。

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class ComputeOffloader:
    """
    計算卸載器

    將同步的策略運算卸載到執行緒池，避免阻塞 asyncio event loop。

    使用範例：
        offloader = ComputeOffloader(max_workers=2)

        # 在 StrategyExecutor 中使用
        executor = StrategyExecutor(
            context_provider=get_context,
            offloader=offloader,
        )

        # 或直接使用
        result = await offloader.run(heavy_computation, arg1, arg2)

        # 關閉時釋放資源
        offloader.shutdown()
    """

    def __init__(self, max_workers: int = 1):
        """
        初始化卸載器

        Args:
            max_workers: 執行緒池最大工作執行緒數
        """
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._shutdown = False

    async def run(self, func: Callable[..., T], *args: Any) -> T:
        """
        將同步函式卸載到執行緒池執行

        Args:
            func: 要執行的同步函式
            *args: 傳遞給函式的位置參數

        Returns:
            函式的回傳值
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    def shutdown(self) -> None:
        """
        關閉執行緒池

        可安全地重複呼叫（冪等）。
        """
        if not self._shutdown:
            self._shutdown = True
            self._executor.shutdown(wait=False)


__all__ = [
    "ComputeOffloader",
]
