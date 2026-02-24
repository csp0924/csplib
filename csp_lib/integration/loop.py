# =============== Integration - Grid Control Loop ===============
#
# 完整控制迴圈編排器
#
# 組合所有整合元件，提供 Equipment → Controller 的完整控制迴圈：
#   - ContextBuilder: 設備值 → StrategyContext
#   - StrategyExecutor: 策略執行
#   - CommandRouter: Command → 設備寫入
#   - DeviceDataFeed: 事件 → PVDataService（可選）
#
# 繼承 AsyncLifecycleMixin，支援 async with 使用

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from csp_lib.controller.core import SystemBase
from csp_lib.controller.executor import StrategyExecutor
from csp_lib.controller.services import PVDataService
from csp_lib.core import AsyncLifecycleMixin, get_logger

from .command_router import CommandRouter
from .context_builder import ContextBuilder
from .data_feed import DeviceDataFeed
from .registry import DeviceRegistry
from .schema import CommandMapping, ContextMapping, DataFeedMapping

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy

logger = get_logger("csp_lib.integration.loop")


@dataclass
class GridControlLoopConfig:
    """
    GridControlLoop 配置

    Attributes:
        context_mappings: 設備點位 → StrategyContext 的映射列表
        command_mappings: Command 欄位 → 設備寫入的映射列表
        system_base: 系統基準值（可選）
        data_feed_mapping: PV 資料餵入映射（可選，設定時自動建立 PVDataService）
        pv_max_history: PVDataService 最大歷史記錄數
    """

    context_mappings: list[ContextMapping] = field(default_factory=list)
    command_mappings: list[CommandMapping] = field(default_factory=list)
    system_base: SystemBase | None = None
    data_feed_mapping: DataFeedMapping | None = None
    pv_max_history: int = 300


class GridControlLoop(AsyncLifecycleMixin):
    """
    完整控制迴圈編排器

    編排 ContextBuilder、CommandRouter、DeviceDataFeed 與 StrategyExecutor，
    提供從設備讀取到策略執行再到設備寫入的完整控制迴圈。

    使用範例::

        loop = GridControlLoop(registry, config)
        await loop.set_strategy(my_strategy)
        async with loop:
            # 自動執行：
            #   ContextBuilder 讀取設備值 → StrategyContext
            #   StrategyExecutor 週期性執行策略
            #   CommandRouter 將 Command 寫入設備
            #   DeviceDataFeed 將 PV 功率餵入 PVDataService
            await asyncio.Event().wait()

    生命週期：
        - ``async with loop:`` → 呼叫 _on_start() / _on_stop()
        - 啟動時：attach data feed + 建立 executor 背景任務
        - 停止時：stop executor + await 任務完成 + detach data feed
    """

    def __init__(self, registry: DeviceRegistry, config: GridControlLoopConfig) -> None:
        """
        初始化控制迴圈

        Args:
            registry: 設備查詢索引
            config: 控制迴圈配置
        """
        self._registry = registry
        self._config = config

        # 若有設定 DataFeedMapping，自動建立 PVDataService 與 DeviceDataFeed
        self._pv_service: PVDataService | None = None
        self._data_feed: DeviceDataFeed | None = None
        if config.data_feed_mapping is not None:
            self._pv_service = PVDataService(max_history=config.pv_max_history)
            self._data_feed = DeviceDataFeed(registry, config.data_feed_mapping, self._pv_service)

        # 建立 ContextBuilder（設備值 → StrategyContext）
        self._context_builder = ContextBuilder(registry, config.context_mappings, system_base=config.system_base)

        # 建立 CommandRouter（Command → 設備寫入）
        self._command_router = CommandRouter(registry, config.command_mappings)

        # 建立 StrategyExecutor，串接 context_provider 與 on_command
        self._executor = StrategyExecutor(
            context_provider=self._context_builder.build,
            on_command=self._command_router.route,
        )

        self._run_task: asyncio.Task[None] | None = None  # executor.run() 背景任務

    # ---- 策略委派 ----

    async def set_strategy(self, strategy: Strategy | None) -> None:
        """
        設定 / 切換策略

        委派給內部的 StrategyExecutor，自動處理 on_activate / on_deactivate。

        Args:
            strategy: 新策略，None 表示清除當前策略
        """
        await self._executor.set_strategy(strategy)

    def trigger(self) -> None:
        """手動觸發策略執行（適用於 TRIGGERED / HYBRID 模式）"""
        self._executor.trigger()

    # ---- 生命週期 ----

    async def _on_start(self) -> None:
        """啟動控制迴圈：attach data feed + 建立 executor 背景任務"""
        if self._data_feed is not None:
            self._data_feed.attach()
        self._run_task = asyncio.create_task(self._executor.run())
        logger.info("GridControlLoop started.")

    async def _on_stop(self) -> None:
        """停止控制迴圈：stop executor + await 任務完成 + detach data feed"""
        self._executor.stop()
        if self._run_task is not None:
            await self._run_task
            self._run_task = None
        if self._data_feed is not None:
            self._data_feed.detach()
        logger.info("GridControlLoop stopped.")

    # ---- 唯讀屬性 ----

    @property
    def registry(self) -> DeviceRegistry:
        """設備查詢索引"""
        return self._registry

    @property
    def executor(self) -> StrategyExecutor:
        """內部的策略執行器"""
        return self._executor

    @property
    def pv_service(self) -> PVDataService | None:
        """PV 資料服務（未設定 DataFeedMapping 時為 None）"""
        return self._pv_service

    @property
    def is_running(self) -> bool:
        """控制迴圈是否正在執行"""
        return self._run_task is not None and not self._run_task.done()
