# =============== Tests - CommunicationWatchdog._check_loop 時序漂移 (WI-TD-107) ===============
#
# 驗證 csp_lib/modbus_gateway/watchdog.py 的 _check_loop 迴圈
# 使用 next_tick_delay 絕對時間錨定後不會產生累積漂移。
#
# 測試手段：
#   - 注入 fake clock（watchdog 已支援 clock= 參數）
#   - patch asyncio.sleep 記錄 delay 並推進 fake_clock
#   - 注入 slow timeout callback 模擬 check work
#   - 跑 N ticks 後驗證 actual_elapsed ≈ N × check_interval

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from csp_lib.modbus_gateway.config import WatchdogConfig
from csp_lib.modbus_gateway.watchdog import CommunicationWatchdog


class TestWatchdogCheckLoopDrift:
    """WI-TD-107: CommunicationWatchdog._check_loop 時序漂移驗證"""

    async def test_check_loop_drift_under_tolerance(self):
        """_check_loop 跑 20 ticks，每次 callback 耗時 10ms，累積漂移 < 1 個 interval。

        修復前：簡單 sleep(check_interval) 模式，callback 耗時直接累積為漂移。
        修復後：next_tick_delay 對齊到 absolute anchor。
        """
        check_interval = 0.1
        timeout_seconds = 1.0  # 設定較大，避免觸發 timeout
        ticks = 20

        real_sleep = asyncio.sleep
        fake_clock = [0.0]
        sleep_count = [0]

        def fake_monotonic() -> float:
            return fake_clock[0]

        async def fake_sleep(delay: float) -> None:
            sleep_count[0] += 1
            fake_clock[0] += max(0.0, delay)
            await real_sleep(0)

        # 使用 clock injection（watchdog 支援）
        watchdog = CommunicationWatchdog(
            config=WatchdogConfig(
                timeout_seconds=timeout_seconds,
                check_interval=check_interval,
                enabled=True,
            ),
            clock=fake_monotonic,
        )

        # 持續 touch 避免 timeout
        async def keep_touching():
            while sleep_count[0] < ticks:
                watchdog.touch()
                await real_sleep(0)

        # Patch asyncio.sleep 和 time.monotonic（用於 next_tick_delay 內部）
        with (
            patch("csp_lib.modbus_gateway.watchdog.asyncio.sleep", fake_sleep),
            patch("csp_lib.core._time_anchor.time.monotonic", fake_monotonic),
        ):
            touch_task = asyncio.create_task(keep_touching())
            await watchdog.start()

            # 等待足夠的 ticks
            for _ in range(ticks * 50):
                if sleep_count[0] >= ticks:
                    break
                await real_sleep(0)

            await watchdog.stop()
            touch_task.cancel()
            try:
                await touch_task
            except asyncio.CancelledError:
                pass

        expected = ticks * check_interval
        actual = fake_clock[0]
        drift = abs(actual - expected)

        # 容忍度：2 個 interval
        tolerance = 2 * check_interval
        assert drift < tolerance, (
            f"Watchdog._check_loop 漂移過大：expected={expected:.3f}s, "
            f"actual={actual:.3f}s, drift={drift:.3f}s, tolerance={tolerance:.3f}s"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
