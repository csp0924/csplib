# =============== Tests - AsyncModbusDevice._read_loop 時序漂移 (WI-TD-103) ===============
#
# 重現 csp_lib/equipment/device/base.py:691-725 的兩個 bug：
#
# (1) 基礎漂移：目前用 elapsed = monotonic() - start_time; sleep = max(0, interval - elapsed)。
#     問題：若 read 耗時 > interval，sleep=0 直接下一輪，累積誤差不會補償；
#           若一次 read 暫時延遲，之後仍然維持新的錯位基準，無 absolute anchor 對齊。
#
# (2) 重連後 burst catch-up：當斷線一段時間（如 5-10s），重連成功後以 monotonic() 重新 anchoring，
#     但若實作保留了 absolute anchor 卻缺乏 reset，會導致連續幾次 read 的 sleep=0（catch-up bursts）。
#     修復目標：reconnect 成功後應重設 anchor，使下一次 read 時間 ≈ reconnect_time + interval（不 burst）。
#
# 測試手段：
#   - patch asyncio.sleep 記錄 delay 序列
#   - mock read_once 返回 {} 但推進 fake_clock（模擬 read 耗時）
#   - 對於重連測試：控制 client.connect 先成功 → 拋 DeviceConnectionError → 再成功

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from csp_lib.core.errors import DeviceConnectionError
from csp_lib.equipment.core import ReadPoint
from csp_lib.equipment.device.base import AsyncModbusDevice
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.modbus import UInt16


def _make_device(read_interval: float = 1.0, reconnect_interval: float = 1.0) -> AsyncModbusDevice:
    """建立最小 Modbus 設備（read_loop 用）"""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()

    device = AsyncModbusDevice(
        config=DeviceConfig(
            device_id="test_modbus_drift",
            unit_id=1,
            read_interval=read_interval,
            reconnect_interval=reconnect_interval,
        ),
        client=client,
        always_points=[ReadPoint(name="power", address=100, data_type=UInt16())],
    )
    # 預設連線狀態（避開 reconnect 分支）
    device._client_connected = True
    device._device_responsive = True
    return device


class TestModbusReadLoopDrift:
    """WI-TD-103 (a): _read_loop 基礎時序漂移"""

    async def test_read_loop_recovers_anchor_after_slow_iteration(self):
        """
        一次 read 異常耗時超過 interval 後，後續 read 應回歸 absolute anchor，
        不應永久錯位。

        修復前：elapsed-subtraction 模式下，慢 iteration 之後 sleep=0 就進入下一輪，
                但下一輪的 start_time 已經延遲了，**再也回不到原本 anchor**。
        修復後：以 absolute anchor 計算下一次 tick，跳過錯過的 tick，但不累積漂移。

        場景：interval=1.0，iteration 1 正常 (0.2s)，iteration 2 異常 (1.5s)，
              iteration 3、4 正常 (0.2s)。
              修復後：到 iteration 4 結束時，cumulative ≈ 4 × interval = 4.0（容忍一次錯過的 tick 即 +1s 內）。
              修復前：cumulative = 0.2 + 0.8 + 1.5 + 0 + 0.2 + 0.8 + 0.2 + 0.8 = 4.5（永久錯位）。
        """
        interval = 1.0
        iterations = 4

        device = _make_device(read_interval=interval)

        real_sleep = asyncio.sleep
        sleep_delays: list[float] = []
        fake_clock = [0.0]
        read_durations = [0.2, 1.5, 0.2, 0.2]  # 第 2 次異常
        read_count = [0]

        def fake_monotonic() -> float:
            return fake_clock[0]

        async def fake_sleep(delay: float) -> None:
            sleep_delays.append(delay)
            fake_clock[0] += max(0.0, delay)
            await real_sleep(0)

        async def fake_read_once() -> dict:
            idx = read_count[0]
            dur = read_durations[idx] if idx < len(read_durations) else 0.2
            read_count[0] += 1
            fake_clock[0] += dur
            await real_sleep(0)
            return {}

        device.read_once = fake_read_once  # type: ignore[method-assign]

        with (
            patch("csp_lib.equipment.device.base.asyncio.sleep", fake_sleep),
            patch("csp_lib.equipment.device.base.time.monotonic", fake_monotonic),
        ):
            task = asyncio.create_task(device._read_loop())
            for _ in range(iterations * 30):
                if len(sleep_delays) >= iterations:
                    break
                await real_sleep(0)
            device._stop_event.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 修復前實際 timeline（elapsed-subtraction）：
        #   iter1: read 0.2 → sleep 0.8 → clock=1.0
        #   iter2: read 1.5 → sleep 0   → clock=2.5（已漂移 0.5s）
        #   iter3: read 0.2 → sleep 0.8 → clock=3.5（永遠落後 0.5s）
        #   iter4: read 0.2 → sleep 0.8 → clock=4.5
        #   cumulative@iter4 = 4.5，expected = 4.0，drift = 0.5s（永久）
        #
        # 修復後（absolute anchor + skip missed ticks）：
        #   iter1: read@0.2 → sleep to tick 1.0（0.8s）→ clock=1.0
        #   iter2: read@2.5 （超過 tick 2.0）→ 直接下一個 tick=3.0，sleep 0.5 → clock=3.0
        #   iter3: read@3.2 → sleep to tick 4.0（0.8）→ clock=4.0
        #   iter4: read@4.2 → sleep to tick 5.0（0.8）→ clock=5.0
        #   cumulative@iter4 = 5.0，expected @ iter4 = 5.0（因為跳過一個 tick），drift=0
        final_clock = fake_clock[0]

        # 合理期望：final_clock 應對齊整數秒（N × interval），誤差 < 0.1s
        # 因為跳過一個 tick，final_clock 應該是 5.0（4 iters 但對應到 tick 5），
        # 而不是 4.5（elapsed-subtraction 的錯位結果）。
        # 更一般化的斷言：final_clock 應為 interval 的整數倍。
        aligned_remainder = final_clock % interval
        aligned_distance = min(aligned_remainder, interval - aligned_remainder)

        assert aligned_distance < 0.1, (
            f"慢 iteration 後 anchor 未回歸：final_clock={final_clock:.3f}s, "
            f"distance_to_aligned_tick={aligned_distance:.3f}s, "
            f"delays={sleep_delays[:iterations]}"
        )


