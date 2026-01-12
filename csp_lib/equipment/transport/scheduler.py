# =============== Equipment IO - Scheduler ===============
#
# 讀取排程器
#
# 支援動態點位輪詢，解決大量點位讀取性能問題

from __future__ import annotations

from typing import Sequence

from .base import ReadGroup


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
