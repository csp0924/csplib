# =============== Equipment Device Tests - Event Loop Helpers ===============
#
# Wave 2b Step 2：AsyncModbusDevice public event loop helper 契約測試
#
# 測試覆蓋：
# - ensure_event_loop_started idempotent
# - ensure_event_loop_stopped idempotent
# - standalone start() 間接啟動 emitter worker（不需手動呼 ensure_event_loop_started）

from __future__ import annotations

import asyncio
from typing import Callable
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.core import ReadPoint
from csp_lib.equipment.device.base import AsyncModbusDevice
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.modbus import UInt16


async def _wait_for_condition(pred: Callable[[], bool], timeout: float = 2.0, interval: float = 0.01) -> None:
    """輪詢斷言 helper：避免 sleep-then-assert 的 race。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pred():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.read_holding_registers = AsyncMock(return_value=[1, 2, 3])
    return client


@pytest.fixture
def device(mock_client: AsyncMock) -> AsyncModbusDevice:
    """最小 AsyncModbusDevice 實例供 event loop helper 測試。"""
    return AsyncModbusDevice(
        config=DeviceConfig(
            device_id="ev_dev",
            unit_id=1,
            address_offset=0,
            read_interval=0.05,
        ),
        client=mock_client,
        always_points=[
            ReadPoint(name="p1", address=100, data_type=UInt16()),
            ReadPoint(name="p2", address=101, data_type=UInt16()),
            ReadPoint(name="p3", address=102, data_type=UInt16()),
        ],
    )


# ======================== ensure_event_loop_started / stopped ========================


class TestEnsureEventLoopStarted:
    """ensure_event_loop_started 契約：idempotent, public, await-safe"""

    async def test_ensure_started_starts_emitter_worker(self, device: AsyncModbusDevice):
        """呼叫後 emitter worker 應啟動（_worker_task 不為 None）。"""
        await device.ensure_event_loop_started()
        try:
            # DeviceEventEmitter 啟動後應有 running worker
            assert device._emitter._worker_task is not None
            assert not device._emitter._worker_task.done()
        finally:
            await device.ensure_event_loop_stopped()

    async def test_ensure_started_is_idempotent(self, device: AsyncModbusDevice):
        """連續多次呼叫不應建立多個 worker task。"""
        await device.ensure_event_loop_started()
        first_task = device._emitter._worker_task

        await device.ensure_event_loop_started()
        second_task = device._emitter._worker_task
        await device.ensure_event_loop_started()
        third_task = device._emitter._worker_task

        try:
            # 同一個 task 物件（idempotent）
            assert first_task is second_task is third_task
            assert not first_task.done()
        finally:
            await device.ensure_event_loop_stopped()


class TestEnsureEventLoopStopped:
    """ensure_event_loop_stopped 契約：idempotent, 對稱於 started"""

    async def test_ensure_stopped_stops_emitter_worker(self, device: AsyncModbusDevice):
        """呼叫後 emitter worker 應停止。"""
        await device.ensure_event_loop_started()
        assert device._emitter._worker_task is not None

        await device.ensure_event_loop_stopped()
        # worker task 應 done 或 None（DeviceEventEmitter.stop 內部會等 task 結束）
        assert device._emitter._worker_task is None or device._emitter._worker_task.done()

    async def test_ensure_stopped_is_idempotent_before_start(self, device: AsyncModbusDevice):
        """尚未 start 時呼叫 stop 不應 raise。"""
        # 不該 raise
        await device.ensure_event_loop_stopped()

    async def test_ensure_stopped_is_idempotent_after_start(self, device: AsyncModbusDevice):
        """start 後多次 stop 不應 raise。"""
        await device.ensure_event_loop_started()
        await device.ensure_event_loop_stopped()
        await device.ensure_event_loop_stopped()  # 第二次不 raise
        await device.ensure_event_loop_stopped()  # 第三次不 raise


# ======================== standalone start() 間接啟動 emitter ========================


class TestStandaloneStartImplicitlyStartsEmitter:
    """standalone 模式：device.start() 會間接啟動 emitter（不需手動呼 ensure_event_loop_started）。"""

    async def test_start_implicitly_starts_emitter(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """device.start() 後 emitter worker 應已啟動。"""
        await device.connect()
        await device.start()
        try:
            # 輪詢等 emitter.start() 在 background 完成（避免 sleep-then-assert race）
            await _wait_for_condition(
                lambda: device._emitter._worker_task is not None and not device._emitter._worker_task.done(),
                timeout=2.0,
            )
        finally:
            await device.stop()
            await device.disconnect()

    async def test_stop_implicitly_stops_emitter(self, device: AsyncModbusDevice, mock_client: AsyncMock):
        """device.stop() 後 emitter worker 應停止（對稱契約）。"""
        await device.connect()
        await device.start()
        await device.stop()
        await device.disconnect()
        # emitter 已停止（None 或 done）
        assert device._emitter._worker_task is None or device._emitter._worker_task.done()