class TestModbusReadLoopReconnectBurst:
    """WI-TD-103 (b): reconnect 後 burst catch-up bug"""

    async def test_reconnect_does_not_cause_burst_catchup(self):
        """
        當 read_loop 因斷線長時間停留在 reconnect 迴圈後，重連成功時
        應該重設 anchor，下一次 read 的 sleep 不應為 0（burst catch-up）。

        修復前（若實作保留 absolute anchor 但缺 reset）：
            斷線 10s 後重連 → 下一次 sleep 被計算為「回到 anchor」= 0 → burst；
            連續幾次 read sleep=0，高速 catch-up，可能壓垮設備。
        修復後：reconnect 成功後重設 anchor 為 now，下一次 sleep ≈ interval。

        注意：目前 base.py 實作用 per-iteration `start_time = monotonic()` 計算 elapsed，
              reconnect 分支 `continue` 後下一輪會重設 start_time，所以**目前實作沒有 burst 問題**。
              但架構要求修復為 absolute anchor 後，**必須** 在 reconnect 成功後 reset anchor，
              否則會引入新 bug。此測試是為修復版本設計的「防止 regress」測試。

        場景：
          - iter1 正常（read 0.2s → sleep 0.8s）
          - 然後 client.connect 丟 DeviceConnectionError 模擬斷線持續 5s
          - 5s 後 connect 成功，執行 iter2
          - 驗證：iter2 後的 sleep 不應為 0（不 burst catch-up）
        """
        interval = 1.0
        reconnect_interval = 1.0

        device = _make_device(
            read_interval=interval,
            reconnect_interval=reconnect_interval,
        )

        real_sleep = asyncio.sleep
        sleep_delays: list[tuple[str, float]] = []  # (phase, delay)
        fake_clock = [0.0]

        # 讀取一次正常後模擬斷線，再重連成功
        read_count = [0]
        connect_attempts = [0]
        disconnect_started_at = [None]  # type: list[float | None]

        def fake_monotonic() -> float:
            return fake_clock[0]

        async def fake_sleep(delay: float) -> None:
            # 根據當前狀態標記 phase
            phase = "connected" if device._client_connected else "reconnect"
            sleep_delays.append((phase, delay))
            fake_clock[0] += max(0.0, delay)
            await real_sleep(0)

        async def fake_read_once() -> dict:
            read_count[0] += 1
            fake_clock[0] += 0.2  # read 耗時 0.2s
            await real_sleep(0)
            # iter1 正常結束後，標記斷線
            if read_count[0] == 1:
                device._client_connected = False
                disconnect_started_at[0] = fake_clock[0]
            return {}

        async def fake_client_connect() -> None:
            connect_attempts[0] += 1
            # 持續失敗 5 次（reconnect_interval=1s，所以失敗 5s）
            if connect_attempts[0] <= 5:
                raise DeviceConnectionError(device._config.device_id, "simulated disconnect")
            # 第 6 次成功
            # client.connect 成功後 read_loop 會把 _client_connected 設為 True

        device._client.connect = fake_client_connect  # type: ignore[method-assign]
        device.read_once = fake_read_once  # type: ignore[method-assign]

        with (
            patch("csp_lib.equipment.device.base.asyncio.sleep", fake_sleep),
            patch("csp_lib.equipment.device.base.time.monotonic", fake_monotonic),
        ):
            task = asyncio.create_task(device._read_loop())
            # 等：iter1 + 5 次 reconnect 失敗 + iter2
            for _ in range(200):
                if read_count[0] >= 2 and connect_attempts[0] >= 6:
                    # 多給幾輪，讓 iter2 後的 sleep 也記到
                    for _ in range(5):
                        await real_sleep(0)
                    break
                await real_sleep(0)
            device._stop_event.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 找出 iter2 之後的第一個 "connected" phase sleep
        connected_sleeps = [d for phase, d in sleep_delays if phase == "connected"]
        assert len(connected_sleeps) >= 2, (
            f"僅捕捉到 {len(connected_sleeps)} 次 connected sleep，全部 sleep：{sleep_delays}"
        )

        # iter2 後的 sleep delay 不應為 0（burst 的 signal）
        # 修復前（若無 anchor reset）：iter2 後 sleep 會嘗試回到 original anchor = 0
        # 修復後：anchor 已 reset，sleep ≈ interval - read_duration = 0.8
        iter2_sleep = connected_sleeps[1]
        assert iter2_sleep > 0.1, (
            f"Reconnect 後出現 burst catch-up：iter2 sleep={iter2_sleep:.3f}s（應 > 0.1），"
            f"全部 connected sleeps={connected_sleeps}, 全部 delays={sleep_delays}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
