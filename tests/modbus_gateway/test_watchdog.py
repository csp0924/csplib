"""Tests for CommunicationWatchdog -- timeout detection and callbacks."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from csp_lib.modbus_gateway.config import WatchdogConfig
from csp_lib.modbus_gateway.watchdog import CommunicationWatchdog
from tests.helpers import wait_for_condition


class TestWatchdogProperties:
    def test_initial_state(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=10))
        assert wd.is_timed_out is False
        assert wd.elapsed >= 0

    def test_touch_updates_last_communication(self):
        t = [100.0]
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=10), clock=lambda: t[0])
        t[0] = 105.0
        wd.touch()
        assert wd.last_communication == 105.0


class TestWatchdogCallbacks:
    def test_on_timeout_registers(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=10))
        cb = AsyncMock()
        wd.on_timeout(cb)
        assert len(wd._timeout_callbacks) == 1

    def test_on_recover_registers(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=10))
        cb = AsyncMock()
        wd.on_recover(cb)
        assert len(wd._recover_callbacks) == 1


class TestWatchdogLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=60, check_interval=0.5))
        await wd.start()
        try:
            assert wd._task is not None
            assert not wd._task.done()
        finally:
            await wd.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=60, check_interval=0.5))
        await wd.start()
        await wd.stop()
        assert wd._task is None or wd._task.done()

    @pytest.mark.asyncio
    async def test_start_disabled_does_nothing(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=60, enabled=False))
        await wd.start()
        assert wd._task is None

    @pytest.mark.asyncio
    async def test_stop_without_start_safe(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=60))
        await wd.stop()


class TestWatchdogTimeout:
    @pytest.mark.asyncio
    async def test_timeout_callback_fires(self):
        """Inject clock → advance past timeout → callback fires."""
        t = [100.0]
        wd = CommunicationWatchdog(
            WatchdogConfig(timeout_seconds=10, check_interval=0.01),
            clock=lambda: t[0],
        )
        cb = AsyncMock()
        wd.on_timeout(cb)
        await wd.start()
        try:
            t[0] = 115.0  # 15s elapsed > 10s timeout
            await wait_for_condition(lambda: cb.called, message="timeout callback should fire")
            assert wd.is_timed_out is True
        finally:
            await wd.stop()

    @pytest.mark.asyncio
    async def test_no_timeout_when_touched(self):
        """Touch keeps resetting the clock."""
        t = [100.0]
        wd = CommunicationWatchdog(
            WatchdogConfig(timeout_seconds=10, check_interval=0.01),
            clock=lambda: t[0],
        )
        cb = AsyncMock()
        wd.on_timeout(cb)
        await wd.start()
        try:
            t[0] = 105.0
            wd.touch()  # resets last_comm to 105
            t[0] = 110.0  # only 5s elapsed, < 10s timeout
            # 必要的短等待：測試「不觸發」需讓 check loop 至少跑一輪（check_interval=0.01s）
            await asyncio.sleep(0.02)
            cb.assert_not_called()
            assert wd.is_timed_out is False
        finally:
            await wd.stop()


class TestWatchdogRecovery:
    @pytest.mark.asyncio
    async def test_recover_callback_fires(self):
        """After timeout, touch → recovery callback."""
        t = [100.0]
        wd = CommunicationWatchdog(
            WatchdogConfig(timeout_seconds=10, check_interval=0.01),
            clock=lambda: t[0],
        )
        timeout_cb = AsyncMock()
        recover_cb = AsyncMock()
        wd.on_timeout(timeout_cb)
        wd.on_recover(recover_cb)
        await wd.start()
        try:
            # Trigger timeout
            t[0] = 115.0
            await wait_for_condition(lambda: wd.is_timed_out, message="watchdog should timeout")

            # Touch to recover
            wd.touch()  # last_comm = 115
            t[0] = 116.0  # elapsed = 1s < 10s
            await wait_for_condition(lambda: recover_cb.called, message="recover callback should fire")
            assert wd.is_timed_out is False
        finally:
            await wd.stop()


class TestWatchdogCallbackExceptions:
    @pytest.mark.asyncio
    async def test_timeout_callback_exception_doesnt_crash(self):
        """Failing callback should not kill the watchdog loop."""
        t = [100.0]
        wd = CommunicationWatchdog(
            WatchdogConfig(timeout_seconds=10, check_interval=0.01),
            clock=lambda: t[0],
        )
        bad_cb = AsyncMock(side_effect=RuntimeError("boom"))
        wd.on_timeout(bad_cb)
        await wd.start()
        try:
            t[0] = 115.0
            await wait_for_condition(lambda: bad_cb.called, message="timeout callback should fire")
            assert wd._task is not None
            assert not wd._task.done()
        finally:
            await wd.stop()
