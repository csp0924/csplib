"""共用測試輔助工具。

提供非同步條件輪詢等 helper，取代硬編碼 asyncio.sleep 以消除 flaky 測試。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


async def wait_for_condition(
    check_fn: Callable[[], bool],
    *,
    timeout: float = 5.0,
    interval: float = 0.01,
    message: str = "Condition not met",
) -> None:
    """輪詢等待條件成立，取代固定 asyncio.sleep。

    以 *interval* 為間隔反覆呼叫 *check_fn*，直到其回傳 ``True``
    或超過 *timeout* 秒後拋出 ``TimeoutError``。

    Args:
        check_fn: 無參數的同步 callable，回傳 bool。
        timeout: 最長等待秒數。
        interval: 輪詢間隔秒數。
        message: 逾時時的錯誤訊息。

    Raises:
        TimeoutError: 條件在 timeout 內未成立。
    """
    start = time.monotonic()
    while not check_fn():
        if time.monotonic() - start > timeout:
            raise TimeoutError(f"{message} within {timeout}s")
        await asyncio.sleep(interval)
