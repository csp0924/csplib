# =============== PV Data Service ===============
#
# PV 功率資料服務

from __future__ import annotations

from collections import deque
from typing import Optional


class PVDataService:
    """
    PV 功率資料服務

    收集並維護 PV 功率歷史資料，供 PVSmooth 等策略使用。
    透過建構子注入策略，確保策略切換時資料不遺失。

    Usage:
        pv_service = PVDataService(max_history=300)
        pv_service.append(500.0)  # 由外部 loop 定期呼叫

        strategy = PVSmoothStrategy(config, pv_service=pv_service)

    Attributes:
        max_history: 最大歷史筆數
    """

    def __init__(self, max_history: int = 300):
        """
        初始化 PV 資料服務

        Args:
            max_history: 最大歷史筆數，超過後自動移除最舊資料
        """
        if max_history < 1:
            raise ValueError("max_history must be at least 1")

        self._max_history = max_history
        self._queue: deque[Optional[float]] = deque(maxlen=max_history)

    @property
    def max_history(self) -> int:
        """最大歷史筆數"""
        return self._max_history

    @property
    def count(self) -> int:
        """目前資料筆數 (含 None)"""
        return len(self._queue)

    def append(self, power: Optional[float]) -> None:
        """
        新增一筆 PV 功率資料

        Args:
            power: PV 功率值 (kW)，可為 None 表示讀取失敗
        """
        self._queue.append(power)

    def get_history(self) -> list[float]:
        """
        取得有效的歷史資料 (過濾 None)

        Returns:
            list[float]: 有效的 PV 功率歷史
        """
        return [p for p in self._queue if p is not None]

    def get_latest(self) -> Optional[float]:
        """
        取得最新一筆有效資料

        Returns:
            Optional[float]: 最新的 PV 功率值，若無資料則回傳 None
        """
        for p in reversed(self._queue):
            if p is not None:
                return p
        return None

    def get_average(self) -> Optional[float]:
        """
        計算有效資料的平均值

        Returns:
            Optional[float]: 平均 PV 功率，若無資料則回傳 None
        """
        valid = self.get_history()
        if not valid:
            return None
        return sum(valid) / len(valid)

    def clear(self) -> None:
        """清空所有歷史資料"""
        self._queue.clear()

    def __len__(self) -> int:
        """回傳有效資料筆數 (不含 None)"""
        return len(self.get_history())

    def __str__(self) -> str:
        return f"PVDataService(count={self.count}, valid={len(self)})"
