# =============== tests/manager/test_device_manager_startup_cancel.py ===============
#
# DeviceManager `_on_start` startup-cancel zombie-task regression tests.
#
# 對應 closed-loop probe H3 假設：
#   - 部分 standalone device 已完成 ``connect()`` + ``start()`` （read_loop task 已建立）
#   - 此時 ``mgr.start()`` 被 cancel
#   - 原行為：``_on_start`` 的 ``finally`` 只 rollback ``_running = False``；
#     後續 ``mgr.stop()`` 命中 ``if not self._running: return`` early-return，
#     已啟動的 device 永遠不會被 stop/disconnect → zombie 殘留
#
# 修復語意：startup cancel rollback 必須清理已成功 ``start()`` 的 standalone device。

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from csp_lib.manager.device import DeviceManager
from tests.helpers import wait_for_condition


class _CancelAwareFakeDevice:
    """模擬 ``AsyncModbusDevice``：``connect`` 可延遲，``start`` 會建立背景 task。

    - ``connect``：可指定延遲（用 ``connect_latency``）
    - ``start``：建立一個 sleep-loop task 模擬 ``read_loop``
    - ``stop``：取消該 task 並等待退出
    - ``disconnect``：no-op，僅累計呼叫次數
    """

    def __init__(self, device_id: str, *, connect_latency: float) -> None:
        self.device_id = device_id
        self._connect_latency = connect_latency
        self._read_loop_task: asyncio.Task[None] | None = None
        self.connect_count = 0
        self.start_count = 0
        self.stop_count = 0
        self.disconnect_count = 0

    async def connect(self) -> None:
        self.connect_count += 1
        await asyncio.sleep(self._connect_latency)

    async def disconnect(self) -> None:
        self.disconnect_count += 1

    async def start(self) -> None:
        self.start_count += 1

        async def _read_loop() -> None:
            try:
                while True:
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                raise

        self._read_loop_task = asyncio.create_task(_read_loop(), name=f"read_loop_{self.device_id}")

    async def stop(self) -> None:
        self.stop_count += 1
        task = self._read_loop_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @property
    def read_loop_alive(self) -> bool:
        return self._read_loop_task is not None and not self._read_loop_task.done()


async def _cleanup_zombies(devices: list[_CancelAwareFakeDevice]) -> None:
    """測試結束 best-effort 收尾：避免遺留 task 污染下個測試。"""
    for d in devices:
        task = d._read_loop_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


