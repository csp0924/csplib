# =============== Manager Schedule Tests - Service ===============
#
# ScheduleService 單元測試
#
# 測試覆蓋：
# - reconcile_once 有/無匹配規則
# - 同規則不重複切換
# - Factory 建立失敗保持現狀
# - 生命週期 start/stop
# - 錯誤恢復
# - Config 驗證

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.manager.schedule.config import ScheduleServiceConfig
from csp_lib.manager.schedule.factory import StrategyFactory
from csp_lib.manager.schedule.schema import ScheduleRule, ScheduleType, StrategyType
from csp_lib.manager.schedule.service import ScheduleService


def _make_config(**overrides) -> ScheduleServiceConfig:
    defaults = {"site_id": "site_001", "poll_interval": 30.0}
    defaults.update(overrides)
    return ScheduleServiceConfig(**defaults)


def _make_rule(
    name: str = "rule",
    priority: int = 10,
    strategy_type: StrategyType = StrategyType.PQ,
    strategy_config: dict | None = None,
) -> ScheduleRule:
    return ScheduleRule(
        name=name,
        site_id="site_001",
        schedule_type=ScheduleType.DAILY,
        strategy_type=strategy_type,
        strategy_config=strategy_config or {"p": 100},
        start_time="00:00",
        end_time="23:59",
        priority=priority,
    )


class TestScheduleServiceConfig:
    """ScheduleServiceConfig 驗證測試"""

    def test_valid_config(self):
        config = ScheduleServiceConfig(site_id="site_001", poll_interval=10.0)
        assert config.site_id == "site_001"
        assert config.poll_interval == 10.0
        assert config.timezone_name == "Asia/Taipei"

    def test_empty_site_id(self):
        with pytest.raises(ValueError, match="site_id"):
            ScheduleServiceConfig(site_id="", poll_interval=10.0)

    def test_zero_poll_interval(self):
        with pytest.raises(ValueError, match="poll_interval"):
            ScheduleServiceConfig(site_id="site_001", poll_interval=0)

    def test_negative_poll_interval(self):
        with pytest.raises(ValueError, match="poll_interval"):
            ScheduleServiceConfig(site_id="site_001", poll_interval=-1)


class TestPollOnce:
    """reconcile_once 測試"""

    @pytest.mark.asyncio
    async def test_matching_rule_switches_strategy(self):
        """有匹配規則時應建立策略並切換"""
        config = _make_config()
        repo = AsyncMock()
        rule = _make_rule()
        repo.find_active_rules = AsyncMock(return_value=[rule])

        mock_strategy = MagicMock()
        factory = MagicMock(spec=StrategyFactory)
        factory.create = MagicMock(return_value=mock_strategy)

        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)
        await service.reconcile_once()

        factory.create.assert_called_once_with(StrategyType.PQ, {"p": 100})
        mode_controller.activate_schedule_mode.assert_called_once()
        call_args = mode_controller.activate_schedule_mode.call_args
        assert call_args.args[0] is mock_strategy
        assert service.current_rule_key is not None

    @pytest.mark.asyncio
    async def test_no_rules_switches_to_fallback(self):
        """無匹配規則且之前有規則時應停用排程模式"""
        config = _make_config()
        repo = AsyncMock()
        repo.find_active_rules = AsyncMock(return_value=[])

        factory = MagicMock(spec=StrategyFactory)
        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)
        # 模擬之前有活躍規則
        service._current_rule_key = "previous_key"

        await service.reconcile_once()

        mode_controller.deactivate_schedule_mode.assert_called_once()
        assert service.current_rule_key is None

    @pytest.mark.asyncio
    async def test_no_rules_no_previous_does_nothing(self):
        """無匹配規則且之前也無規則時不做切換"""
        config = _make_config()
        repo = AsyncMock()
        repo.find_active_rules = AsyncMock(return_value=[])

        factory = MagicMock(spec=StrategyFactory)
        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)
        await service.reconcile_once()

        mode_controller.activate_schedule_mode.assert_not_called()
        mode_controller.deactivate_schedule_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_rule_dedup(self):
        """相同規則不重複切換"""
        config = _make_config()
        repo = AsyncMock()
        rule = _make_rule()
        repo.find_active_rules = AsyncMock(return_value=[rule])

        mock_strategy = MagicMock()
        factory = MagicMock(spec=StrategyFactory)
        factory.create = MagicMock(return_value=mock_strategy)

        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)

        # First call - should switch
        await service.reconcile_once()
        assert mode_controller.activate_schedule_mode.call_count == 1

        # Second call - same rule, should skip
        await service.reconcile_once()
        assert mode_controller.activate_schedule_mode.call_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_factory_failure_keeps_current(self):
        """Factory 建立失敗時保持現狀"""
        config = _make_config()
        repo = AsyncMock()
        rule = _make_rule(strategy_type=StrategyType.ISLAND)
        repo.find_active_rules = AsyncMock(return_value=[rule])

        factory = MagicMock(spec=StrategyFactory)
        factory.create = MagicMock(return_value=None)  # 建立失敗

        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)
        service._current_rule_key = "old_key"

        await service.reconcile_once()

        mode_controller.activate_schedule_mode.assert_not_called()
        assert service.current_rule_key == "old_key"  # 保持不變

    @pytest.mark.asyncio
    async def test_highest_priority_wins(self):
        """最高優先級規則應勝出"""
        config = _make_config()
        repo = AsyncMock()
        rules = [
            _make_rule(name="high", priority=10, strategy_type=StrategyType.PQ, strategy_config={"p": 200}),
            _make_rule(name="low", priority=1, strategy_type=StrategyType.STOP),
        ]
        repo.find_active_rules = AsyncMock(return_value=rules)

        mock_strategy = MagicMock()
        factory = MagicMock(spec=StrategyFactory)
        factory.create = MagicMock(return_value=mock_strategy)

        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)
        await service.reconcile_once()

        factory.create.assert_called_once_with(StrategyType.PQ, {"p": 200})


