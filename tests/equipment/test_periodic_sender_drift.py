# =============== Tests - PeriodicSendScheduler 時序漂移 (WI-TD-102) ===============
#
# 重現 csp_lib/equipment/transport/periodic_sender.py:108-120 的時序漂移 bug：
#
#   async def _send_loop(self, can_id: int, interval: float) -> None:
#       while self._running:
#           try:
#               if can_id not in self._paused:
#                   data = self._frame_buffer.get_frame(can_id)
#                   await self._send_callback(can_id, data)     # ← work 耗時 W
#               await asyncio.sleep(interval)                    # ← 固定等 interval
#           ...
#
# 問題：send_callback 耗時 W 不會扣在 sleep delay 裡，累積漂移 N × W。
#
# 修復目標：send 時間對齊 start + N × interval（不論 send 耗時多少）。
#
# 測試手段：patch asyncio.sleep 記錄每個 can_id 的 delay 序列，
#           驗證 sleep delay 補償了 send 耗時，且多個 can_id 的基準互相獨立。

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from csp_lib.equipment.transport.periodic_sender import (
    PeriodicFrameConfig,
    PeriodicSendScheduler,
)


def _make_scheduler(
    configs: list[PeriodicFrameConfig],
    send_duration: float,
    fake_clock: list[float],
) -> PeriodicSendScheduler:
    """
    建立 PeriodicSendScheduler，send_callback 模擬耗時 send_duration。

    為了讓測試不真的等待，send_callback 只推進 fake_clock（虛擬時鐘），
    並 await real_sleep(0) 讓出 event loop。
    """
    frame_buffer = MagicMock()
    frame_buffer.get_frame = MagicMock(return_value=b"\x00" * 8)

    async def send_callback(can_id: int, data: bytes) -> None:
        fake_clock[0] += send_duration
        # 真讓出控制權（模擬網路 I/O）
        await asyncio.sleep.__wrapped__(0) if hasattr(asyncio.sleep, "__wrapped__") else None

    return PeriodicSendScheduler(
        frame_buffer=frame_buffer,
        send_callback=send_callback,
        configs=configs,
    )


async def _run_scheduler_with_captured_sleep(
    scheduler: PeriodicSendScheduler,
    can_ids: list[int],
    iterations_per_id: int,
    fake_clock: list[float],
) -> dict[int, list[float]]:
    """
    啟動 scheduler，為每個 can_id 捕捉 asyncio.sleep 的 delay 序列。

    因為每個 can_id 有獨立的 _send_loop task，但它們共用 asyncio.sleep，
    我們透過「當前 task name」區分屬於哪個 can_id。

    fake_clock：與 _make_scheduler 共用的虛擬時鐘。fake_sleep 推進它，
    並 patch time.monotonic 回傳同一個值，讓 source 端的 absolute
    anchoring 邏輯（next_time - time.monotonic()）能用虛擬時間計算。
    """
    real_sleep = asyncio.sleep
    delays_per_id: dict[int, list[float]] = {cid: [] for cid in can_ids}

    async def fake_sleep(delay: float) -> None:
        # 透過 task name 判斷屬於哪個 can_id（scheduler.start() 會命名為 periodic_sender_0xNNN）
        task = asyncio.current_task()
        name = task.get_name() if task else ""
        for cid in can_ids:
            if f"0x{cid:03X}" in name:
                delays_per_id[cid].append(delay)
                break
        fake_clock[0] += max(0.0, delay)
        await real_sleep(0)  # 讓 event loop 推進

    def fake_monotonic() -> float:
        return fake_clock[0]

    with (
        patch("csp_lib.equipment.transport.periodic_sender.asyncio.sleep", fake_sleep),
        patch("csp_lib.equipment.transport.periodic_sender.time.monotonic", fake_monotonic),
    ):
        await scheduler.start()
        # 等每個 can_id 累積到足夠 sleep 次數
        for _ in range(iterations_per_id * 50):
            if all(len(delays_per_id[cid]) >= iterations_per_id for cid in can_ids):
                break
            await real_sleep(0)
        await scheduler.stop()

    return delays_per_id