class TestDeviceManagerStartupCancelZombies:
    """``_on_start`` 中途 cancel 不應殘留 zombie ``read_loop`` task。"""

    async def test_startup_cancel_drains_already_started_standalone(self) -> None:
        """fast device 已完成 start()、slow device 仍卡在 connect 時 cancel：
        ``_on_start`` 的 rollback 必須關掉 fast device 的 read_loop。
        """
        mgr = DeviceManager()
        fast: list[_CancelAwareFakeDevice] = [
            _CancelAwareFakeDevice(f"fast_{i}", connect_latency=0.001) for i in range(3)
        ]
        slow: list[_CancelAwareFakeDevice] = [
            _CancelAwareFakeDevice(f"slow_{i}", connect_latency=5.0) for i in range(3)
        ]
        all_devices = fast + slow
        for d in all_devices:
            mgr.register(d)

        start_task = asyncio.create_task(mgr.start(), name="mgr.start")
        # 用 wait_for_condition 取代固定 sleep，等 fast device 完成 connect+start
        # （read_loop 已建立），slow 仍卡 connect。避免 CI 排程抖動造成 flaky。
        await wait_for_condition(
            lambda: all(d.start_count == 1 for d in fast),
            timeout=2.0,
            message="fast devices 未在預期時間內完成 start()",
        )

        # sanity：fast device 應已 start()
        assert all(d.start_count == 1 for d in fast), f"fast 應已 start：{[d.start_count for d in fast]}"
        assert all(d.start_count == 0 for d in slow), "slow 不應 start"

        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass

        # 輪詢確認 rollback 完成（manager 不再 running 且 fast 的 read_loop 皆已退出）
        await wait_for_condition(
            lambda: (not mgr.is_running) and all(not d.read_loop_alive for d in fast),
            timeout=2.0,
            message="rollback 後仍有 zombie read_loop 或 mgr 仍 running",
        )

        try:
            # 核心斷言：fast device 的 read_loop 在 rollback 後不應殘留
            alive_fast = [d.device_id for d in fast if d.read_loop_alive]
            assert alive_fast == [], f"startup cancel rollback 未清理 read_loop：{alive_fast}"
            # fast device 應被 stop()
            assert all(d.stop_count >= 1 for d in fast), (
                f"fast device 應在 rollback 中被 stop：{[d.stop_count for d in fast]}"
            )
            # rollback 完畢應視為未 running
            assert mgr.is_running is False
        finally:
            await _cleanup_zombies(all_devices)

    async def test_stop_after_startup_cancel_is_idempotent(self) -> None:
        """startup cancel 之後再呼叫 ``mgr.stop()`` 不會炸、不會二次 stop fast device。"""
        mgr = DeviceManager()
        fast = [_CancelAwareFakeDevice(f"fast_{i}", connect_latency=0.001) for i in range(2)]
        slow = [_CancelAwareFakeDevice(f"slow_{i}", connect_latency=5.0) for i in range(2)]
        all_devices = fast + slow
        for d in all_devices:
            mgr.register(d)

        start_task = asyncio.create_task(mgr.start())
        await wait_for_condition(
            lambda: all(d.start_count == 1 for d in fast),
            timeout=2.0,
            message="fast devices 未在預期時間內完成 start()",
        )
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass

        await wait_for_condition(
            lambda: (not mgr.is_running) and all(not d.read_loop_alive for d in fast),
            timeout=2.0,
            message="rollback 後仍有 zombie read_loop 或 mgr 仍 running",
        )
        prev_stop_counts = {d.device_id: d.stop_count for d in all_devices}

        # 額外的 stop() 不應炸
        await mgr.stop()

        try:
            # stop() 應為 no-op（_running 已 False，無新增 stop 呼叫）
            for d in all_devices:
                assert d.stop_count == prev_stop_counts[d.device_id], (
                    f"額外 stop() 不應再次呼叫 device.stop：{d.device_id}"
                )

            # 仍無 zombie
            alive = [d.device_id for d in all_devices if d.read_loop_alive]
            assert alive == [], f"zombie 殘留：{alive}"
        finally:
            await _cleanup_zombies(all_devices)

    async def test_no_asyncio_task_leak_after_startup_cancel(self) -> None:
        """收尾後 event loop 不應殘留 ``read_loop_*`` 命名的 task。"""
        mgr = DeviceManager()
        fast = [_CancelAwareFakeDevice(f"fast_{i}", connect_latency=0.001) for i in range(3)]
        slow = [_CancelAwareFakeDevice(f"slow_{i}", connect_latency=5.0) for i in range(2)]
        all_devices = fast + slow
        for d in all_devices:
            mgr.register(d)

        start_task = asyncio.create_task(mgr.start())
        await wait_for_condition(
            lambda: all(d.start_count == 1 for d in fast),
            timeout=2.0,
            message="fast devices 未在預期時間內完成 start()",
        )
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass

        # 輪詢等所有 read_loop_ 命名 task 退出，避免固定 sleep 造成 flaky
        await wait_for_condition(
            lambda: not any(t.get_name().startswith("read_loop_") and not t.done() for t in asyncio.all_tasks()),
            timeout=2.0,
            message="rollback 後 read_loop_ task 仍未退出",
        )

        try:
            leaked = [t for t in asyncio.all_tasks() if t.get_name().startswith("read_loop_") and not t.done()]
            assert leaked == [], f"read_loop task 殘留：{[t.get_name() for t in leaked]}"
        finally:
            await _cleanup_zombies(all_devices)


# 提供給 pytest 的 fixture 接管 event loop（與其他測試慣例一致）
@pytest.fixture(autouse=True)
def _silence_asyncio_warnings() -> Any:
    """避免測試環境因 unraisable warning 而 noise。"""
    yield
