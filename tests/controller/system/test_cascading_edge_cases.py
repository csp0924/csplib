"""CascadingStrategy 邊界案例測試（加法式語義）."""

import math
from unittest.mock import MagicMock

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.system.cascading import CapacityConfig, CascadingStrategy, ClampPriority


def _make_mock_strategy(p: float, q: float):
    """建立固定貢獻量的 mock 策略"""
    s = MagicMock()
    s.execute.return_value = Command(p_target=p, q_target=q)
    return s


class TestCascadingEdgeCases:
    def test_empty_layers_returns_last_command(self):
        cascading = CascadingStrategy(layers=[], capacity=CapacityConfig(s_max_kva=1000))
        last = Command(100, 50)
        ctx = StrategyContext(last_command=last)
        result = cascading.execute(ctx)
        assert result == last

    def test_s_max_zero_clamps_all_output(self):
        """s_max=0: 所有輸出被限幅到 0"""
        layer = _make_mock_strategy(500, 300)
        cascading = CascadingStrategy(layers=[layer], capacity=CapacityConfig(s_max_kva=0))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        # S = hypot(500, 300) = 583 > 0
        # P_FIRST: P 被 clamp 到 min(500, 0) = 0, Q 也 = 0
        assert result.p_target == 0.0
        assert result.q_target == 0.0

    def test_s_max_negative(self):
        """負 s_max: math 仍可運作，effectively blocks all output"""
        layer = _make_mock_strategy(100, 0)
        cascading = CascadingStrategy(layers=[layer], capacity=CapacityConfig(s_max_kva=-10))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        assert isinstance(result, Command)

    def test_nan_from_strategy(self):
        """NaN 輸出: math.hypot(NaN, 0) = NaN"""
        layer = _make_mock_strategy(float("nan"), 0)
        cascading = CascadingStrategy(layers=[layer], capacity=CapacityConfig(s_max_kva=1000))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        assert math.isnan(result.p_target) or isinstance(result.p_target, float)

    def test_inf_from_strategy(self):
        layer = _make_mock_strategy(float("inf"), 0)
        cascading = CascadingStrategy(layers=[layer], capacity=CapacityConfig(s_max_kva=1000))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        assert isinstance(result, Command)

    def test_two_layers_within_capacity(self):
        """兩層加法累積在容量內：P=300+300=600, Q=0+400=400, S=721 < 1000"""
        l1 = _make_mock_strategy(300, 0)
        l2 = _make_mock_strategy(300, 400)
        cascading = CascadingStrategy(layers=[l1, l2], capacity=CapacityConfig(s_max_kva=1000))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        # 加法式累積: P = 300+300 = 600, Q = 0+400 = 400
        assert abs(result.p_target - 600) < 1
        assert abs(result.q_target - 400) < 1

    def test_two_layers_exceeding_capacity_p_first(self):
        """兩層累積超過容量: P=800+800=1600, Q=0+800=800, P_FIRST 限幅"""
        l1 = _make_mock_strategy(800, 0)
        l2 = _make_mock_strategy(800, 800)
        cascading = CascadingStrategy(layers=[l1, l2], capacity=CapacityConfig(s_max_kva=1000))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        s = math.hypot(result.p_target, result.q_target)
        assert s <= 1000.1
        # P_FIRST: P = min(1600, 1000) = 1000, Q 餘量 = sqrt(1000^2 - 1000^2) = 0
        assert result.p_target == pytest.approx(1000.0)
        assert result.q_target == pytest.approx(0.0, abs=0.1)

    def test_two_layers_exceeding_capacity_q_first(self):
        """兩層超容量 Q_FIRST: 保 Q 削 P"""
        l1 = _make_mock_strategy(600, 0)
        l2 = _make_mock_strategy(0, 900)
        cascading = CascadingStrategy(
            layers=[l1, l2], capacity=CapacityConfig(s_max_kva=1000), priority=ClampPriority.Q_FIRST
        )
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        # Q_FIRST: Q = min(900, 1000) = 900, P 餘量 = sqrt(1000^2 - 900^2) ≈ 435.9
        assert result.q_target == pytest.approx(900.0)
        expected_p = math.sqrt(1000**2 - 900**2)
        assert result.p_target == pytest.approx(expected_p, abs=1.0)
        s = math.hypot(result.p_target, result.q_target)
        assert s == pytest.approx(1000.0, abs=1.0)
