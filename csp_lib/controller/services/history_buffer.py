# =============== Controller Services - HistoryBuffer ===============
#
# 通用時序資料緩衝區，取代 PVDataService 綁定語義。

from __future__ import annotations

from collections import deque
from statistics import fmean


class HistoryBuffer:
    """
    通用時序資料緩衝區。

    收集並維護單一來源的歷史數值（float），供策略層跨 tick 使用。
    語義中性，不綁定特定物理量；命名由擁有者（DeviceDataFeed / SystemController）
    以 key 區分（如 "pv_power"、"grid_power"、"battery_soc"）。

    Usage::

        buf = HistoryBuffer(max_history=300)
        buf.append(500.0)
        buf.append(None)  # 讀取失敗佔位
        avg = buf.get_average()  # 自動過濾 None

    Thread safety:
        非 thread-safe。預期由單一 asyncio event loop 存取。

    Attributes:
        max_history: 最大歷史筆數
    """

    def __init__(self, max_history: int = 300) -> None:
        """
        初始化緩衝區。

        Args:
            max_history: 最大歷史筆數；超過後自動丟棄最舊資料。必須 >= 1。

        Raises:
            ValueError: max_history < 1
        """
        if max_history < 1:
            raise ValueError("max_history must be at least 1")

        self._max_history = max_history
        self._queue: deque[float | None] = deque(maxlen=max_history)

    @property
    def max_history(self) -> int:
        """最大歷史筆數"""
        return self._max_history

    @property
    def count(self) -> int:
        """目前資料筆數（含 None 佔位）"""
        return len(self._queue)

    def append(self, value: float | None) -> None:
        """
        新增一筆資料。

        Args:
            value: 數值；None 代表讀取失敗佔位（仍會佔一個 slot，但被過濾方法排除）
        """
        self._queue.append(value)

    def get_history(self) -> list[float]:
        """
        取得有效歷史資料（過濾 None）。

        Returns:
            有效數值清單；若全為 None 則回傳空 list。
        """
        return [v for v in self._queue if v is not None]

    def get_latest(self) -> float | None:
        """
        取得最新一筆有效值（跳過末端 None）。

        Returns:
            最新有效值；若無任何有效值則回傳 None。
        """
        for v in reversed(self._queue):
            if v is not None:
                return v
        return None

    def get_average(self) -> float | None:
        """
        計算有效值平均。

        Returns:
            有效值算術平均；若無有效值則回傳 None。
        """
        valid = self.get_history()
        if not valid:
            return None
        return fmean(valid)

    def clear(self) -> None:
        """清空所有歷史資料"""
        self._queue.clear()

    def __len__(self) -> int:
        """有效資料筆數（不含 None）"""
        return len(self.get_history())

    def __str__(self) -> str:
        return f"HistoryBuffer(count={self.count}, valid={len(self)})"
