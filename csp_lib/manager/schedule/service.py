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
from zoneinfo import ZoneInfo

from csp_lib.controller.system.schedule_mode import ScheduleModeController
from csp_lib.core import AsyncLifecycleMixin, get_logger

from .config import ScheduleServiceConfig
from .factory import StrategyFactory
from .repository import ScheduleRepository
from .schema import ScheduleRule

logger = get_logger(__name__)


class ScheduleService(AsyncLifecycleMixin):
    """
    排程服務

    週期性從 Repository 查詢匹配的排程規則，透過 Factory 建立策略，
    並透過 ScheduleModeController 走 ModeManager 正規路徑進行策略切換。

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
    ) -> None:
        """
        初始化排程服務

        Args:
            config: 服務配置
            repository: 排程規則資料存取層
            factory: 策略工廠
            mode_controller: 排程模式控制器（實作 ScheduleModeController Protocol）
        """
        self._config = config
        self._repository = repository
        self._factory = factory
        self._mode_controller = mode_controller

        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._current_rule_key: str | None = None

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
        """週期輪詢主迴圈"""
        while not self._stop_event.is_set():
            try:
                await self._poll_once()
            except Exception:
                logger.opt(exception=True).warning("ScheduleService: 輪詢失敗")

            # 等待下次輪詢或被停止
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.poll_interval)
                break  # stop_event 被設置
            except asyncio.TimeoutError:
                pass  # 正常週期到達

    async def _poll_once(self) -> None:
        """執行一次輪詢"""
        tz = ZoneInfo(self._config.timezone_name)
        now = datetime.now(tz)

        rules = await self._repository.find_active_rules(self._config.site_id, now)

        if not rules:
            # 無匹配規則
            if self._current_rule_key is not None:
                logger.info("ScheduleService: 無匹配規則，停用排程模式")
                await self._mode_controller.deactivate_schedule_mode()
                self._current_rule_key = None
            return

        # 取最高優先級規則
        winning_rule = rules[0]
        rule_key = self._make_rule_key(winning_rule)

        # 相同規則不重複切換
        if rule_key == self._current_rule_key:
            return

        # 建立新策略
        strategy = self._factory.create(winning_rule.strategy_type, winning_rule.strategy_config)
        if strategy is None:
            logger.warning(f"ScheduleService: 無法建立策略 {winning_rule.strategy_type.value}，保持現狀")
            return

        logger.info(f"ScheduleService: 切換策略 → {winning_rule.name} ({winning_rule.strategy_type.value})")
        await self._mode_controller.activate_schedule_mode(
            strategy,
            description=f"{winning_rule.name} ({winning_rule.strategy_type.value})",
        )
        self._current_rule_key = rule_key

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
