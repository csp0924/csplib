# =============== Modbus Server - Ramp Behavior ===============
#
# 斜率限制行為：按 ramp_rate 逐步趨近目標值

from __future__ import annotations


class RampBehavior:
    """
    斜率限制行為

    按指定的 ramp_rate 逐步趨近 target，模擬設備功率爬升/下降。

    Attributes:
        ramp_rate: 每秒最大變化量
        current_value: 當前值
        target: 目標值
    """

    def __init__(self, ramp_rate: float = 100.0, initial_value: float = 0.0) -> None:
        self._ramp_rate = ramp_rate
        self._current_value = initial_value
        self._target = initial_value

    @property
    def ramp_rate(self) -> float:
        return self._ramp_rate

    @ramp_rate.setter
    def ramp_rate(self, value: float) -> None:
        self._ramp_rate = abs(value)

    @property
    def current_value(self) -> float:
        return self._current_value

    @property
    def target(self) -> float:
        return self._target

    @target.setter
    def target(self, value: float) -> None:
        self._target = value

    @property
    def at_target(self) -> bool:
        return abs(self._current_value - self._target) < 1e-6

    def update(self, dt: float) -> float:
        """
        按斜率趨近目標

        Args:
            dt: 時間步長（秒）

        Returns:
            更新後的值
        """
        if self.at_target:
            return self._current_value

        diff = self._target - self._current_value
        max_change = self._ramp_rate * dt

        if abs(diff) <= max_change:
            self._current_value = self._target
        else:
            direction = 1.0 if diff > 0 else -1.0
            self._current_value += direction * max_change

        return self._current_value

    def reset(self, value: float = 0.0) -> None:
        """重置到指定值"""
        self._current_value = value
        self._target = value


__all__ = ["RampBehavior"]
