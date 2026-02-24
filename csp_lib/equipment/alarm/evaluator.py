# =============== Equipment Alarm - Evaluator ===============
#
# 告警評估器
#
# 根據點位值評估是否觸發告警：
#   - BitMaskAlarmEvaluator: 位元遮罩告警
#   - TableAlarmEvaluator: 查表告警
#   - ThresholdAlarmEvaluator: 閾值告警

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .definition import AlarmDefinition


class AlarmEvaluator(ABC):
    """
    告警評估器抽象基底

    Attributes:
        point_name: 關聯的點位名稱（由子類別定義）
    """

    point_name: str  # 子類別需定義此欄位

    @abstractmethod
    def evaluate(self, value: Any) -> dict[str, bool]:
        """
        評估告警狀態

        Args:
            value: 點位值

        Returns:
            {告警代碼: 是否觸發} 字典
        """

    @abstractmethod
    def get_alarms(self) -> list[AlarmDefinition]:
        """
        取得所有告警定義

        Returns:
            告警定義列表
        """


@dataclass
class BitMaskAlarmEvaluator(AlarmEvaluator):
    """
    位元遮罩告警評估器

    檢查暫存器值的特定位元是否為 1。

    Attributes:
        point_name: 關聯的點位名稱
        bit_alarms: {位元位置: 告警定義} 字典
    """

    point_name: str
    bit_alarms: dict[int, AlarmDefinition]

    def evaluate(self, value: Any) -> dict[str, bool]:
        """
        評估告警狀態

        Args:
            value: 點位值

        Returns:
            {告警代碼: 是否觸發} 字典
        """
        if value is None:
            return {}
        if not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                return {}

        result: dict[str, bool] = {}
        for bit_pos, alarm in self.bit_alarms.items():
            is_triggered = bool((value >> bit_pos) & 1)
            result[alarm.code] = is_triggered
        return result

    def get_alarms(self) -> list[AlarmDefinition]:
        """
        取得所有告警定義

        Returns:
            告警定義列表
        """
        return list(self.bit_alarms.values())


@dataclass
class TableAlarmEvaluator(AlarmEvaluator):
    """
    查表告警評估器

    根據值查表判斷告警。

    Attributes:
        point_name: 關聯的點位名稱
        table: {值: 告警定義} 字典
    """

    point_name: str
    table: dict[int, AlarmDefinition]

    def evaluate(self, value: Any) -> dict[str, bool]:
        """
        評估告警狀態

        Args:
            value: 點位值

        Returns:
            {告警代碼: 是否觸發} 字典
        """
        if value is None:
            return {}

        result: dict[str, bool] = {alarm.code: False for alarm in self.table.values()}

        if not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                return result

        if value in self.table:
            alarm = self.table[value]
            result[alarm.code] = True

        return result

    def get_alarms(self) -> list[AlarmDefinition]:
        """
        取得所有告警定義

        Returns:
            告警定義列表
        """
        return list(self.table.values())


class Operator(Enum):
    """比較運算子"""

    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="
    EQ = "=="
    NE = "!="


@dataclass(frozen=True)
class ThresholdCondition:
    """閾值條件"""

    alarm: AlarmDefinition
    operator: Operator
    value: float

    def check(self, actual_value: float) -> bool:
        """檢查是否滿足條件"""
        if self.operator == Operator.GT:
            return actual_value > self.value
        if self.operator == Operator.GE:
            return actual_value >= self.value
        if self.operator == Operator.LT:
            return actual_value < self.value
        if self.operator == Operator.LE:
            return actual_value <= self.value
        if self.operator == Operator.EQ:
            return actual_value == self.value
        if self.operator == Operator.NE:
            return actual_value != self.value
        raise ValueError(f"Invalid operator: {self.operator}")


@dataclass
class ThresholdAlarmEvaluator(AlarmEvaluator):
    """
    閾值告警評估器

    根據數值與閾值比較判斷告警。

    Attributes:
        point_name: 關聯的點位名稱
        conditions: 閾值條件列表

    使用範例：
        ThresholdAlarmEvaluator(
            point_name="temperature",
            conditions=[
                ThresholdCondition(
                    alarm=AlarmDefinition("HIGH_TEMP", "溫度過高"),
                    operator=Operator.GT,
                    value=45.0,
                ),
            ],
        )
    """

    point_name: str
    conditions: list[ThresholdCondition]

    def evaluate(self, value: Any) -> dict[str, bool]:
        """
        評估告警狀態

        Args:
            value: 點位值

        Returns:
            {告警代碼: 是否觸發} 字典
        """
        if value is None:
            return {}

        if not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return {}

        result: dict[str, bool] = {}
        for condition in self.conditions:
            result[condition.alarm.code] = condition.check(value)
        return result

    def get_alarms(self) -> list[AlarmDefinition]:
        """
        取得所有告警定義

        Returns:
            告警定義列表
        """
        return [condition.alarm for condition in self.conditions]


__all__ = [
    "AlarmEvaluator",
    "BitMaskAlarmEvaluator",
    "TableAlarmEvaluator",
    "ThresholdAlarmEvaluator",
    "ThresholdCondition",
    "Operator",
]
