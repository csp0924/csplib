# =============== Integration - Context Builder ===============
#
# 設備值 → StrategyContext 建構器
#
# 透過 ContextMapping 將設備的 latest_values 映射到 StrategyContext：
#   - device_id 模式：直接讀取單一設備
#   - trait 模式：收集所有匹配設備的值並聚合
#   - 簽名 Callable[[], StrategyContext] 完全符合 StrategyExecutor 的 context_provider

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from csp_lib.controller.core import Command, StrategyContext, SystemBase
from csp_lib.core import get_logger

from .registry import DeviceRegistry
from .schema import AggregateFunc, CapabilityContextMapping, ContextMapping

if TYPE_CHECKING:
    from csp_lib.core.runtime_params import RuntimeParameters

logger = get_logger("csp_lib.integration.context_builder")


def apply_builtin_aggregate(func: AggregateFunc, values: list[Any]) -> Any:
    """
    套用內建聚合函式

    Args:
        func: 聚合函式類型
        values: 待聚合的值列表（已過濾 None）

    Returns:
        聚合結果；空列表時回傳 None
    """
    if not values:
        return None
    if func == AggregateFunc.AVERAGE:
        return sum(values) / len(values)
    if func == AggregateFunc.SUM:
        return sum(values)
    if func == AggregateFunc.MIN:
        return min(values)
    if func == AggregateFunc.MAX:
        return max(values)
    if func == AggregateFunc.FIRST:
        return values[0]
    return None  # pragma: no cover


