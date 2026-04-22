# =============== Manager Device Tests - Partial Failure on Start/Stop ===============
#
# Wave 2b Step 3：DeviceManager._on_start / _on_stop 部分失敗策略測試
#
# 測試覆蓋：
# - Standalone：單一 device connect 失敗不應擋其他 device
# - Standalone：CancelledError 傳播（不吞）
# - Group：單一 device 失敗不擋整 group 啟動
# - Group：ensure_event_loop_started/stopped 失敗時 warn，不擋其他 device
# - _on_stop 對稱測試

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.core.errors import DeviceConnectionError
from csp_lib.manager.device import DeviceManager


def _make_standalone_device(device_id: str) -> MagicMock:
    """建立具備 standalone 模式所需 lifecycle 的 mock device。"""
    device = MagicMock()
    device.device_id = device_id
    device.connect = AsyncMock()
    device.disconnect = AsyncMock()
    device.start = AsyncMock()
    device.stop = AsyncMock()
    return device


def _make_group_device(device_id: str) -> MagicMock:
    """建立具備 group 模式所需 lifecycle 的 mock device。"""
    device = MagicMock()
    device.device_id = device_id
    device.connect = AsyncMock()
    device.disconnect = AsyncMock()
    device.read_once = AsyncMock(return_value={})
    device.ensure_event_loop_started = AsyncMock()
    device.ensure_event_loop_stopped = AsyncMock()
    return device


# ======================== Standalone start partial failure ========================


class TestStandaloneStartPartialFailure:
    """register 後 _on_start 時，單一 device connect 失敗不應阻止其他 device。"""

    async def test_connection_error_on_middle_device_does_not_block_others(self):
        """第二台 connect 拋 DeviceConnectionError → 其他兩台仍 start()。"""
        dev1 = _make_standalone_device("dev_1")
        dev2 = _make_standalone_device("dev_2")
        dev3 = _make_standalone_device("dev_3")
        dev2.connect.side_effect = DeviceConnectionError("dev_2", "timeout")

        manager = DeviceManager()
        manager.register(dev1)
        manager.register(dev2)
        manager.register(dev3)

        await manager.start()
        try:
            # 三台都應呼叫 start（_start_standalone 內 connect 失敗後仍 start）
            dev1.start.assert_awaited_once()
            dev2.start.assert_awaited_once()
            dev3.start.assert_awaited_once()
            # _running 應為 True
            assert manager.is_running is True
        finally:
            await manager.stop()

    async def test_generic_exception_on_connect_does_not_block_others(self):
        """第二台 connect 拋 non-ConnectionError（RuntimeError）→ 其他仍 start。"""
        dev1 = _make_standalone_device("dev_1")
        dev2 = _make_standalone_device("dev_2")
        dev3 = _make_standalone_device("dev_3")
        dev2.connect.side_effect = RuntimeError("unexpected")

        manager = DeviceManager()
        manager.register(dev1)
        manager.register(dev2)
        manager.register(dev3)

        await manager.start()
        try:
            dev1.start.assert_awaited_once()
            dev2.start.assert_awaited_once()
            dev3.start.assert_awaited_once()
        finally:
            await manager.stop()

    async def test_cancelled_error_on_connect_propagates(self):
        """connect 被 CancelledError → _on_start 必須向上傳播。"""
        dev1 = _make_standalone_device("dev_1")
        dev2 = _make_standalone_device("dev_2")
        dev2.connect.side_effect = asyncio.CancelledError()

        manager = DeviceManager()
        manager.register(dev1)
        manager.register(dev2)

        with pytest.raises(asyncio.CancelledError):
            await manager.start()

    async def test_generic_exception_on_start_does_not_block_other_devices(self):
        """start() 本身失敗也不應阻止其他 device（gather return_exceptions=True）。"""
        dev1 = _make_standalone_device("dev_1")
        dev2 = _make_standalone_device("dev_2")
        dev3 = _make_standalone_device("dev_3")
        dev2.start.side_effect = RuntimeError("start boom")

        manager = DeviceManager()
        manager.register(dev1)
        manager.register(dev2)
        manager.register(dev3)

        # 不應 raise；dev2 failure 以 warn 記錄
        await manager.start()
        try:
            dev1.start.assert_awaited_once()
            dev3.start.assert_awaited_once()
        finally:
            await manager.stop()


# ======================== Standalone stop partial failure ========================


