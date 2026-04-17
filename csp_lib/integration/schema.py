# =============== Integration - Schema ===============
#
# 映射資料結構
#
# 定義 Equipment ↔ Controller 之間的映射規格：
#   - AggregateFunc: 多設備值聚合函式
#   - ContextMapping: 設備點位 → StrategyContext 欄位
#   - CommandMapping: Command 欄位 → 設備寫入
#   - DataFeedMapping: 設備點位 → PV 資料餵入
#   - CapabilityContextMapping: Capability-driven context 映射（含 min_device_ratio 品質門檻）
#   - CapabilityCommandMapping: Capability-driven command 映射
#   - CapabilityRequirement: 能力需求定義（preflight validation）
#   - AggregationResult: 聚合結果（附帶品質資訊）

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from csp_lib.equipment.device.capability import Capability


def capability_display_name(capability: Any) -> str:
    """取得 capability 的顯示名稱（name 屬性優先，否則 str）"""
    return capability.name if hasattr(capability, "name") else str(capability)


class HeartbeatMode(Enum):
    """
    心跳寫入值模式

    - TOGGLE: 交替 0/1
    - INCREMENT: 遞增計數（到 max 後歸零）
    - CONSTANT: 固定值
    """

    TOGGLE = "toggle"
    INCREMENT = "increment"
    CONSTANT = "constant"


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


def _validate_context_source(
    device_id: str | None,
    trait: str | None,
    param_key: str | None,
) -> None:
    """驗證 ContextMapping 的三擇一來源：device_id / trait / param_key。

    v0.8.0 起 ContextMapping 支援從 RuntimeParameters 讀值（``param_key``），
    與設備讀取（device_id / trait）互斥 — 三者恰好設定其一。
    """
    sources = [s for s in (device_id, trait, param_key) if s is not None]
    if len(sources) > 1:
        raise ValueError("Cannot set more than one of device_id / trait / param_key; choose exactly one.")
    if not sources:
        raise ValueError("Must set exactly one of device_id / trait / param_key; none was provided.")


@dataclass(frozen=True, slots=True)
class ContextMapping:
    """
    設備點位 / RuntimeParameters → StrategyContext 欄位映射

    將設備的讀取值或 RuntimeParameters 中的參數映射到策略上下文中的特定欄位。
    ``device_id`` 模式用於單一設備讀取；``trait`` 模式用於多設備聚合；
    ``param_key``（v0.8.0+）模式用於從 RuntimeParameters 讀值。三者必須恰好設定其一。

    Attributes:
        point_name: 設備點位名稱（對應 ``device.latest_values`` 的 key）。
            param_key 模式下此欄位不會被用到，但為相容既有 builder 介面仍需設值。
        context_field: 目標 context 欄位（"soc" | "extra.xxx"）
        device_id: 指定單一設備 ID（與 trait / param_key 擇一）
        trait: 指定 trait 標籤，匹配所有同 trait 設備（與 device_id / param_key 擇一）
        param_key: v0.8.0+ 新增。指定 ``RuntimeParameters`` 的 key，從 params 讀值
            （與 device_id / trait 擇一）。requires ContextBuilder 以 ``runtime_params`` 建構；
            否則會 log warning 並回退至 ``default``。
        aggregate: 多設備聚合函式（僅 trait 模式有效）
        custom_aggregate: 自訂聚合函式，優先於 aggregate
        default: 無法取得有效值時的預設值
        transform: 值轉換函式，套用於聚合結果之後
    """

    point_name: str
    context_field: str
    device_id: str | None = None
    trait: str | None = None
    param_key: str | None = None
    aggregate: AggregateFunc = AggregateFunc.AVERAGE
    custom_aggregate: Callable[[list[Any]], Any] | None = None
    default: Any = None
    transform: Callable[[Any], Any] | None = None

    def __post_init__(self) -> None:
        _validate_context_source(self.device_id, self.trait, self.param_key)


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
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
    aggregate: AggregateFunc = AggregateFunc.FIRST

    def __post_init__(self) -> None:
        _validate_device_or_trait(self.device_id, self.trait)