class TestPeriodicSenderDrift:
    """WI-TD-102: PeriodicSendScheduler 時序漂移"""

    async def test_send_loop_compensates_send_duration(self):
        """
        _send_loop 應根據 send_callback 耗時補償 sleep delay。

        修復前：sleep delay 固定 = interval，累積漂移 N × send_duration。
        修復後：cumulative (send + sleep) 對齊 N × interval。
        """
        interval = 1.0
        send_duration = 0.2
        iterations = 5
        can_id = 0x200
        fake_clock = [0.0]

        scheduler = _make_scheduler(
            configs=[PeriodicFrameConfig(can_id=can_id, interval=interval)],
            send_duration=send_duration,
            fake_clock=fake_clock,
        )

        delays = await _run_scheduler_with_captured_sleep(
            scheduler, can_ids=[can_id], iterations_per_id=iterations, fake_clock=fake_clock
        )

        captured = delays[can_id]
        assert len(captured) >= iterations, f"僅捕捉 {len(captured)} 次 sleep"

        # 計算 cumulative time (send + sleep) vs expected (N × interval)
        cumulative = 0.0
        drifts = []
        for i, d in enumerate(captured[:iterations], start=1):
            cumulative += send_duration + d
            drifts.append(cumulative - i * interval)

        max_drift = max(abs(x) for x in drifts)
        tolerance = 0.01 * interval * iterations  # 1%

        # 修復前：每次 iteration 累加 send_duration 漂移，drifts=[0.2, 0.4, 0.6, 0.8, 1.0]
        # 修復後：drifts ≈ [0, 0, 0, 0, 0]
        assert max_drift < tolerance, (
            f"PeriodicSender 時序漂移：最大偏移 {max_drift:.3f}s，"
            f"tolerance {tolerance:.3f}s，delays={captured[:iterations]}, drifts={drifts}"
        )

    async def test_multiple_can_ids_independent_anchors(self):
        """
        多個 CAN ID 不同 interval，每個 send loop 都應該獨立運作並各自有 anchor。

        說明：本測試僅驗證「scheduler 為每個 can_id 建立獨立 task 且各自捕捉到 sleep」，
        不嚴格驗證跨 task 的 drift（在共享 fake_clock 的測試模型下，慢 task 的
        sleep 推進虛擬時鐘會讓快 task 看似落後，這是 mock 設計的人工現象，
        在真實 asyncio 並發中不存在 — 真實情境每個 task 各自看 wall clock）。

        每個 can_id 的 drift 補償行為已由 `test_send_loop_compensates_send_duration`
        以單一 task 驗證。本測試只確保多 task 並行不互相阻塞、各自有第一次補償的
        sleep delay。
        """
        send_duration = 0.15
        iterations = 4
        can_id_fast = 0x200  # interval 0.5s
        can_id_slow = 0x300  # interval 1.0s
        fake_clock = [0.0]

        scheduler = _make_scheduler(
            configs=[
                PeriodicFrameConfig(can_id=can_id_fast, interval=0.5),
                PeriodicFrameConfig(can_id=can_id_slow, interval=1.0),
            ],
            send_duration=send_duration,
            fake_clock=fake_clock,
        )

        delays = await _run_scheduler_with_captured_sleep(
            scheduler,
            can_ids=[can_id_fast, can_id_slow],
            iterations_per_id=iterations,
            fake_clock=fake_clock,
        )

        for can_id, interval in [(can_id_fast, 0.5), (can_id_slow, 1.0)]:
            captured = delays[can_id]
            assert len(captured) >= 1, f"can_id 0x{can_id:03X} 完全沒被排程到 sleep（task 未啟動）"
            # 第一次 sleep 必須是補償後的值（≈ interval - send_duration），
            # 證明 work-first anchoring 邏輯生效；後續因共享 fake_clock 而失真，不檢查
            first_delay = captured[0]
            expected_first = interval - send_duration
            assert abs(first_delay - expected_first) < 0.01, (
                f"can_id 0x{can_id:03X} 第一次 sleep delay={first_delay}，"
                f"期望 ≈ {expected_first}（interval={interval} - send={send_duration}）"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
