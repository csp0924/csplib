# =============== Equipment Template - Definition ===============
#
# 設備範本定義
#
# 提供可重用的設備模型定義：
#   - PointOverride: 點位名稱覆寫（IO 模組場景）
#   - EquipmentTemplate: 不可變設備模型範本

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from csp_lib.core.errors import ConfigurationError

if TYPE_CHECKING:
    from csp_lib.equipment.alarm import AlarmEvaluator
    from csp_lib.equipment.core import PointMetadata, ReadPoint, WritePoint
    from csp_lib.equipment.device.capability import CapabilityBinding
    from csp_lib.equipment.processing import AggregatorPipeline


@dataclass(frozen=True)
class PointOverride:
    """
    點位覆寫定義

    用於重新命名點位及更新元資料（IO 模組場景）。

    Attributes:
        name: 新的點位名稱
        metadata: 新的點位元資料（可選）
    """

    name: str
    metadata: PointMetadata | None = None


@dataclass(frozen=True)
class EquipmentTemplate:
    """
    不可變設備模型範本

    定義可重用的設備模型，包含點位、告警、聚合器等。
    不包含 DeviceConfig（每個實例各自設定）。

    Attributes:
        model: 設備型號名稱（如 "SUN2000-100KTL"）
        always_points: 每次讀取的點位
        rotating_points: 輪詢點位群組
        write_points: 寫入點位
        alarm_evaluators: 告警評估器
        aggregator_pipeline: 聚合處理管線（可選）
        description: 設備描述
    """

    model: str
    always_points: tuple[ReadPoint, ...] = ()
    rotating_points: tuple[tuple[ReadPoint, ...], ...] = ()
    write_points: tuple[WritePoint, ...] = ()
    alarm_evaluators: tuple[AlarmEvaluator, ...] = ()
    aggregator_pipeline: AggregatorPipeline | None = None
    capability_bindings: tuple[CapabilityBinding, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        """驗證所有能力綁定的點位名稱確實存在於範本中"""
        if not self.capability_bindings:
            return

        read_names: set[str] = set()
        for p in self.always_points:
            read_names.add(p.name)
        for group in self.rotating_points:
            for p in group:
                read_names.add(p.name)
        write_names = {p.name for p in self.write_points}

        for binding in self.capability_bindings:
            cap = binding.capability
            for slot in cap.write_slots:
                actual = binding.point_map[slot]
                if actual not in write_names:
                    raise ConfigurationError(
                        f"Template '{self.model}': capability '{cap.name}' slot '{slot}' "
                        f"maps to write point '{actual}' which does not exist. "
                        f"Available: {sorted(write_names)}"
                    )
            for slot in cap.read_slots:
                actual = binding.point_map[slot]
                if actual not in read_names:
                    raise ConfigurationError(
                        f"Template '{self.model}': capability '{cap.name}' slot '{slot}' "
                        f"maps to read point '{actual}' which does not exist. "
                        f"Available: {sorted(read_names)}"
                    )


__all__ = [
    "PointOverride",
    "EquipmentTemplate",
]