class TestStandaloneStopPartialFailure:
    """_on_stop 時單一 device 失敗不應阻止其他 device 收尾。"""

    async def test_stop_failure_does_not_block_other_devices(self):
        """第二台 stop() 拋 RuntimeError → 其他仍 stop + disconnect。"""
        dev1 = _make_standalone_device("dev_1")
        dev2 = _make_standalone_device("dev_2")
        dev3 = _make_standalone_device("dev_3")
        dev2.stop.side_effect = RuntimeError("stop boom")

        manager = DeviceManager()
        manager.register(dev1)
        manager.register(dev2)
        manager.register(dev3)

        await manager.start()
        await manager.stop()

        dev1.stop.assert_awaited_once()
        dev2.stop.assert_awaited_once()
        dev3.stop.assert_awaited_once()
        dev1.disconnect.assert_awaited_once()
        # dev2.disconnect 也會被呼叫（stop 失敗被吞，繼續 disconnect）
        dev2.disconnect.assert_awaited_once()
        dev3.disconnect.assert_awaited_once()
        assert manager.is_running is False

    async def test_disconnect_failure_does_not_block_other_devices(self):
        """第二台 disconnect 失敗 → 其他仍完整收尾。"""
        dev1 = _make_standalone_device("dev_1")
        dev2 = _make_standalone_device("dev_2")
        dev3 = _make_standalone_device("dev_3")
        dev2.disconnect.side_effect = RuntimeError("disconnect boom")

        manager = DeviceManager()
        manager.register(dev1)
        manager.register(dev2)
        manager.register(dev3)

        await manager.start()
        await manager.stop()

        dev1.disconnect.assert_awaited_once()
        dev2.disconnect.assert_awaited_once()
        dev3.disconnect.assert_awaited_once()

    async def test_cancelled_error_on_stop_propagates(self):
        """stop 被 CancelledError → _on_stop 必須向上傳播。"""
        dev1 = _make_standalone_device("dev_1")
        dev2 = _make_standalone_device("dev_2")
        dev2.stop.side_effect = asyncio.CancelledError()

        manager = DeviceManager()
        manager.register(dev1)
        manager.register(dev2)

        await manager.start()
        with pytest.raises(asyncio.CancelledError):
            await manager.stop()


# ======================== Group start partial failure ========================


class TestGroupStartPartialFailure:
    """register_group 後 _on_start 時，單一 device 失敗不應擋整 group。"""

    async def test_connection_error_on_group_device_does_not_block_group_start(self):
        """group 內第二台 connect 失敗 → 其他 device 仍 ensure_event_loop_started，group.start 仍執行。"""
        dev1 = _make_group_device("grp_1")
        dev2 = _make_group_device("grp_2")
        dev3 = _make_group_device("grp_3")
        dev2.connect.side_effect = DeviceConnectionError("dev_2", "timeout")

        manager = DeviceManager()
        manager.register_group([dev1, dev2, dev3], interval=1.0)

        await manager.start()
        try:
            # 三台都應呼叫 ensure_event_loop_started（connect 失敗仍往下）
            dev1.ensure_event_loop_started.assert_awaited_once()
            dev2.ensure_event_loop_started.assert_awaited_once()
            dev3.ensure_event_loop_started.assert_awaited_once()
            assert manager.is_running is True
            assert manager.group_count == 1
        finally:
            await manager.stop()

    async def test_generic_exception_on_group_connect_does_not_block_others(self):
        """group 內 connect 拋 non-ConnectionError → 其他 device 仍啟動。"""
        dev1 = _make_group_device("grp_1")
        dev2 = _make_group_device("grp_2")
        dev3 = _make_group_device("grp_3")
        dev2.connect.side_effect = RuntimeError("unexpected")

        manager = DeviceManager()
        manager.register_group([dev1, dev2, dev3])

        await manager.start()
        try:
            dev1.ensure_event_loop_started.assert_awaited_once()
            dev2.ensure_event_loop_started.assert_awaited_once()
            dev3.ensure_event_loop_started.assert_awaited_once()
        finally:
            await manager.stop()

    async def test_ensure_event_loop_started_failure_does_not_block_others(self):
        """ensure_event_loop_started 失敗 → warn，其他 device 仍 started。"""
        dev1 = _make_group_device("grp_1")
        dev2 = _make_group_device("grp_2")
        dev3 = _make_group_device("grp_3")
        dev2.ensure_event_loop_started.side_effect = RuntimeError("emitter boom")

        manager = DeviceManager()
        manager.register_group([dev1, dev2, dev3])

        # 不應 raise
        await manager.start()
        try:
            dev1.ensure_event_loop_started.assert_awaited_once()
            dev3.ensure_event_loop_started.assert_awaited_once()
            # dev2 被呼叫（拋例外前），也算 awaited
            dev2.ensure_event_loop_started.assert_awaited_once()
        finally:
            await manager.stop()

    async def test_cancelled_error_on_group_connect_propagates(self):
        """group 內 connect 拋 CancelledError → _on_start 向上傳播。"""
        dev1 = _make_group_device("grp_1")
        dev2 = _make_group_device("grp_2")
        dev2.connect.side_effect = asyncio.CancelledError()

        manager = DeviceManager()
        manager.register_group([dev1, dev2])

        with pytest.raises(asyncio.CancelledError):
            await manager.start()


