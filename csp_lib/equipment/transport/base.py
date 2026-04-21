# =============== Equipment Transport - Base ===============
#
# 點位分組器
#
# 自動合併相鄰點位以減少請求次數

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import TYPE_CHECKING, Sequence

from .config import PointGrouperConfig

if TYPE_CHECKING:
    from ..core.point import ReadPoint


@dataclass(slots=True, frozen=True)
class ReadGroup:
    """讀取群組（不可變）

    Attributes:
        unit_id: 此 group 要送往的 Modbus unit_id（slave address）。
            - ``None``（預設）：沿用所屬 ``AsyncModbusDevice`` 的 ``DeviceConfig.unit_id``
            - ``int``：覆寫至指定 unit（SMA 風格 multi-unit device）

        群組內所有 points 的 ``unit_id`` 必須一致（``__post_init__`` 驗證）。
    """

    function_code: int
    start_address: int
    count: int
    points: tuple[ReadPoint, ...] = field(default_factory=tuple)
    unit_id: int | None = None

    def __post_init__(self) -> None:
        if not self.points:
            return
        effective = {p.unit_id for p in self.points}
        if len(effective) > 1:
            raise ValueError(
                f"ReadGroup 內 points unit_id 不一致: {sorted(str(u) for u in effective)} "
                f"(fc={self.function_code}, addr={self.start_address})"
            )
        point_uid = next(iter(effective))
        if self.unit_id is not None and point_uid is not None and point_uid != self.unit_id:
            raise ValueError(
                f"ReadGroup.unit_id={self.unit_id} 與 points unit_id={point_uid} 不一致 "
                f"(fc={self.function_code}, addr={self.start_address})"
            )


class PointGrouper:
    """
    點位分組器

    將點位合併成群組以減少請求次數。

    使用範例：
        grouper = PointGrouper()
        groups = grouper.group(points)
    """

    def __init__(self, config: PointGrouperConfig | None = None) -> None:
        self._config = config or PointGrouperConfig()

    def group(self, points: Sequence[ReadPoint]) -> list[ReadGroup]:
        """
        計算點位分組

        Args:
            points: 點位列表

        Returns:
            分組後的 ReadGroup 列表
        """
        if not points:
            return []

        # unit_id=None 與 int 不可直接排序，用 -1 作為 None 的 sort sentinel
        # （真實 unit_id 合法範圍 0-255，-1 不會衝突）
        def _sort_key(p: ReadPoint) -> tuple[int, str, int, int]:
            uid_key = -1 if p.unit_id is None else p.unit_id
            fc_key = int(p.function_code) if p.function_code is not None else -1
            return (uid_key, p.read_group, fc_key, p.address)

        def _bucket_key(p: ReadPoint) -> tuple[int | None, str, int]:
            fc_key = int(p.function_code) if p.function_code is not None else -1
            return (p.unit_id, p.read_group, fc_key)

        sorted_points = sorted(points, key=_sort_key)

        groups: list[ReadGroup] = []

        for (unit_id, _, function_code), function_point in groupby(sorted_points, key=_bucket_key):
            groups.extend(self._merge_consecutive(list(function_point), function_code, unit_id=unit_id))

        return groups

    def _merge_consecutive(
        self,
        points: list[ReadPoint],
        function_code: int,
        max_length: int | None = None,
        unit_id: int | None = None,
    ) -> list[ReadGroup]:
        """
        合併連續點位成群組

        Args:
            points: 已排序的點位列表
            function_code: 功能碼
            max_length: 最大讀取長度（可選）

        Returns:
            合併後的 ReadGroup 列表
        """
        max_length = max_length or self._config.fc_max_length.get(function_code, 125)
        groups: list[ReadGroup] = []

        current: list[ReadPoint] = []
        start = 0
        end = 0

        for point in points:
            p_start = point.address
            p_end = p_start + point.data_type.register_count

            if not current:
                current, start, end = [point], p_start, p_end
                continue

            if p_end - start <= max_length:
                current.append(point)
                end = max(end, p_end)
                continue

            groups.append(
                ReadGroup(
                    function_code=function_code,
                    start_address=start,
                    count=end - start,
                    points=tuple(current),
                    unit_id=unit_id,
                )
            )
            # 重置狀態，開始新群組
            current, start, end = [point], p_start, p_end

        if current:
            groups.append(
                ReadGroup(
                    function_code=function_code,
                    start_address=start,
                    count=end - start,
                    points=tuple(current),
                    unit_id=unit_id,
                )
            )

        return groups


__all__ = [
    "PointGrouper",
    "ReadGroup",
]
