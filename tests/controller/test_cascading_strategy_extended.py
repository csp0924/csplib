# =============== CascadingStrategy Extended Tests ===============
#
# CascadingStrategy 的擴展測試（加法式累積 + P/Q 優先級限幅語義）

from __future__ import annotations

import math

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext, SystemBase
from csp_lib.controller.system.cascading import CapacityConfig, CascadingStrategy, ClampPriority

# ============================================================
# Test Strategies（加法式語義：每層輸出 = 貢獻量）
# ============================================================


class FixedStrategy(Strategy):
    """固定貢獻量策略（測試用）"""

    def __init__(self, p: float = 0.0, q: float = 0.0):
        self._p = p
        self._q = q

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(p_target=self._p, q_target=self._q)


class RemainingAwareStrategy(Strategy):
    """讀取 remaining_s_kva 的策略（測試 context 傳播）"""

    def __init__(self) -> None:
        self.received_remaining: float | None = None

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        self.received_remaining = context.extra.get("remaining_s_kva")
        # 使用全部剩餘容量作為 Q 貢獻
        remaining = self.received_remaining or 0.0
        return Command(p_target=0.0, q_target=remaining)


# ============================================================
# 加法式累積 + 限幅測試
# ============================================================


class TestAdditiveClamping:
    """加法式累積核心機制測試"""

    def test_no_clamping_within_capacity(self):
        """容量內不需限幅：P=300+300=600, Q=0+400=400, S=721 < 1000"""
        cascading = CascadingStrategy(
            layers=[FixedStrategy(p=300.0, q=0.0), FixedStrategy(p=300.0, q=400.0)],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        # 加法式: 兩層 P 貢獻相加 = 600, Q 貢獻相加 = 400
        assert abs(result.p_target - 600.0) < 0.01
        assert abs(result.q_target - 400.0) < 0.01

    def test_p_first_clamping_preserves_p(self):
        """P_FIRST 限幅：保護 P，削減 Q"""
        cascading = CascadingStrategy(
            layers=[
                FixedStrategy(p=800.0, q=0.0),
                FixedStrategy(p=0.0, q=900.0),
            ],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        # P_FIRST: P = 800 保持, Q = sqrt(1000^2 - 800^2) = 600
        assert abs(result.p_target - 800.0) < 0.01
        expected_q = math.sqrt(1000.0**2 - 800.0**2)
        assert abs(result.q_target - expected_q) < 1.0
        s = math.hypot(result.p_target, result.q_target)
        assert s <= 1000.1

    def test_p_first_p_exceeds_capacity_alone(self):
        """P_FIRST: P 本身就超過 S_max -> P 限幅到 S_max, Q=0"""
        cascading = CascadingStrategy(
            layers=[
                FixedStrategy(p=600.0, q=0.0),
                FixedStrategy(p=0.0, q=1200.0),
            ],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        # P_FIRST: P = min(600, 1000) = 600, Q = sqrt(1000^2 - 600^2) = 800
        assert abs(result.p_target - 600.0) < 0.01
        expected_q = math.sqrt(1000.0**2 - 600.0**2)
        assert abs(result.q_target - expected_q) < 1.0
        s = math.hypot(result.p_target, result.q_target)
        assert s <= 1000.1
        assert s >= 999.0

    def test_q_first_clamping_preserves_q(self):
        """Q_FIRST 限幅：保護 Q，削減 P"""
        cascading = CascadingStrategy(
            layers=[
                FixedStrategy(p=800.0, q=0.0),
                FixedStrategy(p=0.0, q=900.0),
            ],
            capacity=CapacityConfig(s_max_kva=1000.0),
            priority=ClampPriority.Q_FIRST,
        )
        result = cascading.execute(StrategyContext())
        # Q_FIRST: Q = 900 保持, P = sqrt(1000^2 - 900^2) ≈ 435.9
        assert abs(result.q_target - 900.0) < 0.01
        expected_p = math.sqrt(1000.0**2 - 900.0**2)
        assert abs(result.p_target - expected_p) < 1.0
        s = math.hypot(result.p_target, result.q_target)
        assert s <= 1000.1


class TestContextPropagation:
    """Context 在層間的傳播測試"""

    def test_remaining_s_kva_propagation(self):
        """Layer 2+ 應收到 remaining_s_kva"""
        layer2 = RemainingAwareStrategy()
        cascading = CascadingStrategy(
            layers=[FixedStrategy(p=600.0, q=0.0), layer2],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        cascading.execute(StrategyContext())
        assert layer2.received_remaining is not None
        assert abs(layer2.received_remaining - 400.0) < 0.01

    def test_first_layer_gets_zero_accumulated(self):
        """加法式語義：Layer 1 的 last_command = Command(0, 0)（累積起點）"""
        original_cmd = Command(p_target=100.0, q_target=50.0)

        class RecordingStrategy(Strategy):
            received_context: StrategyContext | None = None

            @property
            def execution_config(self) -> ExecutionConfig:
                return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

            def execute(self, context: StrategyContext) -> Command:
                self.received_context = context
                return Command(p_target=500.0)

        layer1 = RecordingStrategy()
        cascading = CascadingStrategy(
            layers=[layer1],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        ctx = StrategyContext(last_command=original_cmd)
        cascading.execute(ctx)
        assert layer1.received_context is not None
        # 加法式: 第一層收到的 last_command 是 Command(0, 0)
        assert layer1.received_context.last_command.p_target == 0.0
        assert layer1.received_context.last_command.q_target == 0.0

    def test_later_layers_get_accumulated_command(self):
        """Layer 2+ 的 last_command 為前幾層的累積結果"""

        class RecordingStrategy(Strategy):
            received_last_command: Command | None = None

            @property
            def execution_config(self) -> ExecutionConfig:
                return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

            def execute(self, context: StrategyContext) -> Command:
                self.received_last_command = context.last_command
                return Command()  # 貢獻量 = 0

        layer2 = RecordingStrategy()
        cascading = CascadingStrategy(
            layers=[FixedStrategy(p=500.0, q=200.0), layer2],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        cascading.execute(StrategyContext())
        assert layer2.received_last_command is not None
        assert abs(layer2.received_last_command.p_target - 500.0) < 0.01
        assert abs(layer2.received_last_command.q_target - 200.0) < 0.01


class TestMultiLayerScenarios:
    """多層場景測試"""

    def test_three_layer_allocation(self):
        """三層分配：P=300+0+100=400, Q=0+200+0=200"""
        cascading = CascadingStrategy(
            layers=[
                FixedStrategy(p=300.0, q=0.0),
                FixedStrategy(p=0.0, q=200.0),
                FixedStrategy(p=100.0, q=0.0),
            ],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        assert abs(result.p_target - 400.0) < 0.01
        assert abs(result.q_target - 200.0) < 0.01

    def test_four_layer_with_clamping(self):
        """四層累積超過容量，P_FIRST 限幅"""
        cascading = CascadingStrategy(
            layers=[
                FixedStrategy(p=500.0, q=0.0),
                FixedStrategy(p=0.0, q=300.0),
                FixedStrategy(p=200.0, q=0.0),
                FixedStrategy(p=0.0, q=500.0),
            ],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        # 累積: P = 500+0+200+0 = 700, Q = 0+300+0+500 = 800
        # S = hypot(700, 800) = 1063 > 1000
        # P_FIRST: P = 700 保持, Q = sqrt(1000^2 - 700^2) ≈ 714.1
        s = math.hypot(result.p_target, result.q_target)
        assert s <= 1000.1
        assert result.p_target == pytest.approx(700.0)

    def test_all_layers_zero_contribution(self):
        """所有層貢獻量=0 -> 結果為 Command(0, 0)"""
        cascading = CascadingStrategy(
            layers=[
                FixedStrategy(p=0.0, q=0.0),
                FixedStrategy(p=0.0, q=0.0),
            ],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        assert result.p_target == 0.0
        assert result.q_target == 0.0


class TestHierarchicalIntegration:
    """階層控制整合場景"""

    def test_parent_command_via_extra(self):
        """上層命令透過 context.extra 傳入"""

        class ChildStrategy(Strategy):
            @property
            def execution_config(self) -> ExecutionConfig:
                return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

            def execute(self, context: StrategyContext) -> Command:
                parent_p = context.extra.get("parent_p_target", 0.0)
                parent_q = context.extra.get("parent_q_target", 0.0)
                return Command(p_target=parent_p, q_target=parent_q)

        cascading = CascadingStrategy(
            layers=[ChildStrategy()],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        ctx = StrategyContext(
            extra={"parent_p_target": 400.0, "parent_q_target": 200.0},
        )
        result = cascading.execute(ctx)
        assert abs(result.p_target - 400.0) < 0.01
        assert abs(result.q_target - 200.0) < 0.01

    def test_cascading_with_system_base(self):
        """搭配 SystemBase 的百分比轉換"""

        class PercentStrategy(Strategy):
            @property
            def execution_config(self) -> ExecutionConfig:
                return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

            def execute(self, context: StrategyContext) -> Command:
                if context.system_base:
                    p = context.percent_to_kw(50.0)  # 50% -> 500kW
                    return Command(p_target=p)
                return Command()

        cascading = CascadingStrategy(
            layers=[PercentStrategy()],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        ctx = StrategyContext(system_base=SystemBase(p_base=1000.0, q_base=500.0))
        result = cascading.execute(ctx)
        assert abs(result.p_target - 500.0) < 0.01


class TestEdgeCases:
    """邊緣案例"""

    def test_empty_layers(self):
        """空層列表回傳 last_command"""
        cascading = CascadingStrategy(layers=[], capacity=CapacityConfig(s_max_kva=1000.0))
        ctx = StrategyContext(last_command=Command(p_target=100.0, q_target=50.0))
        result = cascading.execute(ctx)
        assert result == ctx.last_command

    def test_single_layer_within_capacity(self):
        """單層在容量內"""
        cascading = CascadingStrategy(
            layers=[FixedStrategy(p=500.0, q=300.0)],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        assert abs(result.p_target - 500.0) < 0.01
        assert abs(result.q_target - 300.0) < 0.01

    def test_negative_power(self):
        """負功率（充電）場景"""
        cascading = CascadingStrategy(
            layers=[FixedStrategy(p=-600.0, q=0.0), FixedStrategy(p=0.0, q=300.0)],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        s = math.hypot(result.p_target, result.q_target)
        assert s <= 1000.1
        assert result.p_target < 0  # 充電

    async def test_on_activate_delegates(self):
        """on_activate 委派給所有子策略"""
        activated = []

        class TrackingStrategy(FixedStrategy):
            async def on_activate(self):
                activated.append(self)

        s1 = TrackingStrategy(p=100.0)
        s2 = TrackingStrategy(p=200.0)
        cascading = CascadingStrategy(
            layers=[s1, s2],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        await cascading.on_activate()
        assert len(activated) == 2

    async def test_on_deactivate_delegates(self):
        """on_deactivate 委派給所有子策略"""
        deactivated = []

        class TrackingStrategy(FixedStrategy):
            async def on_deactivate(self):
                deactivated.append(self)

        s1 = TrackingStrategy(p=100.0)
        s2 = TrackingStrategy(p=200.0)
        cascading = CascadingStrategy(
            layers=[s1, s2],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        await cascading.on_deactivate()
        assert len(deactivated) == 2

    def test_str_representation(self):
        """字串表示"""
        cascading = CascadingStrategy(
            layers=[FixedStrategy(p=100.0)],
            capacity=CapacityConfig(s_max_kva=500.0),
        )
        s = str(cascading)
        assert "CascadingStrategy" in s
        assert "500" in s

    def test_negative_p_and_q_clamping(self):
        """負 P 和 Q 的限幅：copysign 確保符號正確"""
        cascading = CascadingStrategy(
            layers=[FixedStrategy(p=-800.0, q=-800.0)],
            capacity=CapacityConfig(s_max_kva=1000.0),
        )
        result = cascading.execute(StrategyContext())
        s = math.hypot(result.p_target, result.q_target)
        assert s == pytest.approx(1000.0, abs=1.0)
        # P_FIRST: 保 P=-800, Q 被削
        assert result.p_target == pytest.approx(-800.0)
        assert result.q_target < 0  # 負號保持
