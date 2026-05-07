# =============== StrategyExecutor Health Tests ===============
#
# K-P2: StrategyExecutor 實作 HealthCheckable
#
# 驗證 StrategyExecutor.health() 的 status 判定優先序、details schema
# 以及 read-only / idempotent 行為。
#
# 設計原則：直接操作 executor 內部 state (_strategy / _is_running /
# _last_command / _task) 模擬各種狀態，不需要實際啟動 run loop。

from __future__ import annotations

import asyncio

import pytest

from csp_lib.controller.core import (
    NO_CHANGE,
    Command,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)
from csp_lib.controller.executor import StrategyExecutor
from csp_lib.core.health import HealthCheckable, HealthReport, HealthStatus

# =============== Mock Strategy ===============


class MockStrategy(Strategy):
    """測試用 Mock 策略（複製自 test_executor.py，保持獨立）。"""

    def __init__(
        self,
        return_command: Command | None = None,
        mode: ExecutionMode = ExecutionMode.PERIODIC,
        interval: float = 1.0,
    ):
        self._return_command = return_command if return_command is not None else Command()
        self._mode = mode
        self._interval = interval

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=self._interval)

    def execute(self, context: StrategyContext) -> Command:
        return self._return_command

    async def on_activate(self):
        pass

    async def on_deactivate(self):
        pass


def _make_executor() -> StrategyExecutor:
    """建立基本 executor，不啟動 run loop。"""
    return StrategyExecutor(context_provider=lambda: StrategyContext())


# =============== Status Cases ===============


class TestHealthStatus:
    """驗證 health() 在各種內部狀態下的 status 判定（依優先序）。"""

    def test_unhealthy_fresh_executor_no_strategy_not_running(self):
        """UNHEALTHY 案例 1：剛建立、無策略、未啟動。"""
        executor = _make_executor()

        report = executor.health()

        assert isinstance(report, HealthReport)
        assert report.status is HealthStatus.UNHEALTHY
        assert report.component == "StrategyExecutor"
        assert "not running" in report.message
        assert "no strategy" in report.message

    async def test_unhealthy_task_done_with_exception(self):
        """UNHEALTHY 案例 2：_task 已 done 且有 exception。

        判定優先序最高 — 即使有策略、is_running=True 也應該 UNHEALTHY。
        """
        executor = _make_executor()

        # 建構一個會拋例外的 task 並等它 done
        async def boom():
            raise RuntimeError("simulated executor crash")

        task = asyncio.ensure_future(boom())
        # 等到 task 真的 done（不能 await，會 re-raise）
        while not task.done():
            await asyncio.sleep(0)

        # 注入到 executor 並設定相對「正常」的其他狀態，
        # 驗證 task exception 優先於其他判定
        executor._task = task
        executor._is_running = True
        await executor.set_strategy(MockStrategy())

        report = executor.health()

        assert report.status is HealthStatus.UNHEALTHY
        assert "executor task died" in report.message
        assert "RuntimeError" in report.message

    async def test_degraded_running_but_no_strategy(self):
        """DEGRADED 案例 1：_is_running=True 且 _strategy is None。"""
        executor = _make_executor()
        executor._is_running = True  # 模擬 run loop 啟動但尚未 set_strategy

        report = executor.health()

        assert report.status is HealthStatus.DEGRADED
        assert "running but no strategy" in report.message
        assert report.details["is_running"] is True
        assert report.details["current_strategy"] is None

    async def test_degraded_last_command_is_fallback(self):
        """DEGRADED 案例 2：last_command.is_fallback=True。

        即使 is_running=True 且 strategy 存在，last_command 是 fallback
        就應降為 DEGRADED。
        """
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=ExecutionMode.PERIODIC, interval=1))
        executor._is_running = True
        executor._last_command = Command(p_target=0.0, q_target=0.0, is_fallback=True)

        report = executor.health()

        assert report.status is HealthStatus.DEGRADED
        assert "fallback" in report.message
        assert report.details["last_command"]["is_fallback"] is True

    async def test_healthy_running_with_strategy_no_fallback(self):
        """HEALTHY：is_running=True、strategy 存在、last_command 非 fallback。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=ExecutionMode.PERIODIC, interval=2.5))
        executor._is_running = True
        executor._last_command = Command(p_target=100.0, q_target=20.0)

        report = executor.health()

        assert report.status is HealthStatus.HEALTHY
        assert "MockStrategy" in report.message
        assert "PERIODIC" in report.message
        assert report.details["is_running"] is True
        assert report.details["current_strategy"] == "MockStrategy"

    async def test_degraded_strategy_attached_but_not_running(self):
        """DEGRADED 兜底：strategy 存在但 not running（已 set_strategy 但尚未 run）。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=ExecutionMode.HYBRID, interval=0.5))
        # _is_running 預設 False；不動

        report = executor.health()

        assert report.status is HealthStatus.DEGRADED
        assert "attached but executor not running" in report.message
        assert report.details["current_strategy"] == "MockStrategy"
        assert report.details["is_running"] is False


