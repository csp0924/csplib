# =============== Strategies Tests ===============
#
# 測試 PQModeStrategy, PVSmoothStrategy, StopStrategy, ScheduleStrategy

from unittest.mock import MagicMock

import pytest

from csp_lib.controller.core import (
    Command,
    ExecutionMode,
    StrategyContext,
)
from csp_lib.controller.services import PVDataService
from csp_lib.controller.strategies import (
    PQModeConfig,
    PQModeStrategy,
    PVSmoothConfig,
    PVSmoothStrategy,
    ScheduleStrategy,
    StopStrategy,
)

# =============== StopStrategy Tests ===============


class TestStopStrategy:
    """StopStrategy 停止策略測試"""

    def test_execute_returns_zero_command(self):
        """execute 應返回 (0, 0)"""
        strategy = StopStrategy()
        ctx = StrategyContext()

        cmd = strategy.execute(ctx)

        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0

    def test_execution_config_is_periodic(self):
        """執行模式應為 PERIODIC"""
        strategy = StopStrategy()
        assert strategy.execution_config.mode == ExecutionMode.PERIODIC
        assert strategy.execution_config.interval_seconds == 1


# =============== PQModeStrategy Tests ===============


class TestPQModeStrategy:
    """PQModeStrategy 定功率策略測試"""

    def test_execute_returns_config_values(self):
        """execute 應返回配置值"""
        config = PQModeConfig(p=500.0, q=100.0)
        strategy = PQModeStrategy(config)
        ctx = StrategyContext()

        cmd = strategy.execute(ctx)

        assert cmd.p_target == 500.0
        assert cmd.q_target == 100.0

    def test_default_config(self):
        """預設配置應為 (0, 0)"""
        strategy = PQModeStrategy()
        ctx = StrategyContext()

        cmd = strategy.execute(ctx)

        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0

    def test_update_config(self):
        """update_config 應更新策略配置"""
        strategy = PQModeStrategy(PQModeConfig(p=100.0))
        strategy.update_config(PQModeConfig(p=200.0, q=50.0))

        ctx = StrategyContext()
        cmd = strategy.execute(ctx)

        assert cmd.p_target == 200.0
        assert cmd.q_target == 50.0

    def test_execution_config_is_periodic(self):
        """執行模式應為 PERIODIC (1秒)"""
        strategy = PQModeStrategy()
        assert strategy.execution_config.mode == ExecutionMode.PERIODIC
        assert strategy.execution_config.interval_seconds == 1

    def test_str_representation(self):
        """__str__ 應包含 P/Q 值"""
        strategy = PQModeStrategy(PQModeConfig(p=100.0, q=50.0))
        assert "100" in str(strategy)
        assert "50" in str(strategy)


# =============== PVSmoothStrategy Tests ===============


class TestPVSmoothStrategy:
    """PVSmoothStrategy PV 平滑策略測試"""

    def test_execute_without_pv_service_returns_zero(self):
        """未設定 PVDataService 時應返回 0"""
        strategy = PVSmoothStrategy()
        ctx = StrategyContext()

        cmd = strategy.execute(ctx)

        assert cmd.p_target == 0.0

    def test_execute_with_insufficient_history_returns_zero(self):
        """歷史資料不足時應返回 0"""
        pv_service = PVDataService(max_history=10)
        config = PVSmoothConfig(min_history=5)
        strategy = PVSmoothStrategy(config=config, pv_service=pv_service)

        # 只加 3 筆，不足 min_history=5
        pv_service.append(100.0)
        pv_service.append(100.0)
        pv_service.append(100.0)

        ctx = StrategyContext()
        cmd = strategy.execute(ctx)

        assert cmd.p_target == 0.0

    def test_execute_with_sufficient_history(self):
        """有足夠歷史資料時應計算平均值"""
        pv_service = PVDataService(max_history=10)
        config = PVSmoothConfig(
            capacity=1000.0,
            ramp_rate=100.0,  # 100% = 不限制
            pv_loss=0.0,
            min_history=3,
        )
        strategy = PVSmoothStrategy(config=config, pv_service=pv_service)

        # 加入 3 筆：平均 = 300
        pv_service.append(200.0)
        pv_service.append(300.0)
        pv_service.append(400.0)

        ctx = StrategyContext(last_command=Command(p_target=0.0))
        cmd = strategy.execute(ctx)

        assert cmd.p_target == 300.0  # 平均值

    def test_ramp_rate_limits_increase(self):
        """Ramp rate 應限制功率上升速度"""
        pv_service = PVDataService(max_history=10)
        config = PVSmoothConfig(
            capacity=1000.0,
            ramp_rate=10.0,  # 10% = 100kW/週期
            min_history=1,
        )
        strategy = PVSmoothStrategy(config=config, pv_service=pv_service)

        pv_service.append(500.0)  # 目標 500kW

        # 從 0 開始，最多只能增加 100kW
        ctx = StrategyContext(last_command=Command(p_target=0.0))
        cmd = strategy.execute(ctx)

        assert cmd.p_target == 100.0  # 受 ramp rate 限制

    def test_ramp_rate_limits_decrease(self):
        """Ramp rate 應限制功率下降速度"""
        pv_service = PVDataService(max_history=10)
        config = PVSmoothConfig(
            capacity=1000.0,
            ramp_rate=10.0,  # 10% = 100kW/週期
            min_history=1,
        )
        strategy = PVSmoothStrategy(config=config, pv_service=pv_service)

        pv_service.append(100.0)  # 目標 100kW

        # 從 500 開始，最多只能減少 100kW
        ctx = StrategyContext(last_command=Command(p_target=500.0))
        cmd = strategy.execute(ctx)

        assert cmd.p_target == 400.0  # 受 ramp rate 限制

    def test_pv_loss_subtracted(self):
        """應扣除 pv_loss"""
        pv_service = PVDataService(max_history=10)
        config = PVSmoothConfig(
            capacity=1000.0,
            ramp_rate=100.0,
            pv_loss=50.0,  # 扣除 50kW
            min_history=1,
        )
        strategy = PVSmoothStrategy(config=config, pv_service=pv_service)

        pv_service.append(200.0)

        ctx = StrategyContext(last_command=Command(p_target=0.0))
        cmd = strategy.execute(ctx)

        assert cmd.p_target == 150.0  # 200 - 50

    def test_pv_loss_does_not_go_negative(self):
        """pv_loss 扣除後不應為負"""
        pv_service = PVDataService(max_history=10)
        config = PVSmoothConfig(
            capacity=1000.0,
            ramp_rate=100.0,
            pv_loss=100.0,  # 扣除 100kW
            min_history=1,
        )
        strategy = PVSmoothStrategy(config=config, pv_service=pv_service)

        pv_service.append(50.0)  # 低於 pv_loss

        ctx = StrategyContext(last_command=Command(p_target=0.0))
        cmd = strategy.execute(ctx)

        assert cmd.p_target == 0.0  # max(50-100, 0) = 0

    def test_set_pv_service(self):
        """set_pv_service 可動態設定"""
        strategy = PVSmoothStrategy()
        assert strategy.pv_service is None

        pv_service = PVDataService()
        strategy.set_pv_service(pv_service)

        assert strategy.pv_service is pv_service


