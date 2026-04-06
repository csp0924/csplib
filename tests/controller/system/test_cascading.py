"""Tests for CascadingStrategy (加法式累積 + P/Q 優先級限幅)."""

import math

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system.cascading import CapacityConfig, CascadingStrategy, ClampPriority


class FixedStrategy(Strategy):
    """固定輸出貢獻量策略（用於測試）"""

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


class TestCascadingSingleLayer:
    def test_single_layer_passthrough(self):
        """單層：貢獻量 P=500, Q=200 直接通過（S=538 < 1000）"""
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
        """單層：S=hypot(600,800)=1000 剛好等於容量 -> 不限幅"""
        strategy = FixedStrategy(p=600.0, q=800.0)
        cascading = CascadingStrategy(
            layers=[strategy],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        assert math.hypot(cmd.p_target, cmd.q_target) == pytest.approx(1000.0, abs=1.0)

    def test_single_layer_exceeds_capacity_p_first(self):
        """單層超過容量，P_FIRST 預設：保 P 削 Q"""
        strategy = FixedStrategy(p=800.0, q=800.0)
        cascading = CascadingStrategy(
            layers=[strategy],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        s = math.hypot(cmd.p_target, cmd.q_target)
        assert s == pytest.approx(1000.0, abs=1.0)
        # P_FIRST: P 保持 800，Q 被削減到 sqrt(1000^2 - 800^2) = 600
        assert cmd.p_target == pytest.approx(800.0)
        assert cmd.q_target == pytest.approx(600.0, abs=1.0)


class TestCascadingMultiLayer:
    def test_two_layers_within_capacity(self):
        """PQ 貢獻 P=300 + QV 貢獻 Q=200 -> S=360 < 1000 不限幅"""
        pq = FixedStrategy(p=300.0, q=0.0)
        qv = FixedStrategy(p=0.0, q=200.0)
        cascading = CascadingStrategy(
            layers=[pq, qv],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        assert cmd.p_target == pytest.approx(300.0)
        assert cmd.q_target == pytest.approx(200.0)

    def test_p_first_clamping_preserves_p(self):
        """P=600 + Q=900 -> S=1082 > 1000, P_FIRST: 保 P=600, Q=sqrt(1000^2-600^2)=800"""
        pq = FixedStrategy(p=600.0, q=0.0)
        qv = FixedStrategy(p=0.0, q=900.0)
        cascading = CascadingStrategy(
            layers=[pq, qv],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)

        # P_FIRST：P 保持不動
        assert cmd.p_target == pytest.approx(600.0)
        # Q 被限幅: sqrt(1000^2 - 600^2) = 800
        expected_q = math.sqrt(1000**2 - 600**2)
        assert cmd.q_target == pytest.approx(expected_q, abs=1.0)
        # S <= 1000
        s = math.hypot(cmd.p_target, cmd.q_target)
        assert s == pytest.approx(1000.0, abs=1.0)

    def test_three_layers_within_capacity(self):
        """三層級聯：P=400+100=500, Q=300 -> S=583 < 1000 不限幅"""
        layer1 = FixedStrategy(p=400.0, q=0.0)
        layer2 = FixedStrategy(p=0.0, q=300.0)
        layer3 = FixedStrategy(p=100.0, q=0.0)
        cascading = CascadingStrategy(
            layers=[layer1, layer2, layer3],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        # 加法累積：P = 400+0+100 = 500, Q = 0+300+0 = 300
        assert cmd.p_target == pytest.approx(500.0)
        assert cmd.q_target == pytest.approx(300.0)

    def test_first_layer_uses_full_capacity(self):
        """第一層用完容量(P=1000) + 第二層貢獻 Q=500 -> P_FIRST 保 P=1000, Q=0"""
        pq = FixedStrategy(p=1000.0, q=0.0)
        qv = FixedStrategy(p=0.0, q=500.0)
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
        """空層列表 -> 回傳 last_command"""
        cascading = CascadingStrategy(
            layers=[],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext(last_command=Command(p_target=100.0, q_target=50.0))
        cmd = cascading.execute(context)
        assert cmd.p_target == 100.0
        assert cmd.q_target == 50.0

    def test_first_layer_receives_zero_accumulated(self):
        """加法式語義：第一層的 last_command 為 Command(0,0)（累積從零開始）"""
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
        # 原始 context 有 last_command=Command(42, 13)，但加法式語義下
        # 第一層收到的 last_command 是 Command(0, 0)（累積起點）
        context = StrategyContext(last_command=Command(p_target=42.0, q_target=13.0), extra={"key": "value"})
        cascading.execute(context)

        assert len(received_contexts) == 1
        # 加法式：累積從 0 開始，第一層的 last_command = Command(0, 0)
        assert received_contexts[0].last_command.p_target == 0.0
        assert received_contexts[0].last_command.q_target == 0.0
        # extra 中的使用者自訂 key 保持傳遞
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
                return Command()  # 貢獻量 = 0

        pq = FixedStrategy(p=600.0, q=0.0)
        capture = CapturingStrategy()
        cascading = CascadingStrategy(
            layers=[pq, capture],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        cascading.execute(StrategyContext())

        assert len(received_extras) == 1
        assert received_extras[0]["remaining_s_kva"] == pytest.approx(400.0)

    def test_zero_contribution_does_not_affect_total(self):
        """某層貢獻量為零，不影響累積結果"""
        pq = FixedStrategy(p=500.0, q=0.0)
        noop = FixedStrategy(p=0.0, q=0.0)
        cascading = CascadingStrategy(
            layers=[pq, noop],
            capacity=CapacityConfig(s_max_kva=1000),
        )
        context = StrategyContext()
        cmd = cascading.execute(context)
        assert cmd.p_target == pytest.approx(500.0)
        assert cmd.q_target == pytest.approx(0.0)


class TestClampPriorityQFirst:
    """ClampPriority.Q_FIRST 限幅測試"""

    def test_q_first_preserves_q(self):
        """Q_FIRST: P=900, Q=600 -> S=1082 > 1000, 保 Q=600, 削 P=sqrt(1000^2-600^2)=800"""
        pq = FixedStrategy(p=900.0, q=0.0)
        qv = FixedStrategy(p=0.0, q=600.0)
        cascading = CascadingStrategy(
            layers=[pq, qv],
            capacity=CapacityConfig(s_max_kva=1000),
            priority=ClampPriority.Q_FIRST,
        )
        cmd = cascading.execute(StrategyContext())

        # Q_FIRST: Q 保持不動
        assert cmd.q_target == pytest.approx(600.0)
        # P 被限幅: sqrt(1000^2 - 600^2) = 800
        expected_p = math.sqrt(1000**2 - 600**2)
        assert cmd.p_target == pytest.approx(expected_p, abs=1.0)
        # S <= 1000
        s = math.hypot(cmd.p_target, cmd.q_target)
        assert s == pytest.approx(1000.0, abs=1.0)

    def test_q_first_q_exceeds_capacity_alone(self):
        """Q_FIRST: Q 本身就超過 S_max -> Q 限幅到 S_max, P=0"""
        qv = FixedStrategy(p=0.0, q=1200.0)
        pq = FixedStrategy(p=500.0, q=0.0)
        cascading = CascadingStrategy(
            layers=[qv, pq],
            capacity=CapacityConfig(s_max_kva=1000),
            priority=ClampPriority.Q_FIRST,
        )
        cmd = cascading.execute(StrategyContext())

        # Q 被限幅到 1000
        assert cmd.q_target == pytest.approx(1000.0)
        # P 無餘量
        assert cmd.p_target == pytest.approx(0.0, abs=0.1)

    def test_q_first_within_capacity_no_clamping(self):
        """Q_FIRST: S 在容量內 -> 不限幅"""
        pq = FixedStrategy(p=300.0, q=0.0)
        qv = FixedStrategy(p=0.0, q=400.0)
        cascading = CascadingStrategy(
            layers=[pq, qv],
            capacity=CapacityConfig(s_max_kva=1000),
            priority=ClampPriority.Q_FIRST,
        )
        cmd = cascading.execute(StrategyContext())
        assert cmd.p_target == pytest.approx(300.0)
        assert cmd.q_target == pytest.approx(400.0)


class TestCascadingLifecycle:
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

    def test_str_shows_priority(self):
        """str 包含 priority 資訊"""
        cascading = CascadingStrategy(
            layers=[],
            capacity=CapacityConfig(s_max_kva=1000),
            priority=ClampPriority.Q_FIRST,
        )
        result = str(cascading)
        assert "q_first" in result

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
