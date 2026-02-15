# =============== Integration - Schema ===============
#
# 映射資料結構
#
# 定義 Equipment ↔ Controller 之間的映射規格：
#   - AggregateFunc: 多設備值聚合函式
#   - ContextMapping: 設備點位 → StrategyContext 欄位
#   - CommandMapping: Command 欄位 → 設備寫入
#   - DataFeedMapping: 設備點位 → PV 資料餵入

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class AggregateFunc(Enum):
    """
    內建聚合函式

    用於多設備 (trait 模式) 值的合併策略：
    - AVERAGE: 平均值
    - SUM: 加總
    - MIN: 最小值
    - MAX: 最大值
    - FIRST: 取排序後第一台設備的值
    """

    AVERAGE = "average"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    FIRST = "first"


def _validate_device_or_trait(device_id: str | None, trait: str | None) -> None:
    """驗證 device_id 與 trait 必須恰好設定其一"""
    if device_id is not None and trait is not None:
        raise ValueError("Cannot set both device_id and trait; choose exactly one.")
    if device_id is None and trait is None:
        raise ValueError("Must set either device_id or trait; neither was provided.")


@dataclass(frozen=True)
class ContextMapping:
    """
    設備點位 → StrategyContext 欄位映射

    將設備的讀取值映射到策略上下文中的特定欄位。
    ``device_id`` 模式用於單一設備讀取；``trait`` 模式用於多設備聚合。
    兩者必須恰好設定其一。

    Attributes:
        point_name: 設備點位名稱 (對應 device.latest_values 的 key)
        context_field: 目標 context 欄位 ("soc" | "extra.xxx")
        device_id: 指定單一設備 ID（與 trait 擇一）
        trait: 指定 trait 標籤，匹配所有同 trait 設備（與 device_id 擇一）
        aggregate: 多設備聚合函式（僅 trait 模式有效）
        custom_aggregate: 自訂聚合函式，優先於 aggregate
        default: 無法取得有效值時的預設值
        transform: 值轉換函式，套用於聚合結果之後
    """

    point_name: str
    context_field: str
    device_id: str | None = None
    trait: str | None = None
    aggregate: AggregateFunc = AggregateFunc.AVERAGE
    custom_aggregate: Callable[[list[Any]], Any] | None = None
    default: Any = None
    transform: Callable[[Any], Any] | None = None

    def __post_init__(self) -> None:
        _validate_device_or_trait(self.device_id, self.trait)


@dataclass(frozen=True)
class CommandMapping:
    """
    Command 欄位 → 設備寫入映射

    將策略輸出的 Command 欄位路由到設備寫入操作。
    ``device_id`` 模式寫入單一設備；``trait`` 模式廣播寫入所有匹配設備。
    兩者必須恰好設定其一。

    Attributes:
        command_field: Command 屬性名稱 ("p_target" | "q_target")
        point_name: 目標設備寫入點位名稱
        device_id: 指定單一設備 ID（與 trait 擇一）
        trait: 指定 trait 標籤，廣播寫入所有匹配設備（與 device_id 擇一）
        transform: 值轉換函式，寫入前套用（例如均分功率）
    """

    command_field: str
    point_name: str
    device_id: str | None = None
    trait: str | None = None
    transform: Callable[[float], Any] | None = None

    def __post_init__(self) -> None:
        _validate_device_or_trait(self.device_id, self.trait)


@dataclass(frozen=True)
class DataFeedMapping:
    """
    PV 資料餵入映射

    指定哪台設備的哪個點位作為 PV 發電功率資料來源，餵入 PVDataService。
    ``device_id`` 模式指定特定設備；``trait`` 模式取第一台 responsive 設備。
    兩者必須恰好設定其一。

    Attributes:
        point_name: PV 功率點位名稱
        device_id: 指定單一設備 ID（與 trait 擇一）
        trait: 指定 trait 標籤，取第一台 responsive 設備（與 device_id 擇一）
    """

    point_name: str
    device_id: str | None = None
    trait: str | None = None

    def __post_init__(self) -> None:
        _validate_device_or_trait(self.device_id, self.trait)
