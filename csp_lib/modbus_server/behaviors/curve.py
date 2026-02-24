# =============== Modbus Server - Curve Behavior ===============
#
# 曲線驅動行為：整合現有 CurveRegistry

from __future__ import annotations

import time
from typing import Iterator

from csp_lib.equipment.simulation.curve import CurvePoint, CurveProvider


class CurveBehavior:
    """
    曲線驅動行為

    使用 CurveProvider 按時間驅動數值變化。
    每個 CurvePoint 指定一個 value 和 duration，
    在 duration 內持續輸出該 value。
    """

    def __init__(self, curve_provider: CurveProvider, default_value: float = 0.0) -> None:
        self._curve_provider = curve_provider
        self._default_value = default_value
        self._current_value = default_value
        self._iterator: Iterator[CurvePoint] | None = None
        self._curve_name: str | None = None
        self._current_point: CurvePoint | None = None
        self._point_end_time: float | None = None

    @property
    def current_value(self) -> float:
        return self._current_value

    @property
    def is_running(self) -> bool:
        return self._iterator is not None

    def start_curve(self, name: str) -> bool:
        """啟動指定曲線"""
        curve = self._curve_provider.get_curve(name)
        if curve is None:
            return False
        self._iterator = curve
        self._curve_name = name
        return self._advance()

    def stop_curve(self) -> None:
        """停止曲線"""
        self._iterator = None
        self._curve_name = None
        self._current_point = None
        self._point_end_time = None
        self._current_value = self._default_value

    def update(self) -> float:
        """
        更新曲線狀態

        Returns:
            當前值（曲線值或 default_value）
        """
        if self._iterator is None:
            return self._current_value

        now = time.monotonic()
        if self._point_end_time is not None and now >= self._point_end_time:
            if not self._advance():
                return self._current_value

        if self._current_point is not None:
            self._current_value = self._current_point.value

        return self._current_value

    def _advance(self) -> bool:
        """前進到下一個曲線點"""
        if self._iterator is None:
            return False
        try:
            point = next(self._iterator)
            self._current_point = point
            self._point_end_time = time.monotonic() + point.duration
            self._current_value = point.value
            return True
        except StopIteration:
            self.stop_curve()
            return False

    def reset(self) -> None:
        """重置到初始狀態"""
        self.stop_curve()


__all__ = ["CurveBehavior"]
