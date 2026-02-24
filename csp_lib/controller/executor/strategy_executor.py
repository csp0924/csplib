# =============== Strategy Executor ===============
#
# 策略執行器：管理策略的執行生命週期
# - 處理週期執行 (PERIODIC)
# - 支援手動觸發 (TRIGGERED)
# - 混合模式 (HYBRID: 週期 + 可提前觸發)

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from csp_lib.controller.core import Command, ExecutionMode, Strategy, StrategyContext
from csp_lib.core import get_logger

if TYPE_CHECKING:
    from .compute_offloader import ComputeOffloader

logger = get_logger(__name__)


class StrategyExecutor:
    """
    策略執行器

    管理策略的執行生命週期，根據策略的 ExecutionConfig 決定執行方式：
    - PERIODIC: 固定週期執行
    - TRIGGERED: 等待外部觸發
    - HYBRID: 週期執行，但可被 trigger() 提前觸發

    Usage:
        executor = StrategyExecutor(context_provider=get_context)
        executor.set_strategy(pq_strategy)

        # 啟動執行迴圈
        await executor.run()

        # 手動觸發 (適用於 TRIGGERED / HYBRID 模式)
        executor.trigger()

    Attributes:
        last_command: 最後一次執行的命令
    """

    def __init__(
        self,
        context_provider: Callable[[], StrategyContext],
        on_command: Optional[Callable[[Command], Awaitable[None]]] = None,
        offloader: ComputeOffloader | None = None,
    ):
        """
        初始化執行器

        Args:
            context_provider: 提供 StrategyContext 的 callable
            on_command: 命令產生後的回呼 (可選，用於將命令發送給 GridController)
            offloader: 計算卸載器 (可選，將同步策略卸載到執行緒池)
        """
        self._context_provider = context_provider
        self._on_command = on_command
        self._offloader = offloader

        self._strategy: Optional[Strategy] = None
        self._last_command = Command()
        self._trigger_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._is_running = False

    @property
    def last_command(self) -> Command:
        """最後一次執行的命令"""
        return self._last_command

    @property
    def current_strategy(self) -> Optional[Strategy]:
        """當前策略"""
        return self._strategy

    @property
    def is_running(self) -> bool:
        """是否正在執行"""
        return self._is_running

    def set_context_provider(self, provider: Callable[[], StrategyContext]) -> None:
        """設定 context provider（供叢集模式切換用）"""
        self._context_provider = provider

    def set_on_command(self, callback: Callable[[Command], Awaitable[None]] | None) -> None:
        """設定 on_command 回呼（供叢集模式切換用）"""
        self._on_command = callback

    async def set_strategy(self, strategy: Optional[Strategy]) -> None:
        """
        設定/切換策略

        會自動呼叫舊策略的 on_deactivate() 和新策略的 on_activate()
        注意：會等待 lifecycle 方法完成

        Args:
            strategy: 新策略，None 表示停止策略
        """
        if self._strategy is not None:
            logger.info(f"停用策略: {self._strategy}")
            await self._strategy.on_deactivate()

        self._strategy = strategy

        if self._strategy is not None:
            logger.info(f"啟用策略: {self._strategy}")
            await self._strategy.on_activate()

    def trigger(self) -> None:
        """
        手動觸發執行

        適用於 TRIGGERED 和 HYBRID 模式。
        對於 PERIODIC 模式無效 (會在下次週期執行)。
        """
        self._trigger_event.set()
        logger.debug("策略執行已觸發")

    async def run(self) -> None:
        """
        主執行迴圈

        根據策略的 ExecutionConfig 決定執行方式。
        呼叫 stop() 可停止迴圈。
        """

        self._stop_event.clear()
        self._is_running = True
        logger.info("策略執行器已啟動")

        try:
            while not self._stop_event.is_set():
                if self._strategy is None:
                    await asyncio.sleep(0.1)
                    continue

                config = self._strategy.execution_config

                # 根據執行模式決定等待方式
                await self._wait_for_execution(config)

                if self._stop_event.is_set():
                    break

                # 執行策略
                await self._execute_strategy()

        except asyncio.CancelledError:
            logger.info("策略執行器被取消")
        finally:
            self._is_running = False
            logger.info("策略執行器已停止")

    def stop(self) -> None:
        """停止執行迴圈"""
        self._stop_event.set()
        self._trigger_event.set()  # 解除等待
        if self._offloader is not None:
            self._offloader.shutdown()

    async def execute_once(self) -> Command:
        """
        執行一次策略 (不考慮執行模式)

        用於測試或手動控制。

        Returns:
            Command: 策略輸出
        """
        if self._strategy is None:
            return Command()

        return await self._execute_strategy()

    async def _wait_for_execution(self, config) -> None:
        """根據執行模式等待執行時機"""

        if config.mode == ExecutionMode.TRIGGERED:
            # 僅等待觸發
            await self._trigger_event.wait()
            self._trigger_event.clear()
            return

        if config.mode == ExecutionMode.PERIODIC:
            # 固定週期等待，但可被 stop() 中斷
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=config.interval_seconds)
                # 如果 wait 成功返回，表示 stop_event 被設置
            except asyncio.TimeoutError:
                # 正常週期到達
                pass
            return

        if config.mode == ExecutionMode.HYBRID:
            # 週期等待，但可被提前觸發
            try:
                # 週期到會觸發 TimeoutError
                await asyncio.wait_for(self._trigger_event.wait(), timeout=config.interval_seconds)
                self._trigger_event.clear()
                logger.debug("策略提前觸發執行")
            except asyncio.TimeoutError:
                # 正常週期到達
                pass
            return

    async def _execute_strategy(self) -> Command:
        """執行當前策略"""
        if self._strategy is None:
            return Command()

        try:
            # 取得基礎上下文並建立不可變副本
            base_context = self._context_provider()
            context = dataclasses.replace(
                base_context, last_command=self._last_command, current_time=datetime.now(timezone.utc)
            )

            # 執行策略（可選卸載到執行緒池）
            if self._offloader is not None:
                command = await self._offloader.run(self._strategy.execute, context)
            else:
                command = self._strategy.execute(context)
            self._last_command = command

            logger.debug(f"策略執行完成: {self._strategy} -> {command}")

            # callback
            if self._on_command is not None:
                await self._on_command(command)

            return command

        except Exception:
            logger.exception(f"策略執行失敗: {self._strategy}")
            return self._last_command
