# =============== Strategy Executor ===============
#
# 策略執行器：管理策略的執行生命週期
# - 處理週期執行 (PERIODIC)
# - 支援手動觸發 (TRIGGERED)
# - 混合模式 (HYBRID: 週期 + 可提前觸發)

from __future__ import annotations

import asyncio
import dataclasses
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from csp_lib.controller.core import Command, ExecutionMode, Strategy, StrategyContext
from csp_lib.core import get_logger
from csp_lib.core._time_anchor import next_tick_delay

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
        self._strategy_changed_event = asyncio.Event()
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

        # 喚醒可能阻塞在 _wait_for_execution() 的 run loop，
        # 使其重新讀取新策略的 execution_config
        self._strategy_changed_event.set()

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
        主執行迴圈（v0.8.0：work-first + absolute time anchoring）

        根據策略的 ExecutionConfig 決定執行方式：

        - ``TRIGGERED``：等待外部觸發 / 策略切換，不使用時間錨。
        - ``PERIODIC`` / ``HYBRID``：**先執行再等待**（work-first），
          以 monotonic anchor 計算下一個 tick delay，補償 execute 耗時。

        重設 anchor 的情況：
        - 策略切換（set_strategy）→ 清除 strategy_changed_event + anchor=now, n=0
        - HYBRID 模式被提前觸發 → anchor=now, n=0
        - ``next_tick_delay`` 偵測到嚴重落後（>= 一個週期）→ 其內部自動重設

        呼叫 stop() 可停止迴圈。
        """

        self._stop_event.clear()
        self._is_running = True
        logger.info("策略執行器已啟動")

        anchor = time.monotonic()
        n = 0

        try:
            while not self._stop_event.is_set():
                if self._strategy is None:
                    await asyncio.sleep(0.1)
                    continue

                config = self._strategy.execution_config

                if config.mode == ExecutionMode.TRIGGERED:
                    # 先 clear strategy_changed_event：忽略「進入迴圈前」的殘留設定
                    # （與 v0.7.x 的 _wait_for_execution 首行 clear 行為等價）。
                    self._strategy_changed_event.clear()
                    # 等觸發（或等待中途的策略切換 / stop）
                    await self._wait_triggered()
                    if self._stop_event.is_set():
                        break
                    if self._strategy_changed_event.is_set():
                        # 等待中發生策略切換 → 清除旗標、重設 anchor 後回到頂部
                        self._strategy_changed_event.clear()
                        anchor = time.monotonic()
                        n = 0
                        continue
                    await self._execute_strategy()
                    continue

                # PERIODIC / HYBRID：work-first — 先執行再等 tick
                # 進入前先清除 strategy_changed，避免首次 execute 後誤判為切換
                self._strategy_changed_event.clear()
                await self._execute_strategy()
                if self._stop_event.is_set():
                    break

                # 計算下一個 tick 應睡多久（絕對時間錨定）
                delay, anchor, n = next_tick_delay(anchor, n, float(config.interval_seconds))
                triggered_early = await self._wait_periodic(
                    delay, allow_early_trigger=(config.mode == ExecutionMode.HYBRID)
                )
                if self._stop_event.is_set():
                    break
                if self._strategy_changed_event.is_set():
                    # 策略切換：清除旗標、重設 anchor + 計數
                    self._strategy_changed_event.clear()
                    anchor = time.monotonic()
                    n = 0
                    continue
                if triggered_early:
                    # HYBRID 提前觸發：重設 anchor 避免連續 burst
                    anchor = time.monotonic()
                    n = 0

        except asyncio.CancelledError:
            logger.info("策略執行器被取消")
        finally:
            self._is_running = False
            logger.info("策略執行器已停止")

    def stop(self) -> None:
        """停止執行迴圈"""
        self._stop_event.set()
        self._trigger_event.set()  # 解除等待
        self._strategy_changed_event.set()  # 解除等待
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

    async def _wait_triggered(self) -> None:
        """TRIGGERED 模式：等待外部觸發或策略切換。

        不涉及時間錨，單純阻塞等待 ``_trigger_event`` 或 ``_strategy_changed_event``。
        任一發生即返回；``stop_event`` 亦會經由上層檢查中斷。
        """
        trigger_task = asyncio.ensure_future(self._trigger_event.wait())
        changed_task = asyncio.ensure_future(self._strategy_changed_event.wait())
        stop_task = asyncio.ensure_future(self._stop_event.wait())
        done, pending = await asyncio.wait(
            [trigger_task, changed_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if trigger_task in done:
            self._trigger_event.clear()

    async def _wait_periodic(self, delay: float, *, allow_early_trigger: bool) -> bool:
        """PERIODIC / HYBRID 模式：等待 delay 秒或被中斷。

        Args:
            delay: 下一個 tick 應睡的秒數（由 ``next_tick_delay`` 算出，可為 0）。
            allow_early_trigger: True（HYBRID）允許 ``trigger()`` 提前喚醒；
                False（PERIODIC）只能被 stop / strategy_changed 中斷。

        Returns:
            True 代表被提前觸發（HYBRID only）；False 代表正常超時或其他中斷。
        """
        if delay <= 0:
            # 不 sleep，但讓出 event loop 一次
            await asyncio.sleep(0)
            return False

        stop_task = asyncio.ensure_future(self._stop_event.wait())
        changed_task = asyncio.ensure_future(self._strategy_changed_event.wait())
        wait_set: list[asyncio.Task[bool]] = [stop_task, changed_task]
        trigger_task: asyncio.Task[bool] | None = None
        if allow_early_trigger:
            trigger_task = asyncio.ensure_future(self._trigger_event.wait())
            wait_set.append(trigger_task)

        triggered_early = False
        try:
            done, pending = await asyncio.wait(
                wait_set,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=delay,
            )
            for t in pending:
                t.cancel()
            if trigger_task is not None and trigger_task in done:
                self._trigger_event.clear()
                triggered_early = True
                logger.debug("策略提前觸發執行")
        except asyncio.TimeoutError:
            for t in wait_set:
                t.cancel()

        return triggered_early

    async def _execute_strategy(self) -> Command:
        """執行當前策略"""
        if self._strategy is None:
            return Command()

        context: StrategyContext | None = None
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

        except Exception as e:
            strategy_name = type(self._strategy).__name__ if self._strategy else "None"
            extra_keys = list(context.extra.keys()) if context is not None else []
            logger.exception(
                f"Strategy execution failed: {strategy_name}, "
                f"soc={getattr(context, 'soc', None)}, "
                f"extra_keys={extra_keys}, "
                f"last_command={self._last_command}, "
                f"error={e!r}"
            )
            # 不更新 self._last_command，保持上次正常命令供下輪 context.last_command 使用
            return Command(p_target=0.0, q_target=0.0, is_fallback=True)