# ======================== Group stop partial failure ========================


class TestGroupStopPartialFailure:
    """_on_stop 時 group 內單一 device 失敗不應擋其他收尾。"""

    async def test_ensure_event_loop_stopped_failure_does_not_block_others(self):
        """ensure_event_loop_stopped 失敗 → warn，其他 device 仍 disconnect。"""
        dev1 = _make_group_device("grp_1")
        dev2 = _make_group_device("grp_2")
        dev3 = _make_group_device("grp_3")
        dev2.ensure_event_loop_stopped.side_effect = RuntimeError("stop emitter boom")

        manager = DeviceManager()
        manager.register_group([dev1, dev2, dev3])

        await manager.start()
        await manager.stop()  # 不應 raise

        dev1.disconnect.assert_awaited_once()
        dev2.disconnect.assert_awaited_once()
        dev3.disconnect.assert_awaited_once()

    async def test_disconnect_failure_in_group_does_not_block_others(self):
        """group 內一台 disconnect 失敗 → 其他仍完整收尾。"""
        dev1 = _make_group_device("grp_1")
        dev2 = _make_group_device("grp_2")
        dev3 = _make_group_device("grp_3")
        dev2.disconnect.side_effect = RuntimeError("disconnect boom")

        manager = DeviceManager()
        manager.register_group([dev1, dev2, dev3])

        await manager.start()
        await manager.stop()

        dev1.ensure_event_loop_stopped.assert_awaited_once()
        dev2.ensure_event_loop_stopped.assert_awaited_once()
        dev3.ensure_event_loop_stopped.assert_awaited_once()
        dev1.disconnect.assert_awaited_once()
        dev3.disconnect.assert_awaited_once()
        assert manager.is_running is False

    async def test_cancelled_error_on_group_stop_propagates(self):
        """group 內 ensure_event_loop_stopped 拋 CancelledError → _on_stop 向上傳播。"""
        dev1 = _make_group_device("grp_1")
        dev2 = _make_group_device("grp_2")
        dev2.ensure_event_loop_stopped.side_effect = asyncio.CancelledError()

        manager = DeviceManager()
        manager.register_group([dev1, dev2])

        await manager.start()
        with pytest.raises(asyncio.CancelledError):
            await manager.stop()


# ======================== 混合模式 partial failure ========================


class TestMixedModePartialFailure:
    """同 manager 下同時有 standalone + group，單一失敗不應互相影響。"""

    async def test_standalone_failure_does_not_block_group(self):
        """standalone 的一台失敗不應影響 group 啟動。"""
        standalone = _make_standalone_device("sa_1")
        standalone.connect.side_effect = RuntimeError("sa boom")

        grp_dev = _make_group_device("grp_1")

        manager = DeviceManager()
        manager.register(standalone)
        manager.register_group([grp_dev])

        await manager.start()
        try:
            # standalone 失敗但仍 start
            standalone.start.assert_awaited_once()
            # group device 正常 ensure_event_loop_started
            grp_dev.ensure_event_loop_started.assert_awaited_once()
        finally:
            await manager.stop()

    async def test_group_failure_does_not_block_standalone(self):
        """group device 失敗不應影響 standalone 啟動。"""
        standalone = _make_standalone_device("sa_1")
        grp_dev = _make_group_device("grp_1")
        grp_dev.ensure_event_loop_started.side_effect = RuntimeError("grp boom")

        manager = DeviceManager()
        manager.register(standalone)
        manager.register_group([grp_dev])

        await manager.start()
        try:
            standalone.start.assert_awaited_once()
        finally:
            await manager.stop()