# =============== ScheduleStrategy Tests ===============


class TestScheduleStrategy:
    """ScheduleStrategy 排程策略測試"""

    def test_default_uses_stop_strategy(self):
        """無排程時應使用 StopStrategy"""
        schedule = ScheduleStrategy()
        ctx = StrategyContext()

        cmd = schedule.execute(ctx)

        assert cmd.p_target == 0.0
        assert cmd.q_target == 0.0

    @pytest.mark.asyncio
    async def test_update_schedule_changes_strategy(self):
        """update_schedule 應切換內部策略"""
        schedule = ScheduleStrategy()
        pq_strategy = PQModeStrategy(PQModeConfig(p=100.0, q=50.0))

        await schedule.update_schedule(pq_strategy)

        ctx = StrategyContext()
        cmd = schedule.execute(ctx)

        assert cmd.p_target == 100.0
        assert cmd.q_target == 50.0

    @pytest.mark.asyncio
    async def test_update_schedule_to_none_uses_fallback(self):
        """設為 None 應回到 fallback"""
        schedule = ScheduleStrategy()
        pq_strategy = PQModeStrategy(PQModeConfig(p=100.0))

        await schedule.update_schedule(pq_strategy)
        await schedule.update_schedule(None)

        ctx = StrategyContext()
        cmd = schedule.execute(ctx)

        assert cmd.p_target == 0.0  # StopStrategy

    @pytest.mark.asyncio
    async def test_has_schedule_property(self):
        """has_schedule 應正確反映狀態"""
        schedule = ScheduleStrategy()
        assert schedule.has_schedule is False

        await schedule.update_schedule(PQModeStrategy())
        assert schedule.has_schedule is True

        await schedule.update_schedule(None)
        assert schedule.has_schedule is False

    @pytest.mark.asyncio
    async def test_lifecycle_hooks_called(self):
        """切換策略時應呼叫生命週期 hooks"""
        from unittest.mock import AsyncMock

        schedule = ScheduleStrategy()

        mock_strategy = MagicMock()
        mock_strategy.on_activate = AsyncMock()
        mock_strategy.on_deactivate = AsyncMock()

        await schedule.update_schedule(mock_strategy)
        mock_strategy.on_activate.assert_awaited_once()

        await schedule.update_schedule(None)
        mock_strategy.on_deactivate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execution_config_delegates_to_current(self):
        """execution_config 應來自當前策略"""
        schedule = ScheduleStrategy()

        # 預設使用 StopStrategy (interval=1)
        assert schedule.execution_config.interval_seconds == 1

        # 切換到 PVSmooth (interval=900)
        pv_strategy = PVSmoothStrategy(interval_seconds=900)
        await schedule.update_schedule(pv_strategy)

        assert schedule.execution_config.interval_seconds == 900
