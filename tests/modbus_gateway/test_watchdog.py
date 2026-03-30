"""Tests for CommunicationWatchdog — timeout detection and callbacks."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from csp_lib.modbus_gateway.config import WatchdogConfig
from csp_lib.modbus_gateway.watchdog import CommunicationWatchdog

# ===========================================================================
# Construction & Properties
# ===========================================================================


class TestWatchdogProperties:
    def test_initial_state(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=10))
        assert wd.is_timed_out is False
        assert wd.elapsed >= 0

    def test_touch_updates_last_communication(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=10))
        old_ts = wd.last_communication
        wd.touch()
        assert wd.last_communication >= old_ts


# ===========================================================================
# Callback registration
# ===========================================================================


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


# ===========================================================================
# Start / stop
# ===========================================================================


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
        assert wd._task is None

    @pytest.mark.asyncio
    async def test_start_disabled_does_nothing(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=60, enabled=False))
        await wd.start()
        assert wd._task is None

    @pytest.mark.asyncio
    async def test_stop_without_start_safe(self):
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=60))
        await wd.stop()  # should not raise


# ===========================================================================
# Timeout detection
# ===========================================================================


class TestWatchdogTimeout:
    @pytest.mark.asyncio
    async def test_timeout_callback_fires(self):
        """After timeout_seconds without touch, timeout callback should fire."""
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=0.1, check_interval=0.05))
        cb = AsyncMock()
        wd.on_timeout(cb)
        await wd.start()
        try:
            # Wait for timeout + check interval
            await asyncio.sleep(0.3)
            cb.assert_called()
            assert wd.is_timed_out is True
        finally:
            await wd.stop()

    @pytest.mark.asyncio
    async def test_no_timeout_when_touched(self):
        """Regular touches should prevent timeout."""
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=0.2, check_interval=0.05))
        cb = AsyncMock()
        wd.on_timeout(cb)
        await wd.start()
        try:
            for _ in range(5):
                wd.touch()
                await asyncio.sleep(0.05)
            cb.assert_not_called()
            assert wd.is_timed_out is False
        finally:
            await wd.stop()


# ===========================================================================
# Recovery detection
# ===========================================================================


class TestWatchdogRecovery:
    @pytest.mark.asyncio
    async def test_recover_callback_fires(self):
        """After timeout, a touch should trigger recovery callback."""
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=0.15, check_interval=0.05))
        timeout_cb = AsyncMock()
        recover_cb = AsyncMock()
        wd.on_timeout(timeout_cb)
        wd.on_recover(recover_cb)
        await wd.start()
        try:
            # Wait for timeout
            await asyncio.sleep(0.35)
            assert wd.is_timed_out is True
            # Touch to recover, then keep touching to prevent re-timeout
            wd.touch()
            await asyncio.sleep(0.08)
            wd.touch()
            await asyncio.sleep(0.08)
            recover_cb.assert_called()
            assert wd.is_timed_out is False
        finally:
            await wd.stop()


# ===========================================================================
# Callback exception handling
# ===========================================================================


class TestWatchdogCallbackExceptions:
    @pytest.mark.asyncio
    async def test_timeout_callback_exception_doesnt_crash(self):
        """A failing timeout callback should not crash the watchdog loop."""
        wd = CommunicationWatchdog(WatchdogConfig(timeout_seconds=0.1, check_interval=0.05))
        bad_cb = AsyncMock(side_effect=RuntimeError("boom"))
        wd.on_timeout(bad_cb)
        await wd.start()
        try:
            await asyncio.sleep(0.3)
            bad_cb.assert_called()
            # Watchdog should still be running
            assert wd._task is not None
            assert not wd._task.done()
        finally:
            await wd.stop()
