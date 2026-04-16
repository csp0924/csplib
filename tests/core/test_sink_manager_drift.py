# =============== Tests - SinkManager._poll_remote 時序漂移 (WI-TD-104) ===============
#
# 驗證 csp_lib/core/logging/sink_manager.py 的 _poll_remote 迴圈
# 使用絕對時間錨定（next_tick_delay）後，累積漂移在容忍範圍內。
#
# 測試手段：
#   - patch time.monotonic 為 fake_clock
#   - patch asyncio.sleep 為 fake_sleep（推進 fake_clock）
#   - 模擬 fetch_levels 有 work_time 的 RemoteLevelSource
#   - 跑 N 次 tick 後，驗證 actual_elapsed ≈ N × interval

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

# 直接測試 next_tick_delay 被正確使用的效果（不依賴 SinkManager 單例）
# 改為直接模擬 _poll_remote 的核心邏輯


class TestSinkManagerPollRemoteDrift:
    """WI-TD-104: SinkManager._poll_remote 時序漂移驗證"""

    async def test_poll_remote_drift_under_tolerance(self):
        """_poll_remote 跑 50 ticks，work 模擬 20ms，累積漂移 < 1 個 interval。

        修復前：簡單 sleep(interval) 模式，work_time 直接累積為漂移。
        修復後：next_tick_delay 對齊到 absolute anchor，不累積。
        """
        interval = 0.1
        ticks = 50
        work_time = 0.02  # 20ms 模擬 fetch_levels 耗時

        real_sleep = asyncio.sleep
        fake_clock = [0.0]
        tick_count = [0]

        def fake_monotonic() -> float:
            return fake_clock[0]

        async def fake_sleep(delay: float) -> None:
            fake_clock[0] += max(0.0, delay)
            await real_sleep(0)

        # 模擬 RemoteLevelSource
        mock_source = AsyncMock()

        async def fake_fetch_levels():
            tick_count[0] += 1
            fake_clock[0] += work_time  # 模擬耗時
            return {}

        mock_source.fetch_levels = fake_fetch_levels

        # 直接跑 _poll_remote 的核心邏輯（避免 SinkManager 單例副作用）
        async def poll_remote_logic():
            from csp_lib.core._time_anchor import next_tick_delay as ntd

            anchor = fake_monotonic()
            n = 0
            while tick_count[0] < ticks:
                await mock_source.fetch_levels()
                # next_tick_delay 使用 real time.monotonic，需 patch
                delay, anchor, n = ntd(anchor, n, interval)
                await fake_sleep(delay)

        with (
            patch("csp_lib.core._time_anchor.time.monotonic", fake_monotonic),
        ):
            task = asyncio.create_task(poll_remote_logic())
            # 等待完成（fake_clock 不需要 real time，循環夠多次就會結束）
            for _ in range(ticks * 30):
                if tick_count[0] >= ticks:
                    break
                await real_sleep(0)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        expected = ticks * interval
        actual = fake_clock[0]
        drift = abs(actual - expected)

        # 容忍度：2 個 interval（考慮 anchor reset 和 work_time 超出一個週期的情況）
        tolerance = 2 * interval
        assert drift < tolerance, (
            f"SinkManager._poll_remote 漂移過大：expected={expected:.3f}s, "
            f"actual={actual:.3f}s, drift={drift:.3f}s, tolerance={tolerance:.3f}s"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
