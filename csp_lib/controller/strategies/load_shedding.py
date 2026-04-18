# =============== Load Shedding Strategy ===============
#
# 階段性負載卸載策略
#
# 在離網 (islanding) 等場景中，根據電池 SOC、剩餘時間等條件，
# 按優先順序逐步卸載/恢復負載，延長供電時間。
#
# Protocol:
#   - LoadCircuitProtocol: 負載迴路控制協定
#   - ShedCondition: 卸載觸發條件協定
#
# 內建條件:
#   - ThresholdCondition: 閾值條件
#   - RemainingTimeCondition: 剩餘時間條件
#
# Strategy:
#   - LoadSheddingStrategy: 階段性負載卸載策略

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from csp_lib.controller.core import (
    Command,
    ConfigMixin,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)
from csp_lib.core import get_logger
from csp_lib.core.runtime_params import RuntimeParameters

from ._param_resolver import ParamResolver

logger = get_logger(__name__)


# =============== Protocols ===============


@runtime_checkable
class LoadCircuitProtocol(Protocol):
    """負載迴路控制協定"""

    @property
    def name(self) -> str: ...

    @property
    def is_shed(self) -> bool: ...

    async def shed(self) -> None: ...

    async def restore(self) -> None: ...


@runtime_checkable
class ShedCondition(Protocol):
    """卸載觸發條件"""

    def should_shed(self, context: StrategyContext) -> bool: ...

    def should_restore(self, context: StrategyContext) -> bool: ...


# =============== Built-in Conditions ===============


class ThresholdCondition:
    """
    閾值條件

    當 context.extra[context_key] < shed_below 時觸發卸載，
    當 context.extra[context_key] > restore_above 時觸發恢復。
    """

    def __init__(self, context_key: str, shed_below: float, restore_above: float) -> None:
        if restore_above < shed_below:
            raise ValueError(f"restore_above ({restore_above}) must be >= shed_below ({shed_below})")
        self._context_key = context_key
        self._shed_below = shed_below
        self._restore_above = restore_above

    def should_shed(self, context: StrategyContext) -> bool:
        value = context.extra.get(self._context_key)
        if value is None:
            return False
        return value < self._shed_below

    def should_restore(self, context: StrategyContext) -> bool:
        value = context.extra.get(self._context_key)
        if value is None:
            return False
        return value > self._restore_above


class RemainingTimeCondition:
    """
    剩餘時間條件

    當電池剩餘時間低於 shed_below 分鐘時觸發卸載，
    高於 restore_above 分鐘時觸發恢復。
    """

    def __init__(
        self,
        context_key: str = "battery_remaining_minutes",
        shed_below: float = 30.0,
        restore_above: float = 45.0,
    ) -> None:
        if restore_above < shed_below:
            raise ValueError(f"restore_above ({restore_above}) must be >= shed_below ({shed_below})")
        self._context_key = context_key
        self._shed_below = shed_below
        self._restore_above = restore_above

    def should_shed(self, context: StrategyContext) -> bool:
        value = context.extra.get(self._context_key)
        if value is None:
            return False
        return value < self._shed_below

    def should_restore(self, context: StrategyContext) -> bool:
        value = context.extra.get(self._context_key)
        if value is None:
            return False
        return value > self._restore_above


# =============== Shed Stage ===============


@dataclass(frozen=True, slots=True)
class ShedStage:
    """
    卸載階段

    Attributes:
        name: 階段名稱
        circuits: 此階段要卸載的迴路
        condition: 觸發條件
        priority: 越小越先卸（越晚恢復）
        min_hold_seconds: 最小保持時間（防抖動）
    """

    name: str
    circuits: list[LoadCircuitProtocol]
    condition: ShedCondition
    priority: int = 0
    min_hold_seconds: float = 30.0


# =============== Config ===============


