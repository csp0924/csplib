# =============== Modbus Gateway - Watchdog ===============
#
# 通訊看門狗（Communication Watchdog）
#
# 監控 EMS 通訊活動，若超過指定時間未收到任何讀寫請求，
# 觸發 timeout 回呼；通訊恢復後觸發 recover 回呼。
#
# 提供：
#   - CommunicationWatchdog: 異步通訊看門狗

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from csp_lib.core import get_logger
from csp_lib.modbus_gateway.config import WatchdogConfig

logger = get_logger(__name__)


class CommunicationWatchdog:
    """Monitors EMS communication activity.

    Runs a periodic check task. If no communication (read or write) is
    observed within ``timeout_seconds``, invokes all registered timeout
    callbacks.  When communication resumes, invokes all registered
    recover callbacks.

    Thread-safe: :meth:`touch` can be called from the pymodbus server
    thread because it performs a single atomic float assignment.

    Args:
        config: Watchdog configuration (timeout, check interval, enabled).

    Example::

        watchdog = CommunicationWatchdog(WatchdogConfig(timeout_seconds=30))
        watchdog.on_timeout(my_timeout_handler)
        watchdog.on_recover(my_recover_handler)
        await watchdog.start()
        # ... later, in request handler:
        watchdog.touch()
    """

    def __init__(self, config: WatchdogConfig) -> None:
        self._config = config
        self._last_comm: float = time.monotonic()
        self._timed_out: bool = False
        self._timeout_callbacks: list[Callable[[], Awaitable[None]]] = []
        self._recover_callbacks: list[Callable[[], Awaitable[None]]] = []
        self._task: asyncio.Task[None] | None = None

    def touch(self) -> None:
        """Record a communication event.

        Thread-safe: performs a single atomic float write.
        """
        self._last_comm = time.monotonic()

    @property
    def is_timed_out(self) -> bool:
        """Whether the watchdog is currently in timeout state."""
        return self._timed_out

    @property
    def last_communication(self) -> float:
        """Monotonic timestamp of the most recent communication event."""
        return self._last_comm

    @property
    def elapsed(self) -> float:
        """Seconds since the last recorded communication event."""
        return time.monotonic() - self._last_comm

    def on_timeout(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Register an async callback to be invoked when a timeout is detected.

        Args:
            callback: Async callable with no arguments.
        """
        self._timeout_callbacks.append(callback)

    def on_recover(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Register an async callback to be invoked when communication recovers.

        Args:
            callback: Async callable with no arguments.
        """
        self._recover_callbacks.append(callback)

    async def start(self) -> None:
        """Start the watchdog check loop.

        Does nothing if ``config.enabled`` is ``False``.
        """
        if not self._config.enabled:
            return
        self._last_comm = time.monotonic()
        self._timed_out = False
        self._task = asyncio.create_task(self._check_loop(), name="gateway_watchdog")
        logger.info(
            f"Watchdog started (timeout={self._config.timeout_seconds}s, check_interval={self._config.check_interval}s)"
        )

    async def stop(self) -> None:
        """Cancel the watchdog check loop and wait for it to finish."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Watchdog stopped")

    async def _check_loop(self) -> None:
        """Internal periodic check loop."""
        try:
            while True:
                await asyncio.sleep(self._config.check_interval)
                elapsed = time.monotonic() - self._last_comm

                if elapsed > self._config.timeout_seconds and not self._timed_out:
                    self._timed_out = True
                    logger.warning(f"Watchdog timeout: {elapsed:.0f}s since last communication")
                    for cb in self._timeout_callbacks:
                        try:
                            await cb()
                        except Exception:
                            logger.opt(exception=True).warning("Watchdog timeout callback failed")

                elif elapsed <= self._config.timeout_seconds and self._timed_out:
                    self._timed_out = False
                    logger.info("Watchdog: communication recovered")
                    for cb in self._recover_callbacks:
                        try:
                            await cb()
                        except Exception:
                            logger.opt(exception=True).warning("Watchdog recover callback failed")
        except asyncio.CancelledError:
            pass


__all__ = [
    "CommunicationWatchdog",
]
