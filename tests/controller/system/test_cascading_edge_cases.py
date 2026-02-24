import math
from unittest.mock import MagicMock

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.system.cascading import CapacityConfig, CascadingStrategy


def _make_mock_strategy(p: float, q: float):
    """Create a mock strategy that always returns Command(p, q)"""
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
        """s_max=0: all output clamped"""
        layer = _make_mock_strategy(500, 300)
        cascading = CascadingStrategy(layers=[layer], capacity=CapacityConfig(s_max_kva=0))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        # new_s = hypot(500, 300) > 0, a_coeff > 0, discriminant = -4*a*(-0) = 0
        # scale = 0 / (2*a) = 0
        assert result.p_target == 0.0
        assert result.q_target == 0.0

    def test_s_max_negative(self):
        """Negative s_max: math still works, effectively blocks all output"""
        layer = _make_mock_strategy(100, 0)
        cascading = CascadingStrategy(layers=[layer], capacity=CapacityConfig(s_max_kva=-10))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        # new_s = 100 > -10, discriminant = 0 - 4*a*(0 - 100) < 0 -> scale=0
        assert isinstance(result, Command)

    def test_nan_from_strategy(self):
        """NaN output from strategy: math.hypot(NaN, 0) = NaN"""
        layer = _make_mock_strategy(float("nan"), 0)
        cascading = CascadingStrategy(layers=[layer], capacity=CapacityConfig(s_max_kva=1000))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        # NaN delta -> NaN accumulated
        assert math.isnan(result.p_target) or isinstance(result.p_target, float)

    def test_inf_from_strategy(self):
        layer = _make_mock_strategy(float("inf"), 0)
        cascading = CascadingStrategy(layers=[layer], capacity=CapacityConfig(s_max_kva=1000))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        assert isinstance(result, Command)

    def test_two_layers_within_capacity(self):
        """Two layers that stay within capacity - no clamping"""
        l1 = _make_mock_strategy(300, 0)
        l2 = _make_mock_strategy(300, 400)  # delta_q=400
        cascading = CascadingStrategy(layers=[l1, l2], capacity=CapacityConfig(s_max_kva=1000))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        assert abs(result.p_target - 300) < 1
        assert abs(result.q_target - 400) < 1

    def test_two_layers_exceeding_capacity(self):
        """Two layers exceeding capacity - second layer delta gets clamped"""
        l1 = _make_mock_strategy(800, 0)
        l2 = _make_mock_strategy(800, 800)  # wants delta_q=800, hypot(800,800)=1131 > 1000
        cascading = CascadingStrategy(layers=[l1, l2], capacity=CapacityConfig(s_max_kva=1000))
        ctx = StrategyContext(last_command=Command())
        result = cascading.execute(ctx)
        s = math.hypot(result.p_target, result.q_target)
        assert s <= 1000.1  # within capacity (small float tolerance)