@dataclass(frozen=True, slots=True)
class LoadSheddingConfig(ConfigMixin):
    """
    負載卸載策略配置

    Attributes:
        stages: 卸載階段列表
        evaluation_interval: 評估週期（秒）。v0.8.0 起型別由 ``int`` 擴寬為 ``float``
            以支援次秒級評估（例如 0.5 秒），既有整數字面值仍相容。
        restore_delay: 恢復延遲（秒，防止頻繁切換）
        auto_restore_on_deactivate: 策略停用時是否自動恢復所有負載
    """

    stages: list[ShedStage] = field(default_factory=list)
    evaluation_interval: float = 5.0
    restore_delay: float = 60.0
    auto_restore_on_deactivate: bool = True


# =============== Internal State ===============


class _StageState:
    """單一階段的內部狀態"""

    __slots__ = ("is_shed", "shed_at", "restore_requested_at")

    def __init__(self) -> None:
        self.is_shed: bool = False
        self.shed_at: float = 0.0
        self.restore_requested_at: float | None = None


# =============== Strategy ===============


class LoadSheddingStrategy(Strategy):
    """
    階段性負載卸載策略

    - PERIODIC 模式持續評估條件
    - execute() 純條件判斷，記錄需要 shed/restore 的 stages
    - 背景 Task 執行實際的 async 斷路器操作
    - 卸載順序：priority 升序（低優先級先卸）
    - 恢復順序：priority 降序（高優先級先恢復）
    """

    def __init__(
        self,
        config: LoadSheddingConfig,
        *,
        params: RuntimeParameters | None = None,
        param_keys: Mapping[str, str] | None = None,
        enabled_key: str | None = None,
    ) -> None:
        """初始化負載卸載策略。

        Runtime 動態化 (v0.8.2):
            可動態化的純數值 / bool 欄位：
                - evaluation_interval
                - restore_delay
                - auto_restore_on_deactivate

            **stages 清單不動態化**（含 circuits / condition 等物件參照，
            runtime 覆寫風險過大；如需改 stages 請用 ``update_config``）。

            ``enabled_key`` falsy → 回 ``context.last_command``（保守策略；
            不強制 shed/restore，避免誤動作）。

        Args:
            config: 負載卸載策略配置
            params: RuntimeParameters，可選
            param_keys: 欄位名 → runtime key 映射
                （只對 evaluation_interval / restore_delay /
                auto_restore_on_deactivate 生效）
            enabled_key: runtime 啟停旗標 key
        """
        self._config = config
        self._sorted_stages = sorted(config.stages, key=lambda s: s.priority)
        self._states: dict[str, _StageState] = {stage.name: _StageState() for stage in config.stages}
        self._pending_actions: list[tuple[str, str]] = []  # (stage_name, "shed"|"restore")
        self._action_task: asyncio.Task[None] | None = None
        self._action_event = asyncio.Event()
        self._resolver = ParamResolver(
            params=params,
            param_keys=param_keys,
            config=self._config,
        )
        self._enabled_key = enabled_key

    @property
    def config(self) -> LoadSheddingConfig:
        return self._config

    @property
    def execution_config(self) -> ExecutionConfig:
        # evaluation_interval 可動態化：每次回 ExecutionConfig 時讀 runtime
        interval = float(self._resolver.resolve("evaluation_interval"))
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=interval)

    def execute(self, context: StrategyContext) -> Command:
        # Runtime enabled 旗標：falsy → 保守策略，維持上次指令（不強制改 0）
        if self._enabled_key is not None:
            enabled = self._resolver.resolve_optional(self._enabled_key, True)
            if not enabled:
                logger.debug("LoadSheddingStrategy: runtime disabled via '{}'", self._enabled_key)
                return context.last_command

        now = time.monotonic()
        restore_delay = float(self._resolver.resolve("restore_delay"))

        # 卸載評估（priority 升序：低優先級先卸）
        for stage in self._sorted_stages:
            state = self._states[stage.name]
            if not state.is_shed and stage.condition.should_shed(context):
                state.is_shed = True
                state.shed_at = now
                state.restore_requested_at = None
                self._pending_actions.append((stage.name, "shed"))
                logger.info(f"Load shedding: stage '{stage.name}' scheduled for shed")

        # 恢復評估（priority 降序：高優先級先恢復）
        for stage in reversed(self._sorted_stages):
            state = self._states[stage.name]
            if not state.is_shed:
                continue
            if not stage.condition.should_restore(context):
                state.restore_requested_at = None
                continue

            # 檢查 min_hold_seconds
            if (now - state.shed_at) < stage.min_hold_seconds:
                continue

            # 開始 restore delay
            if state.restore_requested_at is None:
                state.restore_requested_at = now
                logger.debug(f"Load shedding: stage '{stage.name}' restore delay started")
                continue

            # 檢查 restore_delay（runtime 可動態化）
            if (now - state.restore_requested_at) >= restore_delay:
                state.is_shed = False
                state.restore_requested_at = None
                self._pending_actions.append((stage.name, "restore"))
                logger.info(f"Load shedding: stage '{stage.name}' scheduled for restore")

        if self._pending_actions:
            self._action_event.set()

        return context.last_command

    async def on_activate(self) -> None:
        self._action_event.clear()
        self._action_task = asyncio.create_task(self._action_loop())
        logger.info("LoadSheddingStrategy activated")

    async def on_deactivate(self) -> None:
        if self._action_task is not None:
            self._action_task.cancel()
            try:
                await self._action_task
            except asyncio.CancelledError:
                pass
            self._action_task = None

        # auto_restore_on_deactivate 可動態化
        auto_restore = bool(self._resolver.resolve("auto_restore_on_deactivate"))
        if auto_restore:
            await self._restore_all()

        # 重置狀態
        self._pending_actions.clear()
        for state in self._states.values():
            state.is_shed = False
            state.shed_at = 0.0
            state.restore_requested_at = None
        logger.info("LoadSheddingStrategy deactivated")

    @property
    def shed_stage_names(self) -> list[str]:
        """當前已卸載的階段名稱"""
        return [name for name, state in self._states.items() if state.is_shed]

    async def _action_loop(self) -> None:
        """背景 task：執行待處理的 shed/restore 操作"""
        while True:
            await self._action_event.wait()
            self._action_event.clear()

            actions = list(self._pending_actions)
            self._pending_actions.clear()

            stage_map = {s.name: s for s in self._config.stages}
            for stage_name, action in actions:
                stage = stage_map.get(stage_name)
                if stage is None:
                    continue
                for circuit in stage.circuits:
                    try:
                        if action == "shed":
                            await circuit.shed()
                            logger.info(f"Circuit '{circuit.name}' shed (stage: {stage_name})")
                        else:
                            await circuit.restore()
                            logger.info(f"Circuit '{circuit.name}' restored (stage: {stage_name})")
                    except Exception:
                        logger.opt(exception=True).warning(
                            f"Failed to {action} circuit '{circuit.name}' (stage: {stage_name})"
                        )

    async def _restore_all(self) -> None:
        """恢復所有已卸載的迴路（priority 降序）"""
        for stage in reversed(self._sorted_stages):
            state = self._states[stage.name]
            if not state.is_shed:
                continue
            for circuit in stage.circuits:
                try:
                    if circuit.is_shed:
                        await circuit.restore()
                        logger.info(f"Auto-restore circuit '{circuit.name}' (stage: {stage.name})")
                except Exception:
                    logger.opt(exception=True).warning(
                        f"Failed to auto-restore circuit '{circuit.name}' (stage: {stage.name})"
                    )

    def __str__(self) -> str:
        shed_count = sum(1 for s in self._states.values() if s.is_shed)
        return f"LoadSheddingStrategy(stages={len(self._config.stages)}, shed={shed_count})"
