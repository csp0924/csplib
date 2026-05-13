# =============== Equipment IO - Scheduler ===============
#
# 讀取排程器
#
# 支援動態點位輪詢，解決大量點位讀取性能問題

from __future__ import annotations

from typing import Sequence

from csp_lib.core import get_logger

from .base import ReadGroup

logger = get_logger(__name__)


class ReadScheduler:
    """
    讀取排程器

    支援「固定讀取」與「輪流讀取」兩種模式，解決大量點位讀取性能問題。
    直接接收預計算的 ReadGroup，讓呼叫者負責分組邏輯。

    使用範例：
        from csp_lib.equipment.transport import PointGrouper, ReadGroup

        grouper = PointGrouper()

        scheduler = ReadScheduler(
            always_groups=grouper.compute(mbms_core_points),
            rotating_groups=[
                grouper.compute(sbms1_points),
                grouper.compute(sbms2_points),
                grouper.compute(sbms3_points),
            ],
        )

        # 第1次: always_groups + rotating_groups[0]
        # 第2次: always_groups + rotating_groups[1]
        # 第3次: always_groups + rotating_groups[2]
        # 第4次: always_groups + rotating_groups[0] (循環)
    """

    def __init__(
        self,
        always_groups: Sequence[ReadGroup] | None = None,
        rotating_groups: Sequence[Sequence[ReadGroup]] | None = None,
    ):
        """
        初始化排程器

        Args:
            always_groups: 每次都讀取的分組
            rotating_groups: 輪流讀取的分組列表
        """
        self._always_groups: list[ReadGroup] = list(always_groups) if always_groups else []
        self._rotating_groups: list[list[ReadGroup]] = [list(g) for g in rotating_groups] if rotating_groups else []
        self._rotating_index = 0

    def get_next_groups(self) -> list[ReadGroup]:
        """
        取得下一批要讀取的分組

        Returns:
            ReadGroup 列表
        """
        groups: list[ReadGroup] = list(self._always_groups)

        if self._rotating_groups:
            groups.extend(self._rotating_groups[self._rotating_index])
            self._rotating_index = (self._rotating_index + 1) % len(self._rotating_groups)

        return groups

    def get_next_groups_with_rotating(self) -> tuple[list[ReadGroup], list[ReadGroup]]:
        """
        取得下一批要讀取的分組，同時回傳本次的 rotating slice。

        與 ``get_next_groups`` 同樣推進 rotating_index，但額外回傳「本次取到的
        rotating slot 之 groups」，方便呼叫端在讀取失敗時透過 ``rollback_index``
        將該 slot 排回隊伍頭部重試（避免 silent skip）。

        Returns:
            (all_groups, rotating_slice) — all_groups 是 always + rotating 的合併，
            rotating_slice 是本次推進讀到的 rotating slot；無 rotating 時為空 list。
        """
        always = list(self._always_groups)
        if not self._rotating_groups:
            return always, []
        rotating_slice = list(self._rotating_groups[self._rotating_index])
        self._rotating_index = (self._rotating_index + 1) % len(self._rotating_groups)
        return [*always, *rotating_slice], rotating_slice

    def rollback_index(self) -> None:
        """
        將 rotating_index 回退一格（與最近一次 advance 對稱）。

        用於呼叫端偵測到 rotating slot 讀取失敗、想讓下個 cycle 重訪同一個 slot
        的情境。無 rotating 群組時為 no-op，避免呼叫端額外 guard。
        """
        if not self._rotating_groups:
            return
        self._rotating_index = (self._rotating_index - 1) % len(self._rotating_groups)

    def peek_next_groups(self) -> list[ReadGroup]:
        """
        預覽下一批要讀取的分組（不推進索引）

        Returns:
            ReadGroup 列表
        """
        groups: list[ReadGroup] = list(self._always_groups)

        if self._rotating_groups:
            groups.extend(self._rotating_groups[self._rotating_index])

        return groups

    def update_groups(
        self,
        always_groups: Sequence[ReadGroup] | None = None,
        rotating_groups: Sequence[Sequence[ReadGroup]] | None = None,
    ) -> None:
        """
        動態更新分組

        Args:
            always_groups: 新的固定分組，None 表示保持不變
            rotating_groups: 新的輪替分組，None 表示保持不變
        """
        if always_groups is not None:
            self._always_groups = list(always_groups)
        if rotating_groups is not None:
            self._rotating_groups = [list(g) for g in rotating_groups]
            self._rotating_index = 0
        if always_groups is not None or rotating_groups is not None:
            logger.info(
                f"ReadScheduler groups updated: always={len(self._always_groups)}, rotating={len(self._rotating_groups)}"
            )

    def reset(self) -> None:
        """重置輪詢狀態"""
        self._rotating_index = 0

    @property
    def current_rotating_index(self) -> int:
        """當前輪替索引"""
        return self._rotating_index

    @property
    def rotating_count(self) -> int:
        """輪替群組數量"""
        return len(self._rotating_groups)

    @property
    def has_rotating(self) -> bool:
        """是否有輪替群組"""
        return bool(self._rotating_groups)


__all__ = [
    "ReadScheduler",
]