class TestLifecycle:
    """生命週期測試"""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """start/stop 應正確管理背景 Task"""
        config = _make_config()
        repo = AsyncMock()
        repo.find_active_rules = AsyncMock(return_value=[])

        factory = MagicMock(spec=StrategyFactory)
        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)

        await service.start()
        assert service._task is not None
        assert not service._task.done()

        await service.stop()
        assert service._task is None

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """async with 應正常運作"""
        config = _make_config()
        repo = AsyncMock()
        repo.find_active_rules = AsyncMock(return_value=[])

        factory = MagicMock(spec=StrategyFactory)
        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)

        async with service:
            assert service._task is not None

        assert service._task is None


class TestMakeRuleKey:
    """_make_rule_key 測試"""

    def test_different_configs_different_keys(self):
        rule1 = _make_rule(strategy_config={"p": 100})
        rule2 = _make_rule(strategy_config={"p": 200})

        key1 = ScheduleService._make_rule_key(rule1)
        key2 = ScheduleService._make_rule_key(rule2)

        assert key1 != key2

    def test_same_config_same_key(self):
        rule1 = _make_rule(strategy_config={"p": 100})
        rule2 = _make_rule(strategy_config={"p": 100})

        key1 = ScheduleService._make_rule_key(rule1)
        key2 = ScheduleService._make_rule_key(rule2)

        assert key1 == key2

    def test_different_names_different_keys(self):
        rule1 = _make_rule(name="rule_a")
        rule2 = _make_rule(name="rule_b")

        key1 = ScheduleService._make_rule_key(rule1)
        key2 = ScheduleService._make_rule_key(rule2)

        assert key1 != key2

    def test_different_priorities_different_keys(self):
        rule1 = _make_rule(priority=1)
        rule2 = _make_rule(priority=10)

        key1 = ScheduleService._make_rule_key(rule1)
        key2 = ScheduleService._make_rule_key(rule2)

        assert key1 != key2


class TestErrorResilience:
    """錯誤恢復測試"""

    @pytest.mark.asyncio
    async def test_reconcile_once_repo_error_recorded_in_status(self):
        """Repository 錯誤由 ReconcilerMixin 吞掉並記到 status.last_error。

        Contract: ``reconcile_once`` non-cancel Exception 吞掉並記 status，
        而非 raise。錯誤由上層透過 ``service.status.last_error`` 觀察。
        """
        config = _make_config()
        repo = AsyncMock()
        repo.find_active_rules = AsyncMock(side_effect=Exception("DB error"))

        factory = MagicMock(spec=StrategyFactory)
        mode_controller = AsyncMock()

        service = ScheduleService(config, repo, factory, mode_controller)

        # reconcile_once 不 raise；錯誤寫入 status
        await service.reconcile_once()

        assert service.status.last_error is not None
        assert "DB error" in service.status.last_error
        assert service.status.healthy is False
        assert service.status.run_count == 1
