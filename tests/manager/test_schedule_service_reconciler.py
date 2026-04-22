# =============== Manager Schedule Tests - Reconciler Protocol 契約 ===============
#
# 驗證 ScheduleService 實作 Reconciler Protocol（Wave 2c-F）：
# - name / status / reconcile_once 契約完整
# - reconcile_once 不 raise（non-cancel Exception 吞入 status.last_error）
# - status.detail 記錄 diagnostic metadata（rules_matched / action / rule_name 等）
# - run_count 遞增
# - CancelledError 仍向上傳播

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.core import Reconciler, ReconcilerStatus
from csp_lib.manager.schedule import (
    ScheduleRule,
    ScheduleService,
    ScheduleServiceConfig,
    ScheduleType,
    StrategyFactory,
    StrategyType,
)


def _make_config(site_id: str = "site_test") -> ScheduleServiceConfig:
    return ScheduleServiceConfig(site_id=site_id, poll_interval=0.1, timezone_name="UTC")


def _make_rule(name: str = "rule1", priority: int = 100) -> ScheduleRule:
    return ScheduleRule(
        name=name,
        site_id="site_test",
        schedule_type=ScheduleType.DAILY,
        strategy_type=StrategyType.PQ,
        strategy_config={"p_ref_kw": 100.0, "q_ref_kvar": 50.0},
        start_time="00:00",
        end_time="23:59",
        priority=priority,
        enabled=True,
    )


def _make_service(
    *,
    rules: list[ScheduleRule] | None = None,
    create_returns: object | None = None,
) -> tuple[ScheduleService, MagicMock, AsyncMock]:
    """Factory 回傳 (service, repo, mode_controller)。"""
    repo = MagicMock()
    repo.find_active_rules = AsyncMock(return_value=rules or [])
    factory = MagicMock(spec=StrategyFactory)
    # create 預設回一個非 None 物件，讓 activate_schedule_mode 被呼叫
    factory.create = MagicMock(return_value=create_returns if create_returns is not None else MagicMock())
    mode_ctrl = AsyncMock()
    service = ScheduleService(_make_config(), repo, factory, mode_ctrl)
    return service, repo, mode_ctrl


class TestScheduleServiceImplementsReconciler:
    """ScheduleService 結構性滿足 Reconciler Protocol。"""

    def test_implements_reconciler_protocol(self):
        service, _, _ = _make_service()
        assert isinstance(service, Reconciler)

    def test_name_reflects_site_id(self):
        service, _, _ = _make_service()
        assert service.name == "schedule:site_test"

    def test_initial_status(self):
        """未跑 reconcile 前 status 為 empty snapshot。"""
        service, _, _ = _make_service()
        status = service.status
        assert isinstance(status, ReconcilerStatus)
        assert status.name == "schedule:site_test"
        assert status.run_count == 0
        assert status.last_error is None
        assert status.healthy is True


class TestReconcileOnceDetailMetadata:
    """reconcile_once 寫入 detail diagnostic metadata。"""

    async def test_no_match_records_action(self):
        service, _, _ = _make_service(rules=[])
        status = await service.reconcile_once()
        assert status.detail["rules_matched"] == 0
        assert status.detail["action"] == "no_match"
        assert status.run_count == 1
        assert status.healthy is True

    async def test_switched_records_action_and_rule(self):
        rule = _make_rule("peak_hours")
        service, _, mode_ctrl = _make_service(rules=[rule])

        status = await service.reconcile_once()

        assert status.detail["rules_matched"] == 1
        assert status.detail["action"] == "switched"
        assert status.detail["rule_name"] == "peak_hours"
        assert "rule_key" in status.detail
        mode_ctrl.activate_schedule_mode.assert_awaited_once()

    async def test_unchanged_when_same_rule(self):
        rule = _make_rule("peak_hours")
        service, _, mode_ctrl = _make_service(rules=[rule])

        # 第一次 switch
        await service.reconcile_once()
        mode_ctrl.activate_schedule_mode.reset_mock()

        # 第二次同規則 → unchanged
        status = await service.reconcile_once()
        assert status.detail["action"] == "unchanged"
        mode_ctrl.activate_schedule_mode.assert_not_awaited()

    async def test_deactivated_when_match_disappears(self):
        """從有匹配到無匹配 → deactivate。"""
        rule = _make_rule("peak_hours")
        service, repo, mode_ctrl = _make_service(rules=[rule])

        await service.reconcile_once()  # 進入 schedule mode
        mode_ctrl.activate_schedule_mode.reset_mock()

        # 下一次無匹配
        repo.find_active_rules = AsyncMock(return_value=[])
        status = await service.reconcile_once()

        assert status.detail["action"] == "deactivated"
        mode_ctrl.deactivate_schedule_mode.assert_awaited_once()

    async def test_factory_failed_records_action(self):
        rule = _make_rule("bad_rule")
        # factory.create 回 None 表示無法建立策略
        service, _, mode_ctrl = _make_service(rules=[rule], create_returns=None)
        # create_returns=None 會讓 factory.create 回 MagicMock（非 None），所以
        # 手動覆寫
        service._factory.create = MagicMock(return_value=None)  # type: ignore[attr-defined]

        status = await service.reconcile_once()

        assert status.detail["action"] == "factory_failed"
        mode_ctrl.activate_schedule_mode.assert_not_awaited()


class TestReconcileOnceErrorHandling:
    """reconcile_once 吞 non-cancel Exception、傳播 CancelledError。"""

    async def test_repository_error_recorded_not_raised(self):
        service, repo, _ = _make_service()
        repo.find_active_rules = AsyncMock(side_effect=RuntimeError("DB down"))

        # 不 raise
        status = await service.reconcile_once()

        assert status.last_error is not None
        assert "DB down" in status.last_error
        assert status.healthy is False
        assert status.run_count == 1

    async def test_cancelled_error_propagates(self):
        service, repo, _ = _make_service()
        repo.find_active_rules = AsyncMock(side_effect=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await service.reconcile_once()

    async def test_run_count_increments_across_runs(self):
        service, _, _ = _make_service(rules=[])
        await service.reconcile_once()
        await service.reconcile_once()
        await service.reconcile_once()
        assert service.status.run_count == 3
