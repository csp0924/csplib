# =============== StrategyExecutor Work-First Tests (v0.8.0 WI-V080-006) ===============
#
# 驗證 v0.8.0 的 work-first + absolute time anchoring 語義：
#   - PERIODIC 模式：啟動後立即 execute（不再 wait-first）
#   - PERIODIC 模式：多週期下耗時漂移可控（絕對錨不累積誤差）
#   - HYBRID 模式：提前觸發後 anchor 重設，下次 tick 重新計算
#   - 策略切換：新策略 PERIODIC 首執立即發生、anchor 從切換點起算
#   - TRIGGERED 模式：仍維持舊行為（不會自動執行）
#
# 時序測試設計原則：
#   - 使用短 interval（0.05~0.2s）讓測試快速
#   - 使用寬鬆上限（例如 total <= 1.5 * expected）降低 Windows 上 pytest-xdist 抖動

from __future__ import annotations

import asyncio
import time

import pytest

from csp_lib.controller.core import (
    Command,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)
from csp_lib.controller.executor import StrategyExecutor

# =============== Helpers ===============


class _MockStrategy(Strategy):
    def __init__(
        self,
        return_command: Command | None = None,
        mode: ExecutionMode = ExecutionMode.PERIODIC,
        interval: float = 0.1,
    ) -> None:
        self._return_command = return_command or Command()
        self._mode = mode
        self._interval = interval
        self.execute_count = 0
        self.execute_times: list[float] = []

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=self._interval)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        self.execute_times.append(time.monotonic())
        return self._return_command


async def _start_executor(executor: StrategyExecutor) -> asyncio.Task:
    task = asyncio.create_task(executor.run())
    # 讓 run loop 有機會進入迴圈 — 但 work-first 不需要等太久
    await asyncio.sleep(0)
    return task


async def _stop(executor: StrategyExecutor, task: asyncio.Task) -> None:
    executor.stop()
    await asyncio.wait_for(task, timeout=3.0)


# =============== PERIODIC work-first ===============


class TestPeriodicWorkFirst:
    """PERIODIC 模式 v0.8.0 work-first 語義"""

    async def test_periodic_executes_immediately_on_start(self):
        """interval=1s 但啟動後極短時間內就應看到第 1 次 execute（work-first）"""
        strategy = _MockStrategy(mode=ExecutionMode.PERIODIC, interval=1.0)
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())
        await executor.set_strategy(strategy)

        task = await _start_executor(executor)
        # 遠小於 interval：work-first 保證首執
        await asyncio.sleep(0.05)
        assert strategy.execute_count >= 1, (
            f"PERIODIC work-first should execute immediately, got {strategy.execute_count}"
        )
        await _stop(executor, task)

    async def test_periodic_drift_bounded_over_many_cycles(self):
        """10 個週期（interval=0.1s）後總耗時不應超過理論的 1.5 倍（絕對錨應補償 execute 耗時）"""
        strategy = _MockStrategy(mode=ExecutionMode.PERIODIC, interval=0.1)
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())
        await executor.set_strategy(strategy)

        start = time.monotonic()
        task = await _start_executor(executor)
        # 等足 10 個週期（~1.0s）+ 充裕 buffer
        await asyncio.sleep(1.05)
        await _stop(executor, task)
        total = time.monotonic() - start

        # 至少跑了約 10 次；允許 +/- 2 浮動
        assert 8 <= strategy.execute_count <= 14, (
            f"Expected ~10 executions in ~1s @ 0.1s interval, got {strategy.execute_count}"
        )
        # 總耗時不該超過 1.5s（理論 1.05s）
        assert total < 1.5, f"Total time {total:.3f}s exceeds 1.5s — 錨漂移"


# =============== HYBRID + trigger() ===============


