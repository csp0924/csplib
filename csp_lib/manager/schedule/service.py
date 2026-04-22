# =============== Manager Schedule - Service ===============
#
# 排程服務
#
# 週期性輪詢排程規則並驅動策略切換：
#   - ScheduleService(AsyncLifecycleMixin): 週期輪詢迴圈
#   - 從 Repository 取得匹配規則 → Factory 建立策略 → 更新 ScheduleStrategy

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from csp_lib.controller.system.schedule_mode import ScheduleModeController
from csp_lib.core import AsyncLifecycleMixin, ReconcilerMixin, get_logger

from .config import ScheduleServiceConfig
from .factory import StrategyFactory
from .repository import ScheduleRepository
from .schema import ScheduleRule

if TYPE_CHECKING:
    from csp_lib.manager.base import LeaderGate

logger = get_logger(__name__)


class ScheduleService(ReconcilerMixin, AsyncLifecycleMixin):
    """
    排程服務

    週期性從 Repository 查詢匹配的排程規則，透過 Factory 建立策略，
    並透過 ScheduleModeController 走 ModeManager 正規路徑進行策略切換。

    實作 :class:`~csp_lib.core.Reconciler` Protocol（透過
    :class:`~csp_lib.core.ReconcilerMixin`），排程輪詢本質即 reconcile loop：
    每次 ``reconcile_once()`` 從 repository 取得 desired schedule rule，
    與 ``current_rule_key`` 比對決定是否切換策略。可納入
    ``SystemController.describe()`` 聚合 Reconciler status。

    生命週期：
        - ``async with service:`` → 啟動/停止輪詢迴圈
        - _on_start: 建立背景 Task
        - _on_stop: 設定 stop_event 並等待 Task 完成

    Usage:
        service = ScheduleService(
            config=ScheduleServiceConfig(site_id="site_001"),
            repository=mongo_repo,
            factory=StrategyFactory(pv_service=pv_svc),
            mode_controller=system_controller,  # 實作 ScheduleModeController
        )
        async with service:
            await asyncio.Event().wait()
    """

    def __init__(
        self,
        config: ScheduleServiceConfig,
        repository: ScheduleRepository,
        factory: StrategyFactory,
        mode_controller: ScheduleModeController,
        *,
        leader_gate: LeaderGate | None = None,
    ) -> None:
        """
        初始化排程服務

        Args:
            config: 服務配置
            repository: 排程規則資料存取層
            factory: 策略工廠
            mode_controller: 排程模式控制器（實作 ScheduleModeController Protocol）
            leader_gate: Leader 閘門（keyword-only，可選）。非 leader 時
                輪詢迴圈會跳過 ``_poll_once()``（不查 repository、不觸發
                模式切換），但迴圈本身仍運作以便節點升格後立即恢復。
        """
        self._config = config
        self._repository = repository
        self._factory = factory
        self._mode_controller = mode_controller
        self._leader_gate = leader_gate

        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._current_rule_key: str | None = None

        # Reconciler Protocol：name 以 site_id 為後綴便於多站部署聚合 status
        self._init_reconciler(f"schedule:{config.site_id}")

    @property
    def current_rule_key(self) -> str | None:
        """當前規則的唯一識別鍵"""
        return self._current_rule_key

    # ---- 生命週期 ----

    async def _on_start(self) -> None:
        """啟動輪詢迴圈"""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"ScheduleService started (site={self._config.site_id}, interval={self._config.poll_interval}s)")

    async def _on_stop(self) -> None:
        """停止輪詢迴圈"""
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None
        logger.info("ScheduleService stopped")

    # ---- 輪詢迴圈 ----

    async def _poll_loop(self) -> None:
        """週期輪詢主迴圈 — 透過 ``_poll_once()`` 執行單次收斂。

        ``_poll_once`` 委派至 ``ReconcilerMixin.reconcile_once``，後者吞
        non-cancel Exception 並記到 ``self.status.last_error``；迴圈本身
        不需再包 try/except。保留 ``_poll_once`` 當作測試 hook point
        與向後相容 alias。
        """
        while not self._stop_event.is_set():
            # Leader 閘門：非 leader 跳過本輪輪詢（仍維持迴圈以便升格後恢復）
            if self._leader_gate is None or self._leader_gate.is_leader:
                await self._poll_once()
            else:
                logger.trace("ScheduleService: skip poll (not leader)")

            # 等待下次輪詢或被停止
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.poll_interval)
                break  # stop_event 被設置
            except asyncio.TimeoutError:
                pass  # 正常週期到達

    async def _reconcile_work(self, detail: dict[str, Any]) -> None:
        """執行一次排程 reconcile（desired schedule rule → current strategy）。

        把 diagnostic metadata 寫入 ``detail``，供 ``status.detail`` 觀測：
        - ``rules_matched``: 本輪匹配規則數
        - ``action``: "no_match" / "deactivated" / "unchanged" / "switched" / "factory_failed"
        - ``rule_name`` / ``rule_key``: 匹配或切換的規則資訊
        """
        tz = ZoneInfo(self._config.timezone_name)
        now = datetime.now(tz)

        rules = await self._repository.find_active_rules(self._config.site_id, now)
        detail["rules_matched"] = len(rules)

        if not rules:
            # 無匹配規則
            if self._current_rule_key is not None:
                logger.info("ScheduleService: 無匹配規則，停用排程模式")
                await self._mode_controller.deactivate_schedule_mode()
                self._current_rule_key = None
                detail["action"] = "deactivated"
            else:
                detail["action"] = "no_match"
            return

        # 取最高優先級規則
        winning_rule = rules[0]
        rule_key = self._make_rule_key(winning_rule)
        detail["rule_name"] = winning_rule.name

        # 相同規則不重複切換
        if rule_key == self._current_rule_key:
            detail["action"] = "unchanged"
            return

        # 建立新策略
        strategy = self._factory.create(winning_rule.strategy_type, winning_rule.strategy_config)
        if strategy is None:
            logger.warning(f"ScheduleService: 無法建立策略 {winning_rule.strategy_type.value}，保持現狀")
            detail["action"] = "factory_failed"
            return

        logger.info(f"ScheduleService: 切換策略 → {winning_rule.name} ({winning_rule.strategy_type.value})")
        await self._mode_controller.activate_schedule_mode(
            strategy,
            description=f"{winning_rule.name} ({winning_rule.strategy_type.value})",
        )
        self._current_rule_key = rule_key
        detail["action"] = "switched"
        detail["rule_key"] = rule_key

    # Backward-compat alias：既有測試 / caller 仍可直呼 _poll_once
    async def _poll_once(self) -> None:
        """執行一次輪詢（委派至 ``reconcile_once()``；保留為 backward-compat alias）。"""
        await self.reconcile_once()

    @staticmethod
    def _make_rule_key(rule: ScheduleRule) -> str:
        """
        生成規則的唯一識別鍵

        用於偵測規則是否變更，避免不必要的策略切換。

        Args:
            rule: 排程規則

        Returns:
            str: 複合唯一鍵
        """
        config_json = json.dumps(rule.strategy_config, sort_keys=True, default=str)
        return f"{rule.name}|{rule.schedule_type.value}|{rule.priority}|{config_json}"


__all__ = [
    "ScheduleService",
]
