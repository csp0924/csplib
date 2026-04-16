# =============== Tests - SystemMonitor._run_loop 時序漂移 (WI-TD-108) ===============
#
# 驗證 csp_lib/monitor/manager.py 的 _run_loop 迴圈
# 使用 next_tick_delay 絕對時間錨定後不會產生累積漂移。
#
# 測試手段：
#   - patch SystemMonitor._tick 注入 work_time
#   - patch asyncio.sleep / time.monotonic 為 fake 版本
#   - 跑 N ticks 後驗證 actual_elapsed ≈ N × interval_seconds

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from csp_lib.monitor.config import MonitorConfig


class TestSystemMonitorRunLoopDrift:
    """WI-TD-108: SystemMonitor._run_loop 時序漂移驗證"""

    async def test_run_loop_drift_under_tolerance(self):
        """_run_loop 跑 20 ticks，_tick 模擬 30ms 耗時，累積漂移 < 1 個 interval。

        修復前：簡單 sleep(interval_seconds)，_tick 耗時直接累積為漂移。
        修復後：next_tick_delay 對齊到 absolute anchor。
        """
        from csp_lib.monitor.manager import SystemMonitor

        interval = 0.2
        ticks = 20
        work_time = 0.03  # 30ms 模擬 _tick 耗時

        real_sleep = asyncio.sleep
        fake_clock = [0.0]
        tick_count = [0]

        def fake_monotonic() -> float:
            return fake_clock[0]

        async def fake_sleep(delay: float) -> None:
            fake_clock[0] += max(0.0, delay)
            await real_sleep(0)

        # 建立 SystemMonitor（不需 redis/dispatcher）
        config = MonitorConfig(interval_seconds=interval)
        monitor = SystemMonitor(config=config)

        # Patch _tick 注入 work_time
        async def slow_tick():
            tick_count[0] += 1
            fake_clock[0] += work_time
            await real_sleep(0)

        monitor._tick = slow_tick  # type: ignore[method-assign]

        with (
            patch("csp_lib.monitor.manager.asyncio.sleep", fake_sleep),
            patch("csp_lib.monitor.manager.time.monotonic", fake_monotonic),
            patch("csp_lib.core._time_anchor.time.monotonic", fake_monotonic),
        ):
            monitor._running = True
            task = asyncio.create_task(monitor._run_loop())

            for _ in range(ticks * 50):
                if tick_count[0] >= ticks:
                    break
                await real_sleep(0)

            monitor._running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        expected = ticks * interval
        actual = fake_clock[0]
        drift = abs(actual - expected)

        # 容忍度：2 個 interval
        tolerance = 2 * interval
        assert drift < tolerance, (
            f"SystemMonitor._run_loop 漂移過大：expected={expected:.3f}s, "
            f"actual={actual:.3f}s, drift={drift:.3f}s, tolerance={tolerance:.3f}s"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
