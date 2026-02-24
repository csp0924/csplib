# =============== Manager Schedule Tests - Factory ===============
#
# StrategyFactory 單元測試
#
# 測試覆蓋：
# - 各策略類型的建立
# - 缺少依賴時回傳 None
# - ConfigMixin.from_dict 額外 key 過濾

from __future__ import annotations

from unittest.mock import MagicMock

from csp_lib.controller.strategies import (
    BypassStrategy,
    FPStrategy,
    IslandModeStrategy,
    PQModeStrategy,
    PVSmoothStrategy,
    QVStrategy,
    StopStrategy,
)
from csp_lib.manager.schedule.factory import StrategyFactory
from csp_lib.manager.schedule.schema import StrategyType


class TestStrategyFactory:
    """StrategyFactory 測試"""

    def test_create_pq(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.PQ, {"p": 100, "q": 50})

        assert isinstance(strategy, PQModeStrategy)
        assert strategy.config.p == 100
        assert strategy.config.q == 50

    def test_create_pq_empty_config(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.PQ, {})

        assert isinstance(strategy, PQModeStrategy)
        assert strategy.config.p == 0.0
        assert strategy.config.q == 0.0

    def test_create_pq_none_config(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.PQ, None)

        assert isinstance(strategy, PQModeStrategy)

    def test_create_pv_smooth_with_service(self):
        pv_service = MagicMock()
        factory = StrategyFactory(pv_service=pv_service)
        strategy = factory.create(StrategyType.PV_SMOOTH, {"capacity": 500, "ramp_rate": 5})

        assert isinstance(strategy, PVSmoothStrategy)
        assert strategy.config.capacity == 500
        assert strategy.config.ramp_rate == 5
        assert strategy.pv_service is pv_service

    def test_create_pv_smooth_without_service(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.PV_SMOOTH, {"capacity": 500})

        assert strategy is None

    def test_create_qv(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.QV, {"nominal_voltage": 380, "droop": 5})

        assert isinstance(strategy, QVStrategy)
        assert strategy.config.nominal_voltage == 380
        assert strategy.config.droop == 5

    def test_create_fp(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.FP, {"f_base": 60.0})

        assert isinstance(strategy, FPStrategy)
        assert strategy.config.f_base == 60.0

    def test_create_island_with_relay(self):
        relay = MagicMock()
        factory = StrategyFactory(relay=relay)
        strategy = factory.create(StrategyType.ISLAND, {"sync_timeout": 30})

        assert isinstance(strategy, IslandModeStrategy)
        assert strategy.config.sync_timeout == 30

    def test_create_island_without_relay(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.ISLAND, {})

        assert strategy is None

    def test_create_bypass(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.BYPASS, {})

        assert isinstance(strategy, BypassStrategy)

    def test_create_stop(self):
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.STOP, {})

        assert isinstance(strategy, StopStrategy)

    def test_extra_keys_filtered(self):
        """ConfigMixin.from_dict 應過濾不存在的 key"""
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.PQ, {"p": 100, "q": 50, "unknown_field": "ignored"})

        assert isinstance(strategy, PQModeStrategy)
        assert strategy.config.p == 100
        assert strategy.config.q == 50

    def test_camel_case_conversion(self):
        """ConfigMixin.from_dict 應支援 camelCase"""
        factory = StrategyFactory()
        strategy = factory.create(StrategyType.PV_SMOOTH, {"rampRate": 15})

        # 需要 pv_service 才會成功
        pv_service = MagicMock()
        factory_with_svc = StrategyFactory(pv_service=pv_service)
        strategy = factory_with_svc.create(StrategyType.PV_SMOOTH, {"rampRate": 15})

        assert isinstance(strategy, PVSmoothStrategy)
        assert strategy.config.ramp_rate == 15
