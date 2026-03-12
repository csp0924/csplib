# =============== Executor Tests ===============
#
# 測試 StrategyExecutor 執行器

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from csp_lib.controller.core import (
    Command,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)
from csp_lib.controller.executor import StrategyExecutor

# =============== Mock Strategy ===============


class MockStrategy(Strategy):
    """測試用 Mock 策略"""

    def __init__(
        self, return_command: Command | None = None, mode: ExecutionMode = ExecutionMode.PERIODIC, interval: int = 1
    ):
        self._return_command = return_command if return_command is not None else Command()
        self._mode = mode
        self._interval = interval
        self.execute_count = 0
        self.activated = False
        self.deactivated = False
        self.last_context: StrategyContext | None = None

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=self._interval)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        self.last_context = context
        return self._return_command

    async def on_activate(self):
        self.activated = True

    async def on_deactivate(self):
        self.deactivated = True


# =============== StrategyExecutor Tests ===============


class TestStrategyExecutor:
    """StrategyExecutor 執行器測試"""

    def test_initial_state(self):
        """初始狀態測試"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        assert executor.current_strategy is None
        assert executor.last_command == Command()
        assert executor.is_running is False

    @pytest.mark.asyncio
    async def test_set_strategy_calls_lifecycle_hooks(self):
        """set_strategy 應呼叫生命週期 hooks"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        strategy1 = MockStrategy()
        await executor.set_strategy(strategy1)
        assert strategy1.activated is True

        strategy2 = MockStrategy()
        await executor.set_strategy(strategy2)
        assert strategy1.deactivated is True
        assert strategy2.activated is True

    @pytest.mark.asyncio
    async def test_set_strategy_to_none(self):
        """set_strategy(None) 應停用當前策略"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        strategy = MockStrategy()
        await executor.set_strategy(strategy)
        await executor.set_strategy(None)

        assert strategy.deactivated is True
        assert executor.current_strategy is None

    @pytest.mark.asyncio
    async def test_execute_once(self):
        """execute_once 應執行一次策略"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        strategy = MockStrategy(return_command=Command(p_target=100.0))
        await executor.set_strategy(strategy)

        cmd = await executor.execute_once()

        assert cmd.p_target == 100.0
        assert strategy.execute_count == 1
        assert executor.last_command == cmd

    @pytest.mark.asyncio
    async def test_execute_once_without_strategy(self):
        """無策略時 execute_once 返回空 Command"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        cmd = await executor.execute_once()

        assert cmd == Command()

    @pytest.mark.asyncio
    async def test_context_contains_last_command(self):
        """context 應包含 last_command"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        strategy = MockStrategy(return_command=Command(p_target=100.0))
        await executor.set_strategy(strategy)

        # 第一次執行
        await executor.execute_once()

        # 第二次執行
        await executor.execute_once()

        # 檢查第二次執行時的 context.last_command
        assert strategy.last_context is not None
        assert strategy.last_context.last_command.p_target == 100.0

    @pytest.mark.asyncio
    async def test_context_contains_current_time(self):
        """context 應包含 current_time"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        strategy = MockStrategy()
        await executor.set_strategy(strategy)

        before = datetime.now(timezone.utc)
        await executor.execute_once()
        after = datetime.now(timezone.utc)

        assert strategy.last_context is not None
        assert before <= strategy.last_context.current_time <= after

    @pytest.mark.asyncio
    async def test_on_command_callback(self):
        """on_command 回呼應被呼叫"""
        callback = AsyncMock()
        executor = StrategyExecutor(context_provider=lambda: StrategyContext(), on_command=callback)

        strategy = MockStrategy(return_command=Command(p_target=200.0))
        await executor.set_strategy(strategy)

        await executor.execute_once()

        callback.assert_called_once()
        called_cmd = callback.call_args[0][0]
        assert called_cmd.p_target == 200.0

    @pytest.mark.asyncio
    async def test_strategy_exception_returns_last_command(self):
        """策略執行異常時應返回 last_command"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        # 先設定一個正常策略執行一次
        normal_strategy = MockStrategy(return_command=Command(p_target=100.0))
        await executor.set_strategy(normal_strategy)
        await executor.execute_once()

        # 換成會拋出異常的策略
        class FailingStrategy(MockStrategy):
            def execute(self, context):
                raise RuntimeError("Test error")

        failing_strategy = FailingStrategy()
        await executor.set_strategy(failing_strategy)

        cmd = await executor.execute_once()

        # 應返回上一次的 command
        assert cmd.p_target == 100.0

    @pytest.mark.asyncio
    async def test_run_and_stop(self):
        """run() 和 stop() 基本測試"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        # PERIODIC 模式，stop() 應能中斷等待
        strategy = MockStrategy(
            return_command=Command(p_target=50.0),
            mode=ExecutionMode.PERIODIC,
            interval=10,  # 長週期，測試 stop() 能中斷
        )
        await executor.set_strategy(strategy)

        # 在另一個 task 中執行 run
        async def run_executor():
            await executor.run()

        _task = asyncio.create_task(run_executor())  # noqa: F841

        # 等待一小段時間讓它開始
        await asyncio.sleep(0.1)
        assert executor.is_running is True

        # 停止
        executor.stop()
        await asyncio.sleep(0.2)

        assert executor.is_running is False

    @pytest.mark.asyncio
    async def test_trigger_for_triggered_mode(self):
        """TRIGGERED 模式應等待 trigger()"""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        strategy = MockStrategy(return_command=Command(p_target=100.0), mode=ExecutionMode.TRIGGERED)
        await executor.set_strategy(strategy)

        # 啟動 executor
        task = asyncio.create_task(executor.run())
        await asyncio.sleep(0.1)

        # 尚未觸發，不應執行
        assert strategy.execute_count == 0

        # 觸發
        executor.trigger()
        await asyncio.sleep(0.1)

        assert strategy.execute_count == 1

        executor.stop()
        await task

    @pytest.mark.asyncio
    async def test_switch_triggered_to_periodic_resumes_execution(self):
        """Regression #17: switching from TRIGGERED to PERIODIC should resume execution without manual trigger.

        The bug was: after set_strategy() from TRIGGERED -> PERIODIC, the run loop stayed blocked
        on _trigger_event.wait() and never executed the new PERIODIC strategy.
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        triggered_strategy = MockStrategy(mode=ExecutionMode.TRIGGERED)
        await executor.set_strategy(triggered_strategy)

        task = asyncio.create_task(executor.run())
        await asyncio.sleep(0.1)

        # Executor is running but blocked waiting for trigger - no executions yet
        assert executor.is_running is True
        assert triggered_strategy.execute_count == 0

        # Switch to PERIODIC (1s interval) - this should wake the run loop
        periodic_strategy = MockStrategy(
            return_command=Command(p_target=42.0),
            mode=ExecutionMode.PERIODIC,
            interval=1,
        )
        await executor.set_strategy(periodic_strategy)

        # Wait for the periodic strategy to execute at least once
        # The first execution happens after the interval (1s), so wait a bit more
        await asyncio.sleep(1.5)

        assert periodic_strategy.execute_count >= 1, (
            "PERIODIC strategy should have executed after switching from TRIGGERED, "
            f"but execute_count={periodic_strategy.execute_count}"
        )
        assert executor.last_command.p_target == 42.0

        executor.stop()
        await task

    @pytest.mark.asyncio
    async def test_switch_periodic_to_triggered_blocks_execution(self):
        """Switching from PERIODIC to TRIGGERED should block execution until trigger() is called."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        # Start with PERIODIC strategy (short interval so it executes quickly)
        periodic_strategy = MockStrategy(
            return_command=Command(p_target=10.0),
            mode=ExecutionMode.PERIODIC,
            interval=1,
        )
        await executor.set_strategy(periodic_strategy)

        task = asyncio.create_task(executor.run())
        await asyncio.sleep(1.5)

        # PERIODIC strategy should have executed at least once
        assert periodic_strategy.execute_count >= 1

        # Switch to TRIGGERED mode
        triggered_strategy = MockStrategy(
            return_command=Command(p_target=99.0),
            mode=ExecutionMode.TRIGGERED,
        )
        await executor.set_strategy(triggered_strategy)

        # Wait and verify it does NOT execute without a trigger
        await asyncio.sleep(0.5)
        assert triggered_strategy.execute_count == 0, (
            "TRIGGERED strategy should not execute without trigger(), "
            f"but execute_count={triggered_strategy.execute_count}"
        )

        # Now trigger it - it should execute
        executor.trigger()
        await asyncio.sleep(0.1)
        assert triggered_strategy.execute_count == 1

        executor.stop()
        await task

    @pytest.mark.asyncio
    async def test_switch_triggered_to_periodic_skips_stale_execution(self):
        """After switching strategy, the executor should NOT execute the old strategy.

        The run loop should skip execution on the iteration where strategy_changed_event fires,
        then re-read the new strategy's config on the next iteration.
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        triggered_strategy = MockStrategy(mode=ExecutionMode.TRIGGERED)
        await executor.set_strategy(triggered_strategy)

        task = asyncio.create_task(executor.run())
        await asyncio.sleep(0.1)

        # Switch to PERIODIC
        periodic_strategy = MockStrategy(mode=ExecutionMode.PERIODIC, interval=1)
        await executor.set_strategy(periodic_strategy)

        # Wait for periodic to run
        await asyncio.sleep(1.5)

        # The old triggered strategy should never have been executed
        assert triggered_strategy.execute_count == 0
        # The new periodic strategy should have executed
        assert periodic_strategy.execute_count >= 1

        executor.stop()
        await task

    @pytest.mark.asyncio
    async def test_context_immutability(self):
        """context 應使用 dataclasses.replace 保持不可變"""
        base_context = StrategyContext(soc=50.0)
        executor = StrategyExecutor(context_provider=lambda: base_context)

        strategy = MockStrategy()
        await executor.set_strategy(strategy)

        await executor.execute_once()

        # 檢查原始 context 不應被修改
        assert base_context.last_command == Command()  # 原始值
        assert base_context.current_time is None  # 原始值

        # 策略收到的 context 應有新值
        assert strategy.last_context is not None
        assert strategy.last_context.last_command == Command()  # 執行時的 last
        assert strategy.last_context.current_time is not None