class TestHybridEarlyTrigger:
    """HYBRID 模式提前觸發後 anchor 重設"""

    async def test_hybrid_work_first_then_early_trigger_resets_anchor(self):
        """HYBRID 啟動後 work-first 執行 1 次，接著 trigger 提前觸發，再等 1 個完整 interval"""
        strategy = _MockStrategy(mode=ExecutionMode.HYBRID, interval=0.5)
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())
        await executor.set_strategy(strategy)

        task = await _start_executor(executor)
        # work-first 首執
        await asyncio.sleep(0.05)
        first_count = strategy.execute_count
        assert first_count >= 1

        # 在週期尚未到達前 trigger（~0.1s < 0.5s interval）
        await asyncio.sleep(0.1)
        executor.trigger()
        await asyncio.sleep(0.05)

        # trigger 後應該觸發第 2 次 execute（HYBRID 允許提前）
        assert strategy.execute_count >= first_count + 1

        # 觸發後 anchor 重設 — 再等不到一個 interval 應該不會再跑（除了剛剛那次）
        count_after_trigger = strategy.execute_count
        await asyncio.sleep(0.2)  # 遠小於 0.5s interval
        # 錨重設後下一次 tick 要等完整 0.5s — 這 0.2s 內應該不會再跑
        assert strategy.execute_count == count_after_trigger, "HYBRID trigger 後 anchor 重設，0.2s 內不應再執行"
        await _stop(executor, task)


# =============== 策略切換：新策略 PERIODIC work-first ===============


class TestStrategySwitchWorkFirst:
    """切換到新 PERIODIC 策略後 anchor 重設 + 立即 work-first 執行"""

    async def test_switch_to_new_periodic_strategy_executes_immediately(self):
        """切換到新 PERIODIC 策略後立即 execute（work-first），不等舊 anchor"""
        s1 = _MockStrategy(mode=ExecutionMode.PERIODIC, interval=10.0)  # 10s 長 interval
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())
        await executor.set_strategy(s1)

        task = await _start_executor(executor)
        await asyncio.sleep(0.05)
        assert s1.execute_count >= 1  # work-first

        # 切換到新 PERIODIC 策略
        s2 = _MockStrategy(mode=ExecutionMode.PERIODIC, interval=10.0)
        await executor.set_strategy(s2)

        # work-first 切換後立即執行
        await asyncio.sleep(0.1)
        assert s2.execute_count >= 1, f"Switch to new PERIODIC should work-first execute, got {s2.execute_count}"
        await _stop(executor, task)


# =============== TRIGGERED 模式不自動執行 ===============


class TestTriggeredNoAutoExecute:
    """TRIGGERED 模式啟動後未 trigger 不執行（確保 work-first 不污染 TRIGGERED）"""

    async def test_triggered_mode_no_execute_until_trigger(self):
        strategy = _MockStrategy(mode=ExecutionMode.TRIGGERED, interval=0.1)
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())
        await executor.set_strategy(strategy)

        task = await _start_executor(executor)
        await asyncio.sleep(0.3)
        assert strategy.execute_count == 0, (
            f"TRIGGERED without trigger should not execute, got {strategy.execute_count}"
        )

        # 手動 trigger 後才應執行
        executor.trigger()
        await asyncio.sleep(0.05)
        assert strategy.execute_count == 1
        await _stop(executor, task)


# =============== execute_once 不受 work-first 影響 ===============


class TestExecuteOnceIndependent:
    """execute_once() 直接執行，與 run() 迴圈獨立"""

    async def test_execute_once_works_without_run(self):
        strategy = _MockStrategy(mode=ExecutionMode.PERIODIC, interval=1.0)
        executor = StrategyExecutor(context_provider=lambda: StrategyContext())
        await executor.set_strategy(strategy)

        cmd = await executor.execute_once()
        assert strategy.execute_count == 1
        assert isinstance(cmd, Command)


# =============== 靜默 markers（asyncio_mode=auto 已啟用，但 B3 用 pytest-xdist 平行，避免 race）===============


@pytest.mark.asyncio
async def test_sanity_mode_auto_marker_not_required():
    """確認 asyncio_mode=auto 下不用 marker 也能跑 async 測試

    此測試存在的目的只是 sanity check 整個檔案的 asyncio 設置正常。
    """
    await asyncio.sleep(0)