@dataclass(frozen=True, slots=True)
class HeartbeatMapping:
    """
    心跳寫入映射

    定義控制器對設備的心跳（看門狗）寫入規格。
    控制器定期寫入心跳值，設備端若超時未收到則進入安全模式。

    ``device_id`` 模式寫入單一設備；``trait`` 模式廣播寫入所有匹配設備。
    兩者必須恰好設定其一。

    Attributes:
        point_name: 心跳寫入點位名稱
        device_id: 指定單一設備 ID（與 trait 擇一）
        trait: 指定 trait 標籤，廣播寫入所有匹配設備（與 device_id 擇一）
        mode: 心跳值模式（toggle / increment / constant）
        constant_value: CONSTANT 模式的固定寫入值
        increment_max: INCREMENT 模式的最大計數值（到達後歸零）
    """

    point_name: str
    device_id: str | None = None
    trait: str | None = None
    mode: HeartbeatMode = HeartbeatMode.TOGGLE
    constant_value: int = 1
    increment_max: int = 65535

    def __post_init__(self) -> None:
        _validate_device_or_trait(self.device_id, self.trait)


@dataclass(frozen=True, slots=True)
class CapabilityContextMapping:
    """
    Capability-driven context mapping.

    用 capability 的 read slot 取代明確的 point_name。
    實際點位名稱由各設備的 CapabilityBinding 自動解析。

    Scoping:
    - device_id: 讀取單一設備
    - trait: 讀取同 trait 且具備該 capability 的所有設備
    - 皆不設: 自動發現所有具備該 capability 的設備

    Attributes:
        capability: 目標能力
        slot: capability 的 read slot 名稱
        context_field: 目標 context 欄位 ("soc" | "extra.xxx")
        device_id: 指定單一設備 ID（與 trait 擇一，或皆不設）
        trait: 指定 trait 標籤（與 device_id 擇一，或皆不設）
        aggregate: 多設備聚合函式（trait / auto 模式有效）
        custom_aggregate: 自訂聯合函式，優先於 aggregate
        default: 無法取得有效值時的預設值
        transform: 值轉換函式，套用於聚合結果之後
        min_device_ratio: 最低設備響應比例（0.0~1.0），低於此比例時回傳 default 並發出警告
    """

    capability: Capability
    slot: str
    context_field: str
    device_id: str | None = None
    trait: str | None = None
    aggregate: AggregateFunc = AggregateFunc.AVERAGE
    custom_aggregate: Callable[[list[Any]], Any] | None = None
    default: Any = None
    transform: Callable[[Any], Any] | None = None
    min_device_ratio: float = 0.0

    def __post_init__(self) -> None:
        if self.device_id is not None and self.trait is not None:
            raise ValueError("Cannot set both device_id and trait.")
        if self.slot not in self.capability.read_slots:
            raise ValueError(
                f"Slot '{self.slot}' not in capability '{self.capability.name}' "
                f"read_slots: {self.capability.read_slots}"
            )


@dataclass(frozen=True, slots=True)
class CapabilityCommandMapping:
    """
    Capability-driven command mapping.

    用 capability 的 write slot 取代明確的 point_name。
    實際點位名稱由各設備的 CapabilityBinding 自動解析。

    Scoping:
    - device_id: 寫入單一設備
    - trait: 廣播寫入同 trait 且具備該 capability 的所有設備
    - 皆不設: 自動發現所有具備該 capability 的設備

    Attributes:
        command_field: Command 屬性名稱
        capability: 目標能力
        slot: capability 的 write slot 名稱
        device_id: 指定單一設備 ID（與 trait 擇一，或皆不設）
        trait: 指定 trait 標籤（與 device_id 擇一，或皆不設）
        transform: 值轉換函式，寫入前套用
    """

    command_field: str
    capability: Capability
    slot: str
    device_id: str | None = None
    trait: str | None = None
    transform: Callable[[float], Any] | None = None

    def __post_init__(self) -> None:
        if self.device_id is not None and self.trait is not None:
            raise ValueError("Cannot set both device_id and trait.")
        if self.slot not in self.capability.write_slots:
            raise ValueError(
                f"Slot '{self.slot}' not in capability '{self.capability.name}' "
                f"write_slots: {self.capability.write_slots}"
            )


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """能力需求定義 — 供 preflight validation 使用

    Attributes:
        capability: 必要的設備能力
        min_count: 最少設備數量（預設 1）
        trait_filter: 限定特定 trait 的設備（None = 搜尋所有設備）
    """

    capability: Capability
    min_count: int = 1
    trait_filter: str | None = None


@dataclass(frozen=True, slots=True)
class AggregationResult:
    """聚合結果 — 附帶品質資訊

    Attributes:
        value: 聚合計算結果
        device_count: 實際參與聚合的設備數
        expected_count: 預期設備數（Registry 中該 capability 的總設備數）
    """

    value: Any
    device_count: int
    expected_count: int

    @property
    def quality_ratio(self) -> float:
        """device_count / expected_count，expected_count <= 0 時回傳 1.0"""
        if self.expected_count <= 0:
            return 1.0
        return self.device_count / self.expected_count
