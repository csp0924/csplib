# =============== PV Data Service ===============
#
# PV 功率資料服務（v0.9.x 起為 HistoryBuffer 的語義化 subclass）。
#
# .. deprecated:: 0.9.x
#     本類別僅為 backward-compat 保留，改用 :class:`HistoryBuffer`。
#     將於 v1.0 移除。

from __future__ import annotations

import warnings

from .history_buffer import HistoryBuffer


class PVDataService(HistoryBuffer):
    """
    PV 功率資料服務（deprecated alias of :class:`HistoryBuffer`）。

    .. deprecated:: 0.9.x
        改用 :class:`HistoryBuffer`。
        ``PVDataService`` 將於 v1.0 移除。

        Migration::

            # Before
            from csp_lib.controller.services import PVDataService
            svc = PVDataService(max_history=300)

            # After
            from csp_lib.controller.services import HistoryBuffer
            buf = HistoryBuffer(max_history=300)

    API 與 HistoryBuffer 完全相同（append / get_history / get_latest /
    get_average / clear / count / max_history / __len__）。建構時會發出
    ``DeprecationWarning``。
    """

    def __init__(self, max_history: int = 300) -> None:
        """
        初始化 PV 資料服務（deprecated）。

        Args:
            max_history: 最大歷史筆數；delegate 至 HistoryBuffer。
        """
        warnings.warn(
            "PVDataService is deprecated since 0.9.x; use HistoryBuffer instead. Will be removed in v1.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(max_history=max_history)

    def __str__(self) -> str:
        return f"PVDataService(count={self.count}, valid={len(self)})"