# =============== Details Schema ===============


class TestHealthDetailsSchema:
    """驗證 details 欄位的鍵存在性與類型正確性。"""

    REQUIRED_KEYS = {
        "is_running",
        "current_strategy",
        "execution_mode",
        "interval_seconds",
        "last_command",
        "trigger_pending",
        "stop_pending",
        "has_offloader",
    }

    LAST_COMMAND_KEYS = {"p_target", "q_target", "is_fallback"}

    def test_details_has_all_required_keys_when_empty(self):
        """fresh executor 的 details 也必須包含所有 required keys。"""
        executor = _make_executor()
        report = executor.health()

        assert set(report.details.keys()) >= self.REQUIRED_KEYS
        assert set(report.details["last_command"].keys()) == self.LAST_COMMAND_KEYS

    async def test_details_types_when_strategy_attached(self):
        """有策略時各欄位類型正確。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=ExecutionMode.PERIODIC, interval=1.5))
        executor._is_running = True
        executor._last_command = Command(p_target=10.0, q_target=5.0)

        report = executor.health()
        d = report.details

        assert isinstance(d["is_running"], bool)
        assert isinstance(d["current_strategy"], str)
        assert isinstance(d["execution_mode"], str)
        assert isinstance(d["interval_seconds"], float)
        assert isinstance(d["last_command"], dict)
        assert isinstance(d["trigger_pending"], bool)
        assert isinstance(d["stop_pending"], bool)
        assert isinstance(d["has_offloader"], bool)

        # interval_seconds 內容
        assert d["interval_seconds"] == 1.5
        assert d["execution_mode"] == "PERIODIC"
        assert d["current_strategy"] == "MockStrategy"

    async def test_interval_seconds_none_for_triggered_mode(self):
        """TRIGGERED 模式 interval_seconds 應為 None（無週期意義）。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=ExecutionMode.TRIGGERED))

        report = executor.health()

        assert report.details["execution_mode"] == "TRIGGERED"
        assert report.details["interval_seconds"] is None

    async def test_interval_seconds_present_for_hybrid_mode(self):
        """HYBRID 模式 interval_seconds 應是 float。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=ExecutionMode.HYBRID, interval=0.25))

        report = executor.health()

        assert report.details["execution_mode"] == "HYBRID"
        assert report.details["interval_seconds"] == 0.25
        assert isinstance(report.details["interval_seconds"], float)

    def test_no_strategy_yields_none_strategy_fields(self):
        """無策略時 current_strategy / execution_mode / interval_seconds 皆為 None。"""
        executor = _make_executor()
        report = executor.health()

        assert report.details["current_strategy"] is None
        assert report.details["execution_mode"] is None
        assert report.details["interval_seconds"] is None

    def test_has_offloader_false_by_default(self):
        """預設未注入 offloader → has_offloader=False。"""
        executor = _make_executor()
        report = executor.health()
        assert report.details["has_offloader"] is False

    def test_has_offloader_true_when_injected(self):
        """注入 offloader 時 has_offloader=True。"""
        # 用最小 stub；executor 只在 health() 內檢查 is None
        offloader = object()
        executor = StrategyExecutor(
            context_provider=lambda: StrategyContext(),
            offloader=offloader,  # type: ignore[arg-type]
        )
        report = executor.health()
        assert report.details["has_offloader"] is True

    def test_trigger_pending_reflects_event_state(self):
        """trigger_pending 反映 _trigger_event 狀態。"""
        executor = _make_executor()

        # 初始未 set
        assert executor.health().details["trigger_pending"] is False

        executor.trigger()
        assert executor.health().details["trigger_pending"] is True

    def test_stop_pending_reflects_event_state(self):
        """stop_pending 反映 _stop_event 狀態。"""
        executor = _make_executor()

        assert executor.health().details["stop_pending"] is False

        executor.stop()
        assert executor.health().details["stop_pending"] is True


# =============== NoChange Sentinel Serialization ===============


class TestNoChangeSerialization:
    """驗證 NO_CHANGE sentinel 在 details 中序列化為 "NO_CHANGE" 字串。"""

    def test_no_change_p_target_serialized_as_string(self):
        """p_target=NO_CHANGE → details["last_command"]["p_target"] == "NO_CHANGE"。"""
        executor = _make_executor()
        executor._last_command = Command(p_target=NO_CHANGE, q_target=10.0)

        report = executor.health()

        assert report.details["last_command"]["p_target"] == "NO_CHANGE"
        assert report.details["last_command"]["q_target"] == 10.0

    def test_no_change_q_target_serialized_as_string(self):
        """q_target=NO_CHANGE → 同上。"""
        executor = _make_executor()
        executor._last_command = Command(p_target=5.0, q_target=NO_CHANGE)

        report = executor.health()

        assert report.details["last_command"]["p_target"] == 5.0
        assert report.details["last_command"]["q_target"] == "NO_CHANGE"

    def test_both_no_change_serialized_as_strings(self):
        """雙軸 NO_CHANGE 都應序列化為字串。"""
        executor = _make_executor()
        executor._last_command = Command(p_target=NO_CHANGE, q_target=NO_CHANGE)

        report = executor.health()

        assert report.details["last_command"]["p_target"] == "NO_CHANGE"
        assert report.details["last_command"]["q_target"] == "NO_CHANGE"
        assert report.details["last_command"]["is_fallback"] is False

    def test_normal_floats_preserved_as_floats(self):
        """正常 float 應保留為 float（不被誤序列化）。"""
        executor = _make_executor()
        executor._last_command = Command(p_target=0.0, q_target=0.0)

        report = executor.health()

        assert report.details["last_command"]["p_target"] == 0.0
        assert report.details["last_command"]["q_target"] == 0.0
        assert isinstance(report.details["last_command"]["p_target"], float)
        assert isinstance(report.details["last_command"]["q_target"], float)


# =============== Read-only / Idempotent ===============


class TestHealthReadOnly:
    """驗證 health() 是 read-only：不取 lock、不 await、不改 state。"""

    def test_health_is_sync_method(self):
        """health() 必須是 sync method（不可回傳 coroutine）。"""
        executor = _make_executor()
        result = executor.health()
        # 不是 awaitable
        assert not asyncio.iscoroutine(result)
        assert isinstance(result, HealthReport)

    async def test_health_does_not_modify_state(self):
        """連續呼叫 health() 不應改變 executor state。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=ExecutionMode.PERIODIC, interval=1))
        executor._is_running = True
        executor._last_command = Command(p_target=42.0, q_target=7.0)

        # 快照
        before_strategy = executor._strategy
        before_running = executor._is_running
        before_last = executor._last_command
        before_trigger_set = executor._trigger_event.is_set()
        before_stop_set = executor._stop_event.is_set()

        # 多次呼叫
        for _ in range(5):
            executor.health()

        assert executor._strategy is before_strategy
        assert executor._is_running == before_running
        assert executor._last_command is before_last
        assert executor._trigger_event.is_set() == before_trigger_set
        assert executor._stop_event.is_set() == before_stop_set

    async def test_health_idempotent_two_calls_equal(self):
        """同一 state 下，連續兩次呼叫 health() 結果應相同。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=ExecutionMode.HYBRID, interval=2))
        executor._is_running = True
        executor._last_command = Command(p_target=33.3, q_target=11.1)

        r1 = executor.health()
        r2 = executor.health()

        assert r1.status == r2.status
        assert r1.component == r2.component
        assert r1.message == r2.message
        assert r1.details == r2.details


# =============== Protocol Conformance ===============


class TestHealthCheckableProtocol:
    """驗證 StrategyExecutor structurally 符合 HealthCheckable Protocol。"""

    def test_executor_isinstance_of_health_checkable(self):
        """runtime_checkable Protocol：isinstance 應通過。"""
        executor = _make_executor()
        assert isinstance(executor, HealthCheckable)

    def test_health_returns_health_report(self):
        """health() 回傳 HealthReport instance。"""
        executor = _make_executor()
        report = executor.health()
        assert isinstance(report, HealthReport)
        assert isinstance(report.status, HealthStatus)
        assert isinstance(report.component, str)
        assert isinstance(report.message, str)
        assert isinstance(report.details, dict)


# =============== Status Priority (整合驗證) ===============


class TestStatusPriority:
    """驗證判定優先序：task_dead > no-strategy/not-running > running-no-strategy > fallback > healthy > 兜底。"""

    async def test_task_dead_overrides_running_with_strategy(self):
        """task 異常死亡優先於 HEALTHY 條件。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy())
        executor._is_running = True
        executor._last_command = Command(p_target=1.0)

        async def boom():
            raise ValueError("explicit failure")

        task = asyncio.ensure_future(boom())
        while not task.done():
            await asyncio.sleep(0)
        executor._task = task

        report = executor.health()

        assert report.status is HealthStatus.UNHEALTHY
        assert "ValueError" in report.message

    async def test_run_assigns_task_so_health_can_detect_dead_task(self):
        """run() 啟動後 self._task 應指向 current task；異常終止時 health() 讀得到 task.exception()。

        防 dead-code regression：在補上 `self._task = asyncio.current_task()` 前，
        task-died 分支永遠不可達（_task 始終為 None）。本測試固定此契約。
        """
        executor = _make_executor()

        class _BoomConfigStrategy(Strategy):
            """execution_config 直接 raise，讓 run() 主迴圈未 catch 而傳播例外。"""

            @property
            def execution_config(self) -> ExecutionConfig:
                raise RuntimeError("config explode")

            def execute(self, context: StrategyContext) -> Command:
                return Command()

        await executor.set_strategy(_BoomConfigStrategy())

        run_task = asyncio.ensure_future(executor.run())
        with pytest.raises(RuntimeError, match="config explode"):
            await run_task

        assert executor._task is run_task, "run() 必須 assign self._task"
        assert run_task.done() and run_task.exception() is not None

        report = executor.health()
        assert report.status is HealthStatus.UNHEALTHY
        assert "task died" in report.message
        assert "config explode" in report.message

    async def test_fallback_overrides_healthy(self):
        """last_command.is_fallback=True 應將 HEALTHY 降級為 DEGRADED。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy())
        executor._is_running = True

        # 先 healthy
        executor._last_command = Command(p_target=10.0)
        assert executor.health().status is HealthStatus.HEALTHY

        # 換成 fallback
        executor._last_command = Command(is_fallback=True)
        assert executor.health().status is HealthStatus.DEGRADED

    @pytest.mark.parametrize(
        ("mode", "interval"),
        [
            (ExecutionMode.PERIODIC, 1.0),
            (ExecutionMode.HYBRID, 0.5),
            (ExecutionMode.TRIGGERED, 1.0),  # interval 對 TRIGGERED 無意義但 ExecutionConfig 接受
        ],
    )
    async def test_healthy_across_execution_modes(self, mode: ExecutionMode, interval: float):
        """HEALTHY 判定在多種 ExecutionMode 下都成立。"""
        executor = _make_executor()
        await executor.set_strategy(MockStrategy(mode=mode, interval=interval))
        executor._is_running = True
        executor._last_command = Command(p_target=5.0)

        report = executor.health()

        assert report.status is HealthStatus.HEALTHY
        assert report.details["execution_mode"] == mode.name
        if mode == ExecutionMode.TRIGGERED:
            assert report.details["interval_seconds"] is None
        else:
            assert report.details["interval_seconds"] == interval
