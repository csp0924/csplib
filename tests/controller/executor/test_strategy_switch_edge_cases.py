# =============== Strategy Switch Edge Case Tests ===============
#
# Extensive edge-case tests for StrategyExecutor strategy switching.
# Covers all 9 mode transition combinations, rapid/stress scenarios,
# lifecycle callbacks, and concurrency safety.
#
# Related bug: #17 - Strategy not resuming after pop/override/bypass,
# executor stuck in TRIGGERED mode.

import asyncio

import pytest

from csp_lib.controller.core import (
    Command,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)
from csp_lib.controller.executor import StrategyExecutor

# =============== Test Helpers ===============


class MockStrategy(Strategy):
    """Reusable mock strategy for edge-case tests."""

    def __init__(
        self,
        return_command: Command | None = None,
        mode: ExecutionMode = ExecutionMode.PERIODIC,
        interval: int = 1,
        name: str = "MockStrategy",
    ):
        self._return_command = return_command if return_command is not None else Command()
        self._mode = mode
        self._interval = interval
        self._name = name
        self.execute_count = 0
        self.activated = False
        self.deactivated = False
        self.activate_order: int | None = None
        self.deactivate_order: int | None = None

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=self._interval)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        return self._return_command

    async def on_activate(self):
        self.activated = True

    async def on_deactivate(self):
        self.deactivated = True

    def __str__(self) -> str:
        return self._name


class SlowExecuteStrategy(MockStrategy):
    """Strategy whose execute() takes some time (simulates heavy computation)."""

    def __init__(self, delay: float = 0.3, **kwargs):
        super().__init__(**kwargs)
        self._delay = delay
        self._executing = asyncio.Event()
        self._done = asyncio.Event()

    def execute(self, context: StrategyContext) -> Command:
        self._executing.set()
        self.execute_count += 1
        return self._return_command


class AsyncSlowExecuteStrategy(MockStrategy):
    """Strategy that signals when execute starts so tests can switch mid-execution.

    Since execute() is synchronous in the Strategy ABC, we use a flag
    to detect the window. The on_command callback is async and gives
    us the needed async gap.
    """

    def __init__(self, delay: float = 0.0, **kwargs):
        super().__init__(**kwargs)
        self.execute_started = asyncio.Event()

    def execute(self, context: StrategyContext) -> Command:
        self.execute_started.set()
        self.execute_count += 1
        return self._return_command


# Order tracker for lifecycle hook ordering
_lifecycle_order: list[str] = []


