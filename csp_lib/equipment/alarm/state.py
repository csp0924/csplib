# =============== Equipment Alarm - State ===============
#
# 告警狀態管理
#
# 提供告警狀態持久化與遲滯處理

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from csp_lib.core import get_logger

from .definition import AlarmDefinition, AlarmLevel

logger = get_logger(__name__)


class AlarmEventType(Enum):
    """告警事件類型"""

    TRIGGERED = "triggered"
    CLEARED = "cleared"


@dataclass
class AlarmEvent:
    """告警事件"""

    event_type: AlarmEventType
    alarm: AlarmDefinition
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AlarmState:
    """
    告警狀態 - 可變

    Attributes:
        definition: 告警定義
        is_active: 是否啟用中
        activate_count: 連續觸發次數
        clear_count: 連續解除次數
        activated_at: 本次告警啟用時間
        cleared_at: 本次告警清除時間
        last_triggered_at: 最後條件成立時間（用於追蹤）
    """

    definition: AlarmDefinition
    is_active: bool = False
    activate_count: int = 0
    clear_count: int = 0
    activated_at: datetime | None = None
    cleared_at: datetime | None = None
    last_triggered_at: datetime | None = None

    @property
    def duration(self) -> float | None:
        """
        告警持續時間（秒）

        Returns:
            - 告警已清除：返回 activated_at 到 cleared_at 的秒數
            - 告警進行中：返回 activated_at 到現在的秒數
            - 尚未啟用過：返回 None
        """
        if self.activated_at is None:
            return None
        end_time = self.cleared_at if self.cleared_at else datetime.now(timezone.utc)
        return (end_time - self.activated_at).total_seconds()

    def update(self, is_triggered: bool) -> AlarmEvent | None:
        """
        更新告警狀態

        根據遲滯設定決定是否真正觸發/解除告警。

        Args:
            is_triggered: 本次評估結果

        Returns:
            告警事件（如果狀態變化），否則 None
        """
        hysteresis = self.definition.hysteresis
        now = datetime.now(timezone.utc)

        if is_triggered:
            # 觸發中
            self.activate_count += 1
            self.clear_count = 0
            self.last_triggered_at = now

            if not self.is_active and self.activate_count >= hysteresis.activate_threshold:
                # 達到觸發閾值，啟用告警
                self.is_active = True
                self.activated_at = now
                self.cleared_at = None  # 新週期開始，清除上次的結束時間
                return AlarmEvent(AlarmEventType.TRIGGERED, self.definition, now)
        else:
            # 未觸發
            self.clear_count += 1
            self.activate_count = 0

            if self.is_active and self.clear_count >= hysteresis.clear_threshold:
                # 達到解除閾值，清除告警
                self.is_active = False
                self.cleared_at = now
                return AlarmEvent(AlarmEventType.CLEARED, self.definition, now)

        return None

    def force_clear(self) -> AlarmEvent | None:
        """強制清除告警"""
        if self.is_active:
            now = datetime.now(timezone.utc)
            self.is_active = False
            self.activate_count = 0
            self.clear_count = 0
            self.cleared_at = now
            return AlarmEvent(AlarmEventType.CLEARED, self.definition, now)
        return None


class AlarmStateManager:
    """
    告警狀態管理器

    管理所有告警的狀態，提供持久化與遲滯處理。
    重要：讀取失敗時保持現有狀態，不會清除告警。
    """

    def __init__(self) -> None:
        self._states: dict[str, AlarmState] = {}

    def register_alarm(self, alarm: AlarmDefinition) -> AlarmState:
        """
        註冊告警定義

        Args:
            alarm: 告警定義

        Returns:
            AlarmState: 新建或已存在的告警狀態

        Raises:
            KeyError: 告警代碼已存在
        """
        if alarm.code in self._states:
            raise KeyError(f"告警 '{alarm.code}' 已註冊")
        else:
            self._states[alarm.code] = AlarmState(definition=alarm)
        return self._states[alarm.code]

    def register_alarms(self, alarms: list[AlarmDefinition]) -> list[AlarmState]:
        """
        批量註冊告警定義

        Args:
            alarms: 告警定義列表

        Returns:
            list[AlarmState]: 成功註冊的告警狀態列表

        Raises:
            KeyError: 存在重複的告警代碼
        """
        duplicates = [a.code for a in alarms if a.code in self._states]
        if duplicates:
            raise KeyError(f"以下告警代碼已存在: {duplicates}")

        return [self.register_alarm(alarm) for alarm in alarms]

    def update(self, evaluations: dict[str, bool]) -> list[AlarmEvent]:
        """
        更新告警狀態

        Args:
            evaluations: {告警代碼: 是否觸發} 字典

        Returns:
            告警事件列表（狀態變化的告警）
        """
        events: list[AlarmEvent] = []

        for code, is_triggered in evaluations.items():
            if code not in self._states:
                continue

            state = self._states[code]
            event = state.update(is_triggered=is_triggered)
            if event:
                if event.event_type == AlarmEventType.TRIGGERED:
                    logger.debug(f"Alarm '{event.alarm.name}' ({code}): TRIGGERED")
                else:
                    logger.debug(f"Alarm '{event.alarm.name}' ({code}): CLEARED")
                events.append(event)

        return events

    def clear_alarm(self, code: str) -> AlarmEvent | None:
        """
        強制清除告警

        Args:
            code: 告警代碼

        Returns:
            AlarmEvent: 清除事件，如果告警不存在則返回 None
        """
        if code not in self._states:
            return None

        state = self._states[code]
        return state.force_clear()

    def get_active_alarms(self) -> list[AlarmState]:
        """
        取得所有啟用中的告警

        Returns:
            list[AlarmState]: 所有啟用中的告警狀態
        """
        return [state for state in self._states.values() if state.is_active]

    def get_state(self, code: str) -> AlarmState | None:
        """
        取得特定告警的狀態

        Args:
            code: 告警代碼

        Returns:
            AlarmState: 告警狀態，如果告警不存在則返回 None
        """
        return self._states.get(code)

    def has_protection_alarm(self) -> bool:
        """
        檢查是否存在保護性告警

        Returns:
            bool: 如果存在保護性告警則返回 True，否則返回 False
        """
        return any(state.is_active and state.definition.level == AlarmLevel.ALARM for state in self._states.values())

    def export_states(self) -> dict[str, AlarmState]:
        """
        匯出所有告警狀態的 shallow copy

        Returns:
            {告警代碼: AlarmState} 字典
        """
        return dict(self._states)

    def import_states(self, states: dict[str, AlarmState]) -> None:
        """
        匯入告警狀態

        對已註冊的 code，用舊 state 覆蓋新 state 的計數和時間欄位。

        Args:
            states: 要匯入的告警狀態
        """
        for code, old_state in states.items():
            if code in self._states:
                new_state = self._states[code]
                new_state.is_active = old_state.is_active
                new_state.activate_count = old_state.activate_count
                new_state.clear_count = old_state.clear_count
                new_state.activated_at = old_state.activated_at
                new_state.cleared_at = old_state.cleared_at
                new_state.last_triggered_at = old_state.last_triggered_at

    def reset(self) -> None:
        """
        重置所有告警狀態
        """
        for state in self._states.values():
            state.force_clear()


__all__ = [
    "AlarmEventType",
    "AlarmEvent",
    "AlarmState",
    "AlarmStateManager",
]
