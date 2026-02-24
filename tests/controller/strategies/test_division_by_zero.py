import math

import pytest

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.services import PVDataService
from csp_lib.controller.strategies.fp_strategy import FPConfig, FPStrategy
from csp_lib.controller.strategies.pv_smooth_strategy import PVSmoothConfig, PVSmoothStrategy
from csp_lib.controller.strategies.qv_strategy import QVConfig, QVStrategy


class TestQVDivisionByZero:
    def test_nominal_voltage_zero_validate_raises(self):
        config = QVConfig(nominal_voltage=0)
        with pytest.raises(ValueError):
            config.validate()

    def test_nominal_voltage_negative_validate_raises(self):
        config = QVConfig(nominal_voltage=-100)
        with pytest.raises(ValueError):
            config.validate()

    def test_voltage_nan_in_context(self):
        """NaN voltage should not crash, but produces NaN comparison behavior"""
        strategy = QVStrategy(QVConfig())
        ctx = StrategyContext(last_command=Command(100, 50), extra={"voltage": float("nan")})
        result = strategy.execute(ctx)
        # NaN comparisons are all False, so v_pu <= v_set_pu - v_deadband is False,
        # v_pu >= v_set_pu + v_deadband is False -> returns 0.0 Q
        assert result.q_target == 0.0 or math.isnan(result.q_target)

    def test_voltage_inf_in_context(self):
        strategy = QVStrategy(QVConfig())
        ctx = StrategyContext(last_command=Command(100, 50), extra={"voltage": float("inf")})
        result = strategy.execute(ctx)
        # inf >= v_set_pu + v_deadband -> negative Q (absorb)
        assert isinstance(result, Command)

    def test_voltage_none_returns_last_command(self):
        strategy = QVStrategy(QVConfig())
        last = Command(100, 50)
        ctx = StrategyContext(last_command=last, extra={})
        result = strategy.execute(ctx)
        assert result == last


class TestPVSmoothEdgeCases:
    def test_capacity_zero_rate_limit(self):
        """When capacity=0, rate_limit=0, so target is clamped to last_command"""
        config = PVSmoothConfig(capacity=0, ramp_rate=10)
        svc = PVDataService(max_history=10)
        svc.append(500.0)
        strategy = PVSmoothStrategy(config, svc)
        ctx = StrategyContext(last_command=Command(100, 0))
        result = strategy.execute(ctx)
        # rate_limit = 0 * 10 / 100 = 0, so target clamped to last_command.p_target
        assert result.p_target == 100.0

    def test_nan_in_pv_history(self):
        """NaN in PV history: sum([NaN, 100]) = NaN -> avg = NaN"""
        config = PVSmoothConfig(capacity=1000, ramp_rate=10)
        svc = PVDataService(max_history=10)
        svc.append(float("nan"))
        svc.append(100.0)
        strategy = PVSmoothStrategy(config, svc)
        ctx = StrategyContext(last_command=Command(0, 0))
        result = strategy.execute(ctx)
        # NaN propagates through sum() -> NaN average
        # max(NaN - 0, 0.0) behavior depends on implementation
        assert isinstance(result, Command)

    def test_all_none_history(self):
        """All None history: get_average returns None -> Command(0,0)"""
        config = PVSmoothConfig(capacity=1000, ramp_rate=10)
        svc = PVDataService(max_history=10)
        svc.append(None)
        svc.append(None)
        strategy = PVSmoothStrategy(config, svc)
        ctx = StrategyContext(last_command=Command(100, 50))
        result = strategy.execute(ctx)
        assert result.p_target == 0.0
        assert result.q_target == 0.0

    def test_no_pv_service(self):
        strategy = PVSmoothStrategy(PVSmoothConfig())
        ctx = StrategyContext(last_command=Command(100, 50))
        result = strategy.execute(ctx)
        assert result.p_target == 0.0
        assert result.q_target == 0.0


class TestFPInterpolateEdgeCases:
    def test_interpolate_equal_x_values(self):
        """When x1 == x2, _interpolate returns y1 (guarded)"""
        result = FPStrategy._interpolate(5.0, 5.0, 5.0, 10.0, 20.0)
        assert result == 10.0

    def test_interpolate_nan_x(self):
        result = FPStrategy._interpolate(float("nan"), 1.0, 2.0, 10.0, 20.0)
        # NaN arithmetic: y1 + (y2-y1)*(NaN-x1)/(x2-x1) = NaN
        assert math.isnan(result)

    def test_frequency_none_returns_last_command(self):
        strategy = FPStrategy(FPConfig())
        last = Command(100, 50)
        ctx = StrategyContext(last_command=last, extra={})
        result = strategy.execute(ctx)
        assert result == last