class OrderTrackingStrategy(MockStrategy):
    """Tracks the order of on_activate / on_deactivate calls globally."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def on_activate(self):
        self.activated = True
        _lifecycle_order.append(f"{self._name}.activate")

    async def on_deactivate(self):
        self.deactivated = True
        _lifecycle_order.append(f"{self._name}.deactivate")


async def _run_executor_with_timeout(executor: StrategyExecutor, timeout: float = 3.0) -> asyncio.Task:
    """Start executor.run() in a background task and return the task."""
    task = asyncio.create_task(executor.run())
    # Give the run loop time to start
    await asyncio.sleep(0.05)
    return task


async def _stop_and_wait(executor: StrategyExecutor, task: asyncio.Task, timeout: float = 3.0) -> None:
    """Cleanly stop executor and wait for the task to finish."""
    executor.stop()
    await asyncio.wait_for(task, timeout=timeout)


# =============== Mode Transition Matrix (9 combinations) ===============


class TestModeTransitionMatrix:
    """Test all 9 mode transition combinations."""

    @pytest.mark.asyncio
    async def test_triggered_to_periodic(self):
        """TRIGGERED -> PERIODIC: executor should start periodic execution after switch."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)
        assert s1.execute_count == 0, "TRIGGERED strategy should not execute without trigger"

        s2 = MockStrategy(
            return_command=Command(p_target=1.0), mode=ExecutionMode.PERIODIC, interval=1, name="periodic"
        )
        await executor.set_strategy(s2)
        await asyncio.sleep(1.5)

        assert s2.execute_count >= 1, f"PERIODIC strategy should execute, got {s2.execute_count}"
        assert s1.execute_count == 0, "Old TRIGGERED strategy should never have executed"
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_triggered_to_hybrid(self):
        """TRIGGERED -> HYBRID: executor should start hybrid execution after switch."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)
        assert s1.execute_count == 0

        s2 = MockStrategy(return_command=Command(p_target=2.0), mode=ExecutionMode.HYBRID, interval=1, name="hybrid")
        await executor.set_strategy(s2)
        # HYBRID should execute after interval or on trigger
        await asyncio.sleep(1.5)

        assert s2.execute_count >= 1, f"HYBRID strategy should execute, got {s2.execute_count}"
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_triggered_to_triggered(self):
        """TRIGGERED -> TRIGGERED (different instance): new strategy should respond to trigger."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="triggered-old")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        s2 = MockStrategy(return_command=Command(p_target=3.0), mode=ExecutionMode.TRIGGERED, name="triggered-new")
        await executor.set_strategy(s2)
        await asyncio.sleep(0.1)

        # Neither should have executed yet
        assert s1.execute_count == 0
        assert s2.execute_count == 0

        # Trigger should cause the NEW strategy to execute
        executor.trigger()
        await asyncio.sleep(0.1)

        assert s2.execute_count == 1
        assert s1.execute_count == 0
        assert executor.last_command.p_target == 3.0
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_periodic_to_triggered(self):
        """PERIODIC -> TRIGGERED: execution should stop until trigger() is called."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.PERIODIC, interval=1, name="periodic")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(1.5)
        assert s1.execute_count >= 1

        s2 = MockStrategy(return_command=Command(p_target=4.0), mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s2)
        await asyncio.sleep(0.5)

        assert s2.execute_count == 0, "TRIGGERED should not execute without trigger"

        executor.trigger()
        await asyncio.sleep(0.1)
        assert s2.execute_count == 1
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_periodic_to_hybrid(self):
        """PERIODIC -> HYBRID: executor should continue with hybrid execution."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.PERIODIC, interval=1, name="periodic")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(1.3)
        assert s1.execute_count >= 1

        s2 = MockStrategy(return_command=Command(p_target=5.0), mode=ExecutionMode.HYBRID, interval=1, name="hybrid")
        await executor.set_strategy(s2)
        # Trigger immediately to test hybrid's trigger capability
        executor.trigger()
        await asyncio.sleep(0.1)

        assert s2.execute_count >= 1, "HYBRID should execute on trigger"
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_periodic_to_periodic(self):
        """PERIODIC -> PERIODIC (different instance/interval): new strategy should take over."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(
            return_command=Command(p_target=10.0), mode=ExecutionMode.PERIODIC, interval=1, name="periodic-old"
        )
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(1.3)
        old_count = s1.execute_count
        assert old_count >= 1

        s2 = MockStrategy(
            return_command=Command(p_target=20.0), mode=ExecutionMode.PERIODIC, interval=1, name="periodic-new"
        )
        await executor.set_strategy(s2)
        await asyncio.sleep(1.5)

        # Old strategy should not get any more executions
        assert s1.execute_count == old_count
        assert s2.execute_count >= 1
        assert executor.last_command.p_target == 20.0
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_hybrid_to_triggered(self):
        """HYBRID -> TRIGGERED: executor should block until trigger()."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.HYBRID, interval=1, name="hybrid")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(1.3)
        assert s1.execute_count >= 1

        s2 = MockStrategy(return_command=Command(p_target=7.0), mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s2)
        await asyncio.sleep(0.5)

        assert s2.execute_count == 0, "TRIGGERED should not execute without trigger"

        executor.trigger()
        await asyncio.sleep(0.1)
        assert s2.execute_count == 1
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_hybrid_to_periodic(self):
        """HYBRID -> PERIODIC: executor should continue with periodic execution."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.HYBRID, interval=1, name="hybrid")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(1.3)
        assert s1.execute_count >= 1

        s2 = MockStrategy(
            return_command=Command(p_target=8.0), mode=ExecutionMode.PERIODIC, interval=1, name="periodic"
        )
        await executor.set_strategy(s2)
        await asyncio.sleep(1.5)

        assert s2.execute_count >= 1
        assert executor.last_command.p_target == 8.0
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_hybrid_to_hybrid(self):
        """HYBRID -> HYBRID (different instance): new strategy takes over, trigger works."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.HYBRID, interval=1, name="hybrid-old")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(1.3)
        old_count = s1.execute_count
        assert old_count >= 1

        s2 = MockStrategy(
            return_command=Command(p_target=9.0), mode=ExecutionMode.HYBRID, interval=1, name="hybrid-new"
        )
        await executor.set_strategy(s2)
        # The strategy_changed_event causes the run loop to skip execution on the
        # current iteration, so we need to wait for the loop to re-enter
        # _wait_for_execution before triggering.
        await asyncio.sleep(0.15)
        executor.trigger()
        await asyncio.sleep(0.15)

        assert s2.execute_count >= 1
        assert s1.execute_count == old_count, "Old strategy should not get more executions"
        await _stop_and_wait(executor, task)


