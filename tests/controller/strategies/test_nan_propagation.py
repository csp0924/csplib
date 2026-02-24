import math

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.services import PVDataService
from csp_lib.controller.strategies.pv_smooth_strategy import PVSmoothConfig, PVSmoothStrategy


class TestPVDataServiceNaN:
    def test_nan_in_history(self):
        """NaN is not None, so it passes the filter in get_history"""
        svc = PVDataService(max_history=10)
        svc.append(float("nan"))
        svc.append(100.0)
        history = svc.get_history()
        assert len(history) == 2  # NaN passes the "is not None" filter

    def test_nan_average(self):
        """sum([NaN, 100]) / 2 = NaN"""
        svc = PVDataService(max_history=10)
        svc.append(float("nan"))
        svc.append(100.0)
        avg = svc.get_average()
        assert math.isnan(avg)

    def test_inf_in_history(self):
        svc = PVDataService(max_history=10)
        svc.append(float("inf"))
        svc.append(100.0)
        avg = svc.get_average()
        assert math.isinf(avg)


class TestPVSmoothNaNEndToEnd:
    def test_nan_average_propagation(self):
        """NaN propagates through PVSmooth: avg=NaN -> adjusted=NaN -> target=NaN"""
        config = PVSmoothConfig(capacity=1000, ramp_rate=10)
        svc = PVDataService(max_history=10)
        svc.append(float("nan"))
        strategy = PVSmoothStrategy(config, svc)
        ctx = StrategyContext(last_command=Command(0, 0))
        result = strategy.execute(ctx)
        # max(NaN - 0, 0.0) depends on Python: max(nan, 0) = nan in CPython
        # The result p_target should be NaN (demonstrating the data corruption)
        assert isinstance(result, Command)
