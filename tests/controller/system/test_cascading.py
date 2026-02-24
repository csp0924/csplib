"""Tests for CascadingStrategy."""

import math

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system.cascading import CapacityConfig, CascadingStrategy


class FixedStrategy(Strategy):
    """固定輸出策略（用於測試）"""

    def __init__(self, p: float = 0.0, q: float = 0.0):
        self._p = p
        self._q = q
        self.activated = False
        self.deactivated = False

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(p_target=self._p, q_target=self._q)

    async def on_activate(self) -> None:
        self.activated = True

    async def on_deactivate(self) -> None:
        self.deactivated = True


class AdditiveStrategy(Strategy):
    """累加策略：在 last_command 基礎上加增量"""

    def __init__(self, delta_p: float = 0.0, delta_q: float = 0.0):
        self._delta_p = delta_p
        self._delta_q = delta_q

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(
            p_target=context.last_command.p_target + self._delta_p,
            q_target=context.last_command.q_target + self._delta_q,
        )


class TestCascadingSingleLayer:
    def test_single_layer_passthrough(self):
        """單層直接傳遞"""
        strategy = FixedStrategy(p=500.0, q=200.0)
        cascading = CascadingStrategy(
            layers=[strategy],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        assert cmd.p_target == 500.0
        assert cmd.q_target == 200.0

    def test_single_layer_within_capacity(self):
        """單層在容量內"""
        strategy = FixedStrategy(p=600.0, q=800.0)
        cascading = CascadingStrategy(
            layers=[strategy],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        assert math.hypot(cmd.p_target, cmd.q_target) == pytest.approx(1000.0, abs=1.0)

    def test_single_layer_exceeds_capacity(self):
        """單層超過容量 → delta clamped"""
        strategy = FixedStrategy(p=800.0, q=800.0)
        cascading = CascadingStrategy(
            layers=[strategy],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        s = math.hypot(cmd.p_target, cmd.q_target)
        assert s == pytest.approx(1000.0, abs=1.0)
        # 等比例縮放
        assert cmd.p_target == pytest.approx(cmd.q_target, abs=0.1)


class TestCascadingMultiLayer:
    def test_two_layers_within_capacity(self):
        """PQ + QV 不超過容量"""
        pq = FixedStrategy(p=300.0, q=0.0)
        qv = AdditiveStrategy(delta_p=0.0, delta_q=200.0)
        cascading = CascadingStrategy(
            layers=[pq, qv],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        assert cmd.p_target == pytest.approx(300.0)
        assert cmd.q_target == pytest.approx(200.0)

    def test_delta_clamping_preserves_first_layer(self):
        """P=600 + Q=900 → delta clamping 只縮 Q"""
        pq = FixedStrategy(p=600.0, q=0.0)
        qv = AdditiveStrategy(delta_p=0.0, delta_q=900.0)
        cascading = CascadingStrategy(
            layers=[pq, qv],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)

        # P 必須保持 600（高優先層不被修改）
        assert cmd.p_target == pytest.approx(600.0)
        # Q 被 clamp: remaining = √(1000²-600²) = 800
        expected_q = math.sqrt(1000**2 - 600**2)
        assert cmd.q_target == pytest.approx(expected_q, abs=1.0)
        # 總 S ≤ 1000
        s = math.hypot(cmd.p_target, cmd.q_target)
        assert s == pytest.approx(1000.0, abs=1.0)

    def test_three_layers_cascading(self):
        """三層級聯"""
        layer1 = FixedStrategy(p=400.0, q=0.0)
        layer2 = AdditiveStrategy(delta_p=0.0, delta_q=300.0)
        layer3 = AdditiveStrategy(delta_p=100.0, delta_q=0.0)
        cascading = CascadingStrategy(
            layers=[layer1, layer2, layer3],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        # S = √(500² + 300²) = 583 < 1000 → 不 clamp
        assert cmd.p_target == pytest.approx(500.0)
        assert cmd.q_target == pytest.approx(300.0)

    def test_second_layer_zero_remaining(self):
        """第一層用完容量 → 第二層 delta 全部 clamp 到 0"""
        pq = FixedStrategy(p=1000.0, q=0.0)
        qv = AdditiveStrategy(delta_p=0.0, delta_q=500.0)
        cascading = CascadingStrategy(
            layers=[pq, qv],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        assert cmd.p_target == pytest.approx(1000.0)
        assert cmd.q_target == pytest.approx(0.0, abs=0.1)


class TestCascadingEdgeCases:
    def test_empty_layers(self):
        """空層列表 → 回傳 last_command"""
        cascading = CascadingStrategy(
            layers=[],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext(last_command=Command(p_target=100.0, q_target=50.0))
        cmd = cascading.execute(context)
        assert cmd.p_target == 100.0
        assert cmd.q_target == 50.0

    def test_first_layer_receives_original_context(self):
        """第一層收到原始 context（含 executor 注入的 last_command）"""
        received_contexts = []

        class CapturingStrategy(Strategy):
            @property
            def execution_config(self) -> ExecutionConfig:
                return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

            def execute(self, context: StrategyContext) -> Command:
                received_contexts.append(context)
                return Command(p_target=100.0, q_target=0.0)

        cascading = CascadingStrategy(
            layers=[CapturingStrategy()],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        original_cmd = Command(p_target=42.0, q_target=13.0)
        context = StrategyContext(last_command=original_cmd, extra={"key": "value"})
        cascading.execute(context)

        assert len(received_contexts) == 1
        assert received_contexts[0].last_command is original_cmd
        assert received_contexts[0].extra["key"] == "value"

    def test_subsequent_layer_receives_remaining_kva(self):
        """後續層收到 remaining_s_kva"""
        received_extras = []

        class CapturingStrategy(Strategy):
            @property
            def execution_config(self) -> ExecutionConfig:
                return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

            def execute(self, context: StrategyContext) -> Command:
                received_extras.append(dict(context.extra))
                return context.last_command

        pq = FixedStrategy(p=600.0, q=0.0)
        capture = CapturingStrategy()
        cascading = CascadingStrategy(
            layers=[pq, capture],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        cascading.execute(StrategyContext())

        assert len(received_extras) == 1
        assert received_extras[0]["remaining_s_kva"] == pytest.approx(400.0)

    def test_no_delta_skips_clamping(self):
        """層輸出與累積相同 → 跳過 clamping"""
        # 第二層不產生任何增量
        pq = FixedStrategy(p=500.0, q=0.0)
        noop = AdditiveStrategy(delta_p=0.0, delta_q=0.0)
        cascading = CascadingStrategy(
            layers=[pq, noop],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        assert cmd.p_target == pytest.approx(500.0)
        assert cmd.q_target == pytest.approx(0.0)


class TestCascadingLifecycle:
    @pytest.mark.asyncio
    async def test_on_activate_delegates(self):
        """on_activate 委派給所有子策略"""
        s1 = FixedStrategy()
        s2 = FixedStrategy()
        cascading = CascadingStrategy(
            layers=[s1, s2],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        await cascading.on_activate()
        assert s1.activated is True
        assert s2.activated is True

    @pytest.mark.asyncio
    async def test_on_deactivate_delegates(self):
        """on_deactivate 委派給所有子策略"""
        s1 = FixedStrategy()
        s2 = FixedStrategy()
        cascading = CascadingStrategy(
            layers=[s1, s2],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        await cascading.on_deactivate()
        assert s1.deactivated is True
        assert s2.deactivated is True


class TestCascadingStr:
    def test_str_repr(self):
        s = FixedStrategy()
        cascading = CascadingStrategy(
            layers=[s],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        result = str(cascading)
        assert "CascadingStrategy" in result
        assert "1000" in result

    def test_execution_config(self):
        cascading = CascadingStrategy(
            layers=[],
            capacity=CapacityConfig(s_max_kva=1000),
            execution_config=ExecutionConfig(mode=ExecutionMode.HYBRID, interval_seconds=2),
        )
        assert cascading.execution_config.mode == ExecutionMode.HYBRID
        assert cascading.execution_config.interval_seconds == 2


class TestCapacityConfig:
    def test_frozen(self):
        cfg = CapacityConfig(s_max_kva=1000)
        with pytest.raises(AttributeError):
            cfg.s_max_kva = 500  # type: ignore[misc]