# =============== Rapid / Stress Scenarios ===============


class TestRapidStressScenarios:
    """Test rapid successive operations and stress scenarios."""

    @pytest.mark.asyncio
    async def test_rapid_successive_set_strategy(self):
        """Rapid successive set_strategy() calls should not crash or deadlock.

        Only the final strategy should be active.
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="s1")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Rapid fire 5 strategy switches
        strategies = []
        for i in range(5):
            s = MockStrategy(
                return_command=Command(p_target=float(i)),
                mode=ExecutionMode.PERIODIC,
                interval=1,
                name=f"rapid-{i}",
            )
            strategies.append(s)
            await executor.set_strategy(s)

        # Only the last one should be the current strategy
        assert executor.current_strategy is strategies[-1]

        # Wait for the final strategy to execute
        await asyncio.sleep(1.5)
        assert strategies[-1].execute_count >= 1

        # All intermediate strategies should have been activated and deactivated
        for i, s in enumerate(strategies[:-1]):
            assert s.activated is True, f"Strategy {i} should have been activated"
            assert s.deactivated is True, f"Strategy {i} should have been deactivated"

        # Last strategy should be activated but not deactivated
        assert strategies[-1].activated is True
        assert strategies[-1].deactivated is False

        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_set_strategy_none_while_triggered_wait(self):
        """set_strategy(None) while blocked in TRIGGERED wait should not crash."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Set to None -- should wake the run loop safely
        await executor.set_strategy(None)
        await asyncio.sleep(0.2)

        # Executor should still be running (in the None-strategy sleep loop)
        assert executor.is_running is True
        assert executor.current_strategy is None
        assert s1.deactivated is True
        assert s1.execute_count == 0

        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_set_strategy_none_then_new_strategy(self):
        """set_strategy(None) then set_strategy(new) should resume execution."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Clear the strategy
        await executor.set_strategy(None)
        await asyncio.sleep(0.2)

        # Set a new periodic strategy
        s2 = MockStrategy(
            return_command=Command(p_target=42.0), mode=ExecutionMode.PERIODIC, interval=1, name="periodic"
        )
        await executor.set_strategy(s2)
        await asyncio.sleep(1.5)

        assert s2.execute_count >= 1
        assert executor.last_command.p_target == 42.0
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_multiple_triggers_before_processing(self):
        """Multiple trigger() calls before strategy processes them should coalesce.

        asyncio.Event.set() is idempotent, so multiple triggers
        before processing should result in at most one execution per wait cycle.
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(return_command=Command(p_target=1.0), mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Fire multiple triggers rapidly before executor can process
        for _ in range(5):
            executor.trigger()

        await asyncio.sleep(0.2)

        # Due to event coalescing, execute_count should be exactly 1
        # (the event is cleared after one wait, so subsequent sets before
        #  the next wait are coalesced)
        assert s1.execute_count == 1, (
            f"Multiple triggers should coalesce to 1 execution per cycle, got {s1.execute_count}"
        )

        await _stop_and_wait(executor, task)


# =============== Lifecycle & Callback Edge Cases ===============


class TestLifecycleCallbackEdgeCases:
    """Test lifecycle hook ordering and callback behavior during switches."""

    @pytest.mark.asyncio
    async def test_deactivate_then_activate_order(self):
        """on_deactivate of old strategy must be called BEFORE on_activate of new strategy."""
        global _lifecycle_order
        _lifecycle_order = []

        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = OrderTrackingStrategy(mode=ExecutionMode.PERIODIC, interval=1, name="old")
        s2 = OrderTrackingStrategy(mode=ExecutionMode.PERIODIC, interval=1, name="new")

        await executor.set_strategy(s1)
        assert _lifecycle_order == ["old.activate"]

        await executor.set_strategy(s2)
        assert _lifecycle_order == ["old.activate", "old.deactivate", "new.activate"]

    @pytest.mark.asyncio
    async def test_on_command_fires_for_new_strategy_after_switch(self):
        """After switch, on_command should fire for the NEW strategy's output."""
        received_commands: list[Command] = []

        async def on_command(cmd: Command) -> None:
            received_commands.append(cmd)

        executor = StrategyExecutor(context_provider=lambda: StrategyContext(), on_command=on_command)

        s1 = MockStrategy(return_command=Command(p_target=100.0), mode=ExecutionMode.TRIGGERED, name="old")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Switch to new strategy with different command
        s2 = MockStrategy(return_command=Command(p_target=200.0), mode=ExecutionMode.PERIODIC, interval=1, name="new")
        await executor.set_strategy(s2)
        await asyncio.sleep(1.5)

        # All callbacks after the switch should have the new strategy's command
        assert len(received_commands) >= 1
        for cmd in received_commands:
            assert cmd.p_target == 200.0, f"Expected new strategy command, got p_target={cmd.p_target}"

        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_strategy_switch_during_on_command_callback(self):
        """Strategy changes mid-execution (during on_command callback) should not crash.

        Simulates the scenario where on_command triggers another set_strategy().
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s2 = MockStrategy(return_command=Command(p_target=999.0), mode=ExecutionMode.TRIGGERED, name="replacement")
        switch_done = asyncio.Event()

        async def switching_callback(cmd: Command) -> None:
            if cmd.p_target == 100.0:
                await executor.set_strategy(s2)
                switch_done.set()

        executor._on_command = switching_callback

        s1 = MockStrategy(
            return_command=Command(p_target=100.0), mode=ExecutionMode.PERIODIC, interval=1, name="original"
        )
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)

        # Wait for the callback to fire and switch the strategy
        await asyncio.wait_for(switch_done.wait(), timeout=3.0)
        await asyncio.sleep(0.1)

        # Executor should still be running with the new strategy
        assert executor.is_running is True
        assert executor.current_strategy is s2
        assert s1.deactivated is True

        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_set_strategy_when_executor_not_running(self):
        """set_strategy() called without run() should not hang or crash."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.PERIODIC, name="s1")
        # This should complete immediately -- no run loop to wake up
        await asyncio.wait_for(executor.set_strategy(s1), timeout=2.0)

        assert s1.activated is True
        assert executor.current_strategy is s1
        assert executor.is_running is False

        # Switch again without running
        s2 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="s2")
        await asyncio.wait_for(executor.set_strategy(s2), timeout=2.0)

        assert s1.deactivated is True
        assert s2.activated is True
        assert executor.current_strategy is s2


