"""Tests for AsyncLifecycleMixin edge cases.

Covers: idempotent start, safe stop-before-start, exception propagation,
nested async-with, and restart after stop.
"""

from __future__ import annotations

import pytest

from csp_lib.core.lifecycle import AsyncLifecycleMixin

# ---------------------------------------------------------------------------
# Helpers — configurable test subclass
# ---------------------------------------------------------------------------


class _StubService(AsyncLifecycleMixin):
    """Subclass with observable start/stop counts and optional failure injection."""

    def __init__(self, *, fail_on_start: bool = False, fail_on_stop: bool = False) -> None:
        self.start_count = 0
        self.stop_count = 0
        self._fail_on_start = fail_on_start
        self._fail_on_stop = fail_on_stop
        self.running = False

    async def _on_start(self) -> None:
        if self._fail_on_start:
            raise RuntimeError("injected start failure")
        self.start_count += 1
        self.running = True

    async def _on_stop(self) -> None:
        if self._fail_on_stop:
            raise RuntimeError("injected stop failure")
        self.stop_count += 1
        self.running = False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAsyncLifecycleEdgeCases:
    """Edge-case tests for AsyncLifecycleMixin."""

    @pytest.mark.asyncio
    async def test_start_calls_on_start(self) -> None:
        """Basic happy path: start() invokes _on_start."""
        svc = _StubService()
        await svc.start()
        assert svc.start_count == 1
        assert svc.running is True

    @pytest.mark.asyncio
    async def test_start_twice_calls_on_start_twice(self) -> None:
        """start() while already running calls _on_start again (no built-in guard).

        AsyncLifecycleMixin is a thin mixin — idempotency is the subclass's
        responsibility.  This test documents the base behaviour.
        """
        svc = _StubService()
        await svc.start()
        await svc.start()
        assert svc.start_count == 2

    @pytest.mark.asyncio
    async def test_stop_before_start_is_safe(self) -> None:
        """stop() on a never-started service must not raise."""
        svc = _StubService()
        await svc.stop()  # should silently invoke _on_stop
        assert svc.stop_count == 1

    @pytest.mark.asyncio
    async def test_exception_during_on_start_propagates(self) -> None:
        """If _on_start raises, the exception must propagate to the caller."""
        svc = _StubService(fail_on_start=True)
        with pytest.raises(RuntimeError, match="injected start failure"):
            await svc.start()
        # Service should NOT be marked as running
        assert svc.running is False
        assert svc.start_count == 0

    @pytest.mark.asyncio
    async def test_exception_during_on_start_in_context_manager(self) -> None:
        """async with should propagate _on_start failure and not call _on_stop."""
        svc = _StubService(fail_on_start=True)
        with pytest.raises(RuntimeError, match="injected start failure"):
            async with svc:
                pass  # pragma: no cover — should not reach here
        assert svc.stop_count == 0

    @pytest.mark.asyncio
    async def test_nested_async_with(self) -> None:
        """Two nested 'async with' on the same instance call start/stop twice."""
        svc = _StubService()
        async with svc:
            assert svc.start_count == 1
            async with svc:
                assert svc.start_count == 2
            # Inner __aexit__ calls stop
            assert svc.stop_count == 1
        # Outer __aexit__ calls stop again
        assert svc.stop_count == 2

    @pytest.mark.asyncio
    async def test_restart_after_stop(self) -> None:
        """stop() then start() again should work (restart cycle)."""
        svc = _StubService()
        await svc.start()
        assert svc.running is True
        await svc.stop()
        assert svc.running is False
        await svc.start()
        assert svc.running is True
        assert svc.start_count == 2
        assert svc.stop_count == 1

    @pytest.mark.asyncio
    async def test_context_manager_calls_stop_on_exception(self) -> None:
        """__aexit__ must call stop even if the body raises."""
        svc = _StubService()
        with pytest.raises(ValueError, match="body error"):
            async with svc:
                raise ValueError("body error")
        assert svc.stop_count == 1

    @pytest.mark.asyncio
    async def test_exception_during_on_stop_propagates(self) -> None:
        """If _on_stop raises, the exception must propagate from stop()."""
        svc = _StubService(fail_on_stop=True)
        await svc.start()
        with pytest.raises(RuntimeError, match="injected stop failure"):
            await svc.stop()
