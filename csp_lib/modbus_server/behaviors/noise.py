# =============== Modbus Server - Noise Behavior ===============
#
# 隨機波動行為

from __future__ import annotations

import random
from enum import Enum


class NoiseType(Enum):
    """擾動類型"""

    UNIFORM = "uniform"
    GAUSSIAN = "gaussian"


class NoiseBehavior:
    """
    隨機擾動行為

    在 base_value 附近加入隨機波動。

    Attributes:
        base_value: 基準值
        amplitude: 擾動幅度
        noise_type: 擾動類型 (uniform/gaussian)
    """

    def __init__(
        self,
        base_value: float = 0.0,
        amplitude: float = 1.0,
        noise_type: NoiseType = NoiseType.UNIFORM,
    ) -> None:
        self._base_value = base_value
        self._amplitude = amplitude
        self._noise_type = noise_type
        self._current_value = base_value

    @property
    def base_value(self) -> float:
        return self._base_value

    @base_value.setter
    def base_value(self, value: float) -> None:
        self._base_value = value

    @property
    def current_value(self) -> float:
        return self._current_value

    @property
    def amplitude(self) -> float:
        return self._amplitude

    @amplitude.setter
    def amplitude(self, value: float) -> None:
        self._amplitude = value

    def update(self) -> float:
        """
        產生帶擾動的新值

        Returns:
            base_value + noise
        """
        if self._amplitude <= 0:
            self._current_value = self._base_value
            return self._current_value

        if self._noise_type == NoiseType.UNIFORM:
            noise = random.uniform(-self._amplitude, self._amplitude)
        else:
            # Gaussian: amplitude 作為 1-sigma
            noise = random.gauss(0, self._amplitude)

        self._current_value = self._base_value + noise
        return self._current_value

    def reset(self) -> None:
        """重置到基準值"""
        self._current_value = self._base_value


__all__ = ["NoiseBehavior", "NoiseType"]
