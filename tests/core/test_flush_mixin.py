"""BackgroundFlushMixin 單元測試"""

from __future__ import annotations

import asyncio

import pytest

from csp_lib.core.flush_mixin import BackgroundFlushMixin


class _TestFlusher(BackgroundFlushMixin):
    """測試用具體子類別"""

    def __init__(self, interval: float = 0.05) -> None:
        self._flush_interval = interval
        self._flush_task: asyncio.Task[None] | None = None
        self._flush_stop_event = asyncio.Event()
        self.flush_count = 0
        self.errors: list[Exception] = []

    async def _flush_once(self) -> None:
        self.flush_count += 1

    async def _on_flush_error(self, exc: Exception) -> None:
        self.errors.append(exc)


class _FailingFlusher(_TestFlusher):
    """每次 flush 都失敗"""

    async def _flush_once(self) -> None:
        self.flush_count += 1
        raise RuntimeError("flush failed")


# --- Tests ---


async def test_periodic_flush() -> None:
    """啟動後應定期呼叫 _flush_once"""
    flusher = _TestFlusher(interval=0.02)
    flusher._start_flush_loop()
    await asyncio.sleep(0.1)
    await flusher._stop_flush_loop()
    assert flusher.flush_count >= 2


async def test_stop_calls_final_flush() -> None:
    """停止時應呼叫 _final_flush（預設再呼叫一次 _flush_once）"""
    flusher = _TestFlusher(interval=10.0)  # 長間隔，不會自然 flush
    flusher._start_flush_loop()
    await asyncio.sleep(0.01)
    count_before = flusher.flush_count
    await flusher._stop_flush_loop()
    assert flusher.flush_count == count_before + 1  # final flush


async def test_stop_without_start() -> None:
    """未啟動就停止不應報錯"""
    flusher = _TestFlusher()
    flusher._flush_task = None
    # _final_flush 會呼叫 _flush_once，但不該 crash
    await flusher._stop_flush_loop()
    assert flusher.flush_count == 1  # final flush still runs


async def test_flush_error_calls_handler() -> None:
    """flush 失敗時應呼叫 _on_flush_error"""
    flusher = _FailingFlusher(interval=0.02)
    flusher._start_flush_loop()
    await asyncio.sleep(0.08)
    await flusher._stop_flush_loop()
    assert len(flusher.errors) >= 1
    assert all(isinstance(e, RuntimeError) for e in flusher.errors)


async def test_error_does_not_stop_loop() -> None:
    """flush 失敗後迴圈應繼續"""
    flusher = _FailingFlusher(interval=0.02)
    flusher._start_flush_loop()
    await asyncio.sleep(0.1)
    await flusher._stop_flush_loop()
    assert flusher.flush_count >= 2  # 失敗後仍繼續


async def test_not_implemented_raises() -> None:
    """未覆寫 _flush_once 應 raise NotImplementedError"""
    bare = BackgroundFlushMixin()
    with pytest.raises(NotImplementedError):
        await bare._flush_once()