class ContextBuilder:
    """
    設備值 → StrategyContext 建構器

    透過 ContextMapping 列表，從 DeviceRegistry 中的設備讀取點位值，
    映射並聚合後填入 StrategyContext。

    設計為 StrategyExecutor 的 ``context_provider`` 參數。
    ``build()`` 的簽名 ``Callable[[], StrategyContext]`` 完全符合該介面。

    注意：
        - ``last_command`` / ``current_time`` 不由此處設定，
          由 StrategyExecutor._execute_strategy 自行注入
        - ``latest_values`` 回傳 copy，無競態問題
    """

    def __init__(
        self,
        registry: DeviceRegistry,
        mappings: list[ContextMapping],
        system_base: SystemBase | None = None,
        capability_mappings: list[CapabilityContextMapping] | None = None,
        runtime_params: RuntimeParameters | None = None,
    ) -> None:
        """
        初始化建構器

        Args:
            registry: 設備查詢索引
            mappings: 設備點位 → context 欄位的映射列表
            system_base: 系統基準值（可選），設定於 context.system_base
            capability_mappings: capability-driven context 映射列表（可選）
            runtime_params: 系統參數（可選），直接引用掛到 context.params
        """
        self._registry = registry
        self._mappings = mappings
        self._system_base = system_base
        self._capability_mappings = capability_mappings or []
        self._runtime_params = runtime_params

    def build(self) -> StrategyContext:
        """
        建構 StrategyContext

        遍歷所有 ContextMapping，解析設備值並填入對應的 context 欄位。

        Returns:
            填入設備值的 StrategyContext 實例
        """
        ctx = StrategyContext(
            last_command=Command(),
            system_base=self._system_base,
            params=self._runtime_params,
        )

        for mapping in self._mappings:
            value = self._resolve_value(mapping)
            self._set_context_field(ctx, mapping.context_field, value)

        for cap_mapping in self._capability_mappings:
            value = self._resolve_capability_value(cap_mapping)
            self._set_context_field(ctx, cap_mapping.context_field, value)

        return ctx

    def _resolve_value(self, mapping: ContextMapping) -> Any:
        """
        解析單一映射的值

        流程：
        1. 依 device_id 或 trait 模式取得原始值
        2. 原始值為 None → 回傳 mapping.default
        3. 套用 transform（若有），例外時回傳 default 並 log warning
        """
        if mapping.device_id is not None:
            raw = self._read_single_device(mapping)
        else:
            raw = self._read_trait_aggregate(mapping)

        # 無有效值 → 使用預設值
        if raw is None:
            return mapping.default

        # 套用轉換函式
        if mapping.transform is not None:
            try:
                raw = mapping.transform(raw)
            except Exception:
                logger.warning(f"Transform failed for mapping '{mapping.context_field}', using default.")
                return mapping.default

        return raw

    def _read_single_device(self, mapping: ContextMapping) -> Any:
        """device_id 模式：讀取單一設備的點位值"""
        device = self._registry.get_device(mapping.device_id)  # type: ignore[arg-type]
        if device is None or not device.is_responsive:
            return None
        return device.latest_values.get(mapping.point_name)

    def _read_trait_aggregate(self, mapping: ContextMapping) -> Any:
        """
        trait 模式：收集所有 responsive 設備的值並聚合

        流程：
        1. 取得所有 responsive 設備
        2. 收集各設備的點位值，過濾 None
        3. custom_aggregate 優先；否則使用內建 aggregate
        4. 聚合例外或全 None → 回傳 None（由上層轉為 default）
        """
        devices = self._registry.get_responsive_devices_by_trait(mapping.trait)  # type: ignore[arg-type]
        if not devices:
            return None

        # 收集有效值（過濾 None）
        values = []
        for device in devices:
            v = device.latest_values.get(mapping.point_name)
            if v is not None:
                values.append(v)

        if not values:
            return None

        # 自訂聚合優先
        if mapping.custom_aggregate is not None:
            try:
                return mapping.custom_aggregate(values)
            except Exception:
                logger.warning(f"Custom aggregate failed for mapping '{mapping.context_field}', using default.")
                return None

        return apply_builtin_aggregate(mapping.aggregate, values)

    def _resolve_capability_value(self, mapping: CapabilityContextMapping) -> Any:
        """解析 capability-driven mapping 的值"""
        if mapping.device_id is not None:
            raw = self._read_capability_single(mapping)
        elif mapping.trait is not None:
            raw = self._read_capability_trait(mapping)
        else:
            raw = self._read_capability_auto(mapping)

        if raw is None:
            return mapping.default

        if mapping.transform is not None:
            try:
                raw = mapping.transform(raw)
            except Exception:
                logger.warning(f"Transform failed for capability mapping '{mapping.context_field}', using default.")
                return mapping.default

        return raw

    def _read_capability_single(self, mapping: CapabilityContextMapping) -> Any:
        """單一設備：resolve_point → latest_values"""
        device = self._registry.get_device(mapping.device_id)  # type: ignore[arg-type]
        if device is None or not device.is_responsive:
            return None
        if not device.has_capability(mapping.capability):
            return None
        point_name = device.resolve_point(mapping.capability, mapping.slot)
        return device.latest_values.get(point_name)

    def _read_capability_trait(self, mapping: CapabilityContextMapping) -> Any:
        """trait 模式：過濾 responsive + has_capability"""
        devices = self._registry.get_responsive_devices_by_trait(mapping.trait)  # type: ignore[arg-type]
        if not devices:
            return None
        capable = [d for d in devices if d.has_capability(mapping.capability)]
        return self._aggregate_capability_values(capable, mapping)

    def _read_capability_auto(self, mapping: CapabilityContextMapping) -> Any:
        """自動發現：所有具備該 capability 的 responsive 設備"""
        devices = self._registry.get_responsive_devices_with_capability(mapping.capability)
        if not devices:
            return None
        return self._aggregate_capability_values(devices, mapping)

    def _aggregate_capability_values(self, devices: list, mapping: CapabilityContextMapping) -> Any:
        """聚合多設備的 capability 值"""
        values = []
        for device in devices:
            point_name = device.resolve_point(mapping.capability, mapping.slot)
            v = device.latest_values.get(point_name)
            if v is not None:
                values.append(v)

        if not values:
            return None

        if mapping.custom_aggregate is not None:
            try:
                return mapping.custom_aggregate(values)
            except Exception:
                logger.warning(
                    f"Custom aggregate failed for capability mapping '{mapping.context_field}', using default."
                )
                return None

        return apply_builtin_aggregate(mapping.aggregate, values)

    @staticmethod
    def _set_context_field(ctx: StrategyContext, field: str, value: Any) -> None:
        """
        設定 StrategyContext 欄位值

        支援點號路徑：
        - "soc" → ctx.soc = value
        - "extra.xxx" → ctx.extra["xxx"] = value
        """
        if field.startswith("extra."):
            key = field[len("extra.") :]
            ctx.extra[key] = value
        else:
            setattr(ctx, field, value)
