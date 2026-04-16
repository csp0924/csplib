# =============== Tests - CANDevice Snapshot Loop 時序漂移 (WI-TD-101) ===============
#
# 重現 csp_lib/equipment/device/can_device.py:449-465 的時序漂移 bug：
#
#   async def _snapshot_loop(self) -> None:
#       while True:
#           await asyncio.sleep(self._config.read_interval)   # ← 固定等 interval
#           values = self._latest_values.copy()
#           ...
#           await self._evaluate_alarm(values)                # ← work 耗時 W
#           self._check_rx_timeout()
#
# 問題：每一次 tick 實際週期 = interval + W（work 耗時累加到下一次 tick），
#       長時間執行後會出現明顯漂移，無法對齊 absolute time anchor。
#
# 修復目標：第 N 次 tick 時間 ≈ start + N × interval（不論 work 耗時多少）。
#
# 測試手段：patch asyncio.sleep 記錄 delay 序列，並模擬 work 耗時。
#           sleep delay 應該隨著 work 耗時而減少（補償策略），
#           使 cumulative time (work + sleep) 每次都剛好落在 N × interval。

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from csp_lib.can.clients.base import AsyncCANClientBase
from csp_lib.can.config import CANFrame
from csp_lib.equipment.device.can_device import AsyncCANDevice, CANRxFrameDefinition
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.processing.can_parser import CANField, CANFrameParser


class _MockCANClient(AsyncCANClientBase):
    """簡易 Mock CAN Client（不影響 snapshot_loop 測試）"""

    def __init__(self) -> None:
        self.connected = False
        self._handlers: dict[int, list] = {}

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def is_connected(self) -> bool:
        return self.connected

    async def start_listener(self) -> None:
        pass

    async def stop_listener(self) -> None:
        pass

    def subscribe(self, can_id, handler):
        self._handlers.setdefault(can_id, []).append(handler)
        return lambda: None

    async def send(self, can_id, data):
        pass

    async def request(self, can_id, data, response_id, timeout=1.0):
        return CANFrame(can_id=response_id, data=b"\x00" * 8)


def _make_device(read_interval: float = 1.0) -> AsyncCANDevice:
    """建立最小 CAN 設備（僅 RX，無 TX，用於 snapshot_loop 測試）"""
    bms_parser = CANFrameParser(
        source_name="bms",
        fields=[CANField("soc", 0, 8, resolution=1.0)],
    )
    return AsyncCANDevice(
        config=DeviceConfig(device_id="test_can_drift", read_interval=read_interval),
        client=_MockCANClient(),
        rx_frame_definitions=[CANRxFrameDefinition(can_id=0x100, parser=bms_parser)],
    )


async def _run_snapshot_loop_with_captured_sleep(
    device: AsyncCANDevice,
    work_duration: float,
    iterations: int,
) -> list[float]:
    """
    跑 snapshot loop N 次，回傳每次 asyncio.sleep 的 delay 序列。

    - asyncio.sleep 被替換為：記錄 delay + 用 real sleep(0) 讓 event loop 推進。
    - 透過 monkey-patch device._evaluate_alarm 模擬 work 耗時 W（以累計 fake clock 方式）。
    - 跑完 N 次後 cancel snapshot task。

    關鍵設計：
      用「虛擬時間」而不是 real sleep work_duration，避免測試真跑很慢。
      在 _evaluate_alarm 內將 fake_clock 往前推 work_duration 秒，
      這樣修復版的 sleep_to_next_tick 可以根據 fake_clock 計算出
      下一次 tick 應該 sleep 多少。
    """
    real_sleep = asyncio.sleep
    sleep_delays: list[float] = []
    fake_clock = [0.0]  # 虛擬 monotonic 時間

    async def fake_sleep(delay: float) -> None:
        """記錄 delay 並推進虛擬時鐘"""
        sleep_delays.append(delay)
        fake_clock[0] += max(0.0, delay)
        await real_sleep(0)  # 讓 event loop 真正推進，其他 coroutine 才能跑

    def fake_monotonic() -> float:
        """回傳虛擬 monotonic 時間（給 source 端 absolute anchoring 使用）"""
        return fake_clock[0]

    # Monkey-patch _evaluate_alarm: 模擬 work 耗時（推進 fake_clock）
    original_eval = device._evaluate_alarm

    async def fake_eval(values):
        fake_clock[0] += work_duration
        await real_sleep(0)
        # 呼叫原本的（不會有 alarm 所以很快）
        await original_eval(values)

    device._evaluate_alarm = fake_eval  # type: ignore[method-assign]

    # Patch asyncio.sleep + time.monotonic in the can_device module where they are imported
    with (
        patch("csp_lib.equipment.device.can_device.asyncio.sleep", fake_sleep),
        patch("csp_lib.equipment.device.can_device.time.monotonic", fake_monotonic),
    ):
        task = asyncio.create_task(device._snapshot_loop())
        # 等 sleep_delays 累積到 iterations 次
        deadline_iters = iterations
        for _ in range(deadline_iters * 10):
            if len(sleep_delays) >= deadline_iters:
                break
            await real_sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    return sleep_delays