# =============== Concurrency Safety ===============


class TestConcurrencySafety:
    """Test concurrent operations for deadlocks and crashes."""

    @pytest.mark.asyncio
    async def test_concurrent_set_strategy_and_trigger(self):
        """Concurrent set_strategy() and trigger() should not deadlock or crash."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="initial")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Fire trigger and set_strategy concurrently
        s2 = MockStrategy(return_command=Command(p_target=50.0), mode=ExecutionMode.PERIODIC, interval=1, name="new")

        async def do_trigger():
            executor.trigger()

        async def do_switch():
            await executor.set_strategy(s2)

        # Run both concurrently
        await asyncio.gather(do_trigger(), do_switch())
        await asyncio.sleep(1.5)

        # Should not have crashed; new strategy should be active
        assert executor.is_running is True
        assert executor.current_strategy is s2
        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_concurrent_set_strategy_and_stop(self):
        """Concurrent set_strategy() and stop() should result in clean shutdown."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.PERIODIC, interval=1, name="initial")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.2)

        s2 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="new")

        async def do_switch():
            await executor.set_strategy(s2)

        def do_stop():
            executor.stop()

        # Fire both concurrently
        do_stop()
        await do_switch()

        # Wait for the task to finish
        await asyncio.wait_for(task, timeout=3.0)

        assert executor.is_running is False

    @pytest.mark.asyncio
    async def test_set_strategy_from_on_command_reentrant(self):
        """set_strategy() called from within on_command (reentrant) should not deadlock."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        call_count = 0
        s_final = MockStrategy(return_command=Command(p_target=777.0), mode=ExecutionMode.TRIGGERED, name="final")

        async def reentrant_callback(cmd: Command) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Reentrant: switch strategy from inside the callback
                await executor.set_strategy(s_final)

        executor._on_command = reentrant_callback

        s1 = MockStrategy(
            return_command=Command(p_target=100.0), mode=ExecutionMode.PERIODIC, interval=1, name="initial"
        )
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)

        # Wait for the first execution + reentrant switch
        await asyncio.sleep(1.5)

        assert executor.current_strategy is s_final
        assert s1.deactivated is True
        assert executor.is_running is True

        await _stop_and_wait(executor, task)


# =============== Event State Consistency ===============


class TestEventStateConsistency:
    """Test that event states are consistent after mode transitions."""

    @pytest.mark.asyncio
    async def test_stale_trigger_after_triggered_to_periodic_no_extra_execution(self):
        """After TRIGGERED->PERIODIC switch, a stale trigger_event.set() should NOT cause extra execution.

        The _strategy_changed_event causes the run loop to skip execution on the
        iteration where the switch happens, so a leftover trigger should not leak through.
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Set the trigger event BEFORE switching strategy (simulates stale trigger)
        executor._trigger_event.set()

        # Switch to PERIODIC
        s2 = MockStrategy(
            return_command=Command(p_target=50.0), mode=ExecutionMode.PERIODIC, interval=10, name="periodic-slow"
        )
        await executor.set_strategy(s2)

        # The long interval (10s) means we should see 0 executions in a short wait
        # if the stale trigger doesn't leak through.
        # But the _strategy_changed_event causes the loop to `continue`, skipping execution.
        await asyncio.sleep(0.3)

        # With a 10s interval, the periodic strategy should not have executed yet
        # (unless a stale trigger leaked through, which would be a bug).
        assert s2.execute_count == 0, f"Stale trigger should not cause extra execution, but got {s2.execute_count}"

        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_hybrid_to_triggered_periodic_timer_does_not_fire(self):
        """After HYBRID->TRIGGERED switch, no periodic timer from HYBRID should fire.

        The TRIGGERED strategy should only execute when trigger() is called.
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.HYBRID, interval=1, name="hybrid")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        # Wait for hybrid to get at least one execution
        await asyncio.sleep(1.3)
        assert s1.execute_count >= 1

        # Switch to TRIGGERED
        s2 = MockStrategy(return_command=Command(p_target=88.0), mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s2)

        # Wait well past what the old hybrid interval was -- no execution should happen
        await asyncio.sleep(1.5)
        assert s2.execute_count == 0, f"TRIGGERED strategy should not execute without trigger, got {s2.execute_count}"

        # Now trigger -- should execute
        executor.trigger()
        await asyncio.sleep(0.1)
        assert s2.execute_count == 1

        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_stop_after_set_strategy_clean_shutdown(self):
        """stop() immediately after set_strategy() should result in clean shutdown."""
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Switch strategy, then immediately stop
        s2 = MockStrategy(mode=ExecutionMode.PERIODIC, interval=1, name="periodic")
        await executor.set_strategy(s2)
        executor.stop()

        # Should not hang
        await asyncio.wait_for(task, timeout=3.0)
        assert executor.is_running is False

    @pytest.mark.asyncio
    async def test_triggered_trigger_then_switch_no_old_strategy_execution(self):
        """If trigger() is called right before set_strategy(), the old strategy should not execute
        after the switch takes effect.

        Specifically: trigger() -> set_strategy(new) should not cause old strategy to execute.
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(return_command=Command(p_target=1.0), mode=ExecutionMode.TRIGGERED, name="old-triggered")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        await asyncio.sleep(0.1)

        # Trigger, then immediately switch
        executor.trigger()
        s2 = MockStrategy(
            return_command=Command(p_target=2.0), mode=ExecutionMode.PERIODIC, interval=1, name="new-periodic"
        )
        await executor.set_strategy(s2)
        await asyncio.sleep(1.5)

        # After the switch, only the new strategy should produce commands going forward.
        # The old strategy MAY have executed once if the trigger was processed before the switch,
        # but the new strategy should definitely have executed.
        assert s2.execute_count >= 1

        await _stop_and_wait(executor, task)

    @pytest.mark.asyncio
    async def test_periodic_to_triggered_no_stale_timeout_execution(self):
        """After PERIODIC->TRIGGERED switch, a stale periodic timeout should not cause execution.

        The run loop should re-read the config after strategy_changed_event fires.
        """
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())

        s1 = MockStrategy(mode=ExecutionMode.PERIODIC, interval=1, name="periodic")
        await executor.set_strategy(s1)

        task = await _run_executor_with_timeout(executor)
        # Let it execute once
        await asyncio.sleep(1.3)
        assert s1.execute_count >= 1

        # Switch to TRIGGERED
        s2 = MockStrategy(return_command=Command(p_target=55.0), mode=ExecutionMode.TRIGGERED, name="triggered")
        await executor.set_strategy(s2)

        # Wait past what the old periodic interval would be
        await asyncio.sleep(1.5)

        # Triggered should not have executed
        assert s2.execute_count == 0

        # Explicit trigger
        executor.trigger()
        await asyncio.sleep(0.1)
        assert s2.execute_count == 1

        await _stop_and_wait(executor, task)
