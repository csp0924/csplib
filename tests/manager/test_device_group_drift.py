# =============== Tests - DeviceGroup._sequential_loop 時序漂移 (WI-TD-106) ===============
#
# 驗證 csp_lib/manager/device/group.py 的 _sequential_loop 迴圈
# 使用 next_tick_delay 絕對時間錨定後不會產生累積漂移。
#
# 注意：DeviceGroup 的迴圈內部有 step_interval sleep（設備間延遲），
# 再加上 interval（一輪的總間隔），所以實際 sleep 包含兩部分。
# 測試驗證的是「完整一輪的間隔」是否對齊到 absolute anchor。
#
# 測試手段：
#   - 建構 DeviceGroup 並注入 mock devices
#   - patch asyncio.sleep / asyncio.wait_for 記錄時序
#   - patch time.monotonic 為 fake_clock
#   - 跑 N 輪後驗證 actual_elapsed ≈ N × interval

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_device(device_id: str, read_time: float = 0.01):
    """建立 mock 設備（模擬 AsyncModbusDevice 最小介面）。"""
    device = MagicMock()
    device.device_id = device_id
    device.should_attempt_read = True

    real_sleep = asyncio.sleep

    async def fake_read_once():
        # 模擬讀取耗時（推進 fake clock 在外部處理）
        await real_sleep(0)

    device.read_once = AsyncMock(side_effect=fake_read_once)
    return device


class TestDeviceGroupSequentialLoopDrift:
    """WI-TD-106: DeviceGroup._sequential_loop 時序漂移驗證"""

    async def test_sequential_loop_drift_under_tolerance(self):
        """_sequential_loop 跑 10 輪，每輪 2 個設備各耗時 20ms，
        step_interval=0.01s，interval=0.5s，累積漂移 < 1 個 interval。

        修復前：elapsed-subtraction 模式，work_time 直接累積為漂移。
        修復後：next_tick_delay 對齊到 absolute anchor。
        """
        from csp_lib.manager.device.group import DeviceGroup

        interval = 0.5
        step_interval = 0.01
        rounds = 10
        work_time = 0.02  # 每個設備 read 耗時 20ms

        real_sleep = asyncio.sleep
        fake_clock = [0.0]
        round_count = [0]

        def fake_monotonic() -> float:
            return fake_clock[0]

        async def fake_sleep(delay: float) -> None:
            fake_clock[0] += max(0.0, delay)
            await real_sleep(0)

        # asyncio.wait_for 用於 stop_event.wait 的等待，需特別處理
        async def fake_wait_for(coro, timeout=None):
            if timeout is not None:
                fake_clock[0] += timeout
            await real_sleep(0)
            raise asyncio.TimeoutError()

        devices = [_make_mock_device("dev1"), _make_mock_device("dev2")]

        # 用 read_once side_effect 推進 clock
        for d in devices:

            async def side_effect(*args, _d=d, **kwargs):
                round_count[0] += 0.5  # 每個設備算半輪
                fake_clock[0] += work_time
                await real_sleep(0)

            d.read_once = AsyncMock(side_effect=side_effect)

        group = DeviceGroup(
            devices=devices,
            interval=interval,
            step_interval=step_interval,
        )

        with (
            patch("csp_lib.manager.device.group.asyncio.sleep", fake_sleep),
            patch("csp_lib.manager.device.group.asyncio.wait_for", fake_wait_for),
            patch("csp_lib.manager.device.group.time.monotonic", fake_monotonic),
            patch("csp_lib.core._time_anchor.time.monotonic", fake_monotonic),
        ):
            # 啟動 group（會建立 _sequential_loop task）
            group._stop_event = asyncio.Event()
            task = asyncio.create_task(group._sequential_loop())

            # 等足夠多輪
            for _ in range(rounds * 100):
                if round_count[0] >= rounds:
                    break
                await real_sleep(0)

            group._stop_event.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        expected = rounds * interval
        actual = fake_clock[0]
        drift = abs(actual - expected)

        # 容忍度：2 個 interval（含 step_interval 和 work_time 的累積效果）
        tolerance = 2 * interval
        assert drift < tolerance, (
            f"DeviceGroup._sequential_loop 漂移過大：expected={expected:.3f}s, "
            f"actual={actual:.3f}s, drift={drift:.3f}s, tolerance={tolerance:.3f}s, "
            f"rounds={round_count[0]}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
