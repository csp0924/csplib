"""Tests for csp_lib.controller.executor.compute_offloader."""

import threading
import time

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.executor.compute_offloader import ComputeOffloader
from csp_lib.controller.executor.strategy_executor import StrategyExecutor


class TestComputeOffloader:
    @pytest.mark.asyncio
    async def test_run_offloads_to_thread(self):
        """run() should execute in a different thread."""
        offloader = ComputeOffloader(max_workers=1)
        main_thread = threading.current_thread().ident

        def get_thread_id():
            return threading.current_thread().ident

        try:
            worker_thread = await offloader.run(get_thread_id)
            assert worker_thread != main_thread
        finally:
            offloader.shutdown()

    @pytest.mark.asyncio
    async def test_run_returns_result(self):
        offloader = ComputeOffloader(max_workers=1)
        try:
            result = await offloader.run(lambda x, y: x + y, 3, 4)
            assert result == 7
        finally:
            offloader.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_is_idempotent(self):
        offloader = ComputeOffloader(max_workers=1)
        offloader.shutdown()
        offloader.shutdown()  # Should not raise


class TestStrategyExecutorWithOffloader:
    @pytest.mark.asyncio
    async def test_execute_with_offloader(self):
        """StrategyExecutor should use offloader when provided."""
        offloader = ComputeOffloader(max_workers=1)
        executed_threads: list[int] = []

        class ThreadTrackingStrategy(Strategy):
            @property
            def execution_config(self) -> ExecutionConfig:
                return ExecutionConfig(mode=ExecutionMode.TRIGGERED, interval_seconds=1)

            def execute(self, context: StrategyContext) -> Command:
                executed_threads.append(threading.current_thread().ident)
                return Command(p_target=42.0)

            async def on_activate(self) -> None:
                pass

            async def on_deactivate(self) -> None:
                pass

        strategy = ThreadTrackingStrategy()
        ctx = StrategyContext()
        executor = StrategyExecutor(
            context_provider=lambda: ctx,
            offloader=offloader,
        )
        await executor.set_strategy(strategy)

        try:
            cmd = await executor.execute_once()
            assert cmd.p_target == 42.0
            assert len(executed_threads) == 1
            assert executed_threads[0] != threading.current_thread().ident
        finally:
            executor.stop()

    @pytest.mark.asyncio
    async def test_execute_without_offloader(self):
        """Without offloader, strategy runs in main thread."""
        executed_threads: list[int] = []

        class ThreadTrackingStrategy(Strategy):
            @property
            def execution_config(self) -> ExecutionConfig:
                return ExecutionConfig(mode=ExecutionMode.TRIGGERED, interval_seconds=1)

            def execute(self, context: StrategyContext) -> Command:
                executed_threads.append(threading.current_thread().ident)
                return Command(p_target=99.0)

            async def on_activate(self) -> None:
                pass

            async def on_deactivate(self) -> None:
                pass

        strategy = ThreadTrackingStrategy()
        ctx = StrategyContext()
        executor = StrategyExecutor(context_provider=lambda: ctx)
        await executor.set_strategy(strategy)

        cmd = await executor.execute_once()
        assert cmd.p_target == 99.0
        assert len(executed_threads) == 1
        assert executed_threads[0] == threading.current_thread().ident