class TestCANSnapshotLoopDrift:
    """WI-TD-101: CAN snapshot_loop 時序漂移"""

    async def test_snapshot_loop_compensates_work_duration(self):
        """
        Snapshot loop 應根據上一次 work 耗時補償 sleep delay，
        使得每次 tick 落在 absolute anchor + N × interval。

        修復前：所有 sleep 都是固定 interval（1.0），完全不補償 work 耗時。
        修復後：sleep delay 應 ≈ interval - work_duration（考慮累計誤差）。
        """
        interval = 1.0
        work = 0.3  # 每次 work 耗時 0.3s
        iterations = 5

        device = _make_device(read_interval=interval)
        delays = await _run_snapshot_loop_with_captured_sleep(device, work, iterations)

        assert len(delays) >= iterations, f"只捕捉到 {len(delays)} 次 sleep，需要 {iterations}"

        # 關鍵斷言：第 2 次以後的 sleep 應該補償 work 耗時（≈ interval - work）
        # 修復前：所有 delay 都是 1.0（固定 interval） → 明顯偏離 interval - work = 0.7
        # 修復後：delay 應接近 0.7（扣除 work 耗時）
        #
        # 以「cumulative time 對齊 N × interval」為更強斷言：
        # 到第 N 次 tick 結束（即第 N 個 sleep 完成後），累計時間應 ≈ N × interval。
        cumulative = 0.0
        drifts = []
        for i, d in enumerate(delays[:iterations], start=1):
            cumulative += work + d  # 每個 iteration = work + sleep
            expected = i * interval
            drifts.append(cumulative - expected)

        # 修復後：cumulative 漂移應 ≈ 0（誤差 < 1% × interval × iterations）
        max_drift = max(abs(x) for x in drifts)
        tolerance = 0.01 * interval * iterations  # 1% tolerance
        assert max_drift < tolerance, (
            f"Snapshot loop 出現時序漂移：最大偏移 {max_drift:.3f}s，"
            f"tolerance {tolerance:.3f}s，delays={delays[:iterations]}, drifts={drifts}"
        )

    async def test_snapshot_loop_heavy_work_does_not_accumulate_drift(self):
        """
        重負載場景（work 接近 interval）下，長時間執行不應累積漂移。

        修復前：每次 tick 實際週期 = interval + work，10 次後漂移 = 10 × work。
        修復後：cumulative 仍對齊 N × interval（若 work > interval 則應 sleep=0 但不補 catch-up）。
        """
        interval = 1.0
        work = 0.5
        iterations = 10

        device = _make_device(read_interval=interval)
        delays = await _run_snapshot_loop_with_captured_sleep(device, work, iterations)

        assert len(delays) >= iterations

        # 計算第 N 次 tick 結束後的累計時間
        cumulative = 0.0
        for d in delays[:iterations]:
            cumulative += work + d

        expected = iterations * interval
        drift = cumulative - expected

        # 修復前：drift ≈ iterations × work = 10 × 0.5 = 5.0
        # 修復後：drift < 0.1s
        assert abs(drift) < 0.1, f"重負載下累計漂移 {drift:.3f}s (expected ≈ 0)，delays={delays[:iterations]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
