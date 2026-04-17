# =============== Core - Time Anchor Helper (Internal) ===============
#
# 絕對時間錨定 (absolute time anchoring) 睡眠輔助函式
#
# 提供週期性 loop 的時間漂移修正機制：
#   - 以 loop 啟動時間為 anchor，第 N 次 tick 目標為 anchor + N × interval
#   - 每次睡眠根據「目前實際時間」與「下一個 tick 目標」計算補償 delay
#   - 落後超過一整個週期時重設 anchor，避免 burst catch-up
#
# 此模組為 csp_lib 內部使用（前綴底線），不對外 export。

from __future__ import annotations

import time

from csp_lib.core import get_logger

# 統一走 csp_lib.core.get_logger，享用全域 sink/filter 設定
_logger = get_logger(__name__)


def next_tick_delay(anchor: float, completed: int, interval: float) -> tuple[float, float, int]:
    """計算到下一個 tick 應睡多久（絕對時間錨定，內部自動遞增 completed 計數）。

    典型用法（work-first 模式）::

        anchor = time.monotonic()
        n = 0
        while True:
            await do_work()
            delay, anchor, n = next_tick_delay(anchor, n, interval)
            await asyncio.sleep(delay)

    計算方式：
        target = completed + 1
        next_tick = anchor + target * interval
        delay = next_tick - now

    三種情況：
        1. delay > 0（正常）：回傳 ``(delay, anchor, completed + 1)``。
        2. -interval < delay <= 0（輕微落後）：回傳 ``(0.0, anchor, completed + 1)``，
           呼叫端 sleep(0) 讓出 event loop。
        3. delay <= -interval（嚴重落後）：重設 anchor 為 now，completed 歸零。
           回傳 ``(0.0, now, 0)``，避免 burst catch-up。

    Args:
        anchor: Loop 啟動時的 monotonic 時間基準。
        completed: 目前已完成的 tick 次數（從 0 開始）。
        interval: 週期秒數。

    Returns:
        ``(delay, new_anchor, new_completed)``：
        - ``delay``：應該 ``await asyncio.sleep(delay)`` 的秒數（含 0）。
        - ``new_anchor``：嚴重落後時重設為 now，否則不變。
        - ``new_completed``：正常與輕微落後遞增為 ``completed + 1``，重設時歸零。

    Note:
        呼叫端需自行 ``await asyncio.sleep(delay)``，使 test 能透過 patch
        呼叫端 module 的 ``asyncio.sleep`` 攔截。helper 本身不 await。
    """
    target = completed + 1
    next_tick = anchor + target * interval
    now = time.monotonic()
    delay = next_tick - now

    if delay > 0:
        return delay, anchor, target

    if delay <= -interval:
        # 嚴重落後（>= 一個週期），重設 anchor 並歸零計數
        _logger.debug(
            "時間漂移超過一個週期，重設 anchor (delay={:.3f}s, interval={:.3f}s)",
            delay,
            interval,
        )
        return 0.0, now, 0

    # 輕微落後：不睡但讓出 event loop，計數仍遞增
    return 0.0, anchor, target


__all__ = ["next_tick_delay"]
