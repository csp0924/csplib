# =============== Cluster - Virtual Context Builder ===============
#
# 從 Redis 資料建構 StrategyContext（取代 live 設備讀取）
#
# Follower 使用此 builder 從 ClusterStateSubscriber 的快取資料
# 建構 StrategyContext，與 ContextBuilder.build() 相同簽名。

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from csp_lib.controller.core import Command, StrategyContext, SystemBase
from csp_lib.core import get_logger
from csp_lib.integration.context_builder import _apply_builtin_aggregate
from csp_lib.integration.schema import ContextMapping

logger = get_logger("csp_lib.cluster.context")


@runtime_checkable
class DeviceStateProvider(Protocol):
    """提供設備狀態資料的 Protocol（ClusterStateSubscriber / DeviceStateSubscriber 皆滿足）"""

    @property
    def device_states(self) -> dict[str, dict[str, Any]]: ...


class VirtualContextBuilder:
    """
    虛擬 Context 建構器

    從 DeviceStateProvider 的快取設備資料建構 StrategyContext，
    作為 ContextBuilder.build() 的 drop-in 替代。

    用於 Follower 模式或分散式模式：不連接實體設備，改從 Redis 同步的資料建構 context。
    """

    def __init__(
        self,
        subscriber: DeviceStateProvider,
        mappings: list[ContextMapping],
        system_base: SystemBase | None = None,
        trait_device_map: dict[str, list[str]] | None = None,
    ) -> None:
        """
        初始化虛擬 context builder

        Args:
            subscriber: 設備資料提供者（提供 device_states 屬性）
            mappings: 設備點位 → context 欄位的映射列表
            system_base: 系統基準值（可選）
            trait_device_map: trait → device_id 列表的映射（可選，trait 模式用）
        """
        self._subscriber = subscriber
        self._mappings = mappings
        self._system_base = system_base
        self._trait_device_map = trait_device_map or {}

    def build(self) -> StrategyContext:
        """
        建構 StrategyContext

        從 subscriber 快取的設備資料解析值並填入 context。
        """
        ctx = StrategyContext(
            last_command=Command(),
            system_base=self._system_base,
        )

        for mapping in self._mappings:
            value = self._resolve_value(mapping)
            _set_context_field(ctx, mapping.context_field, value)

        return ctx

    def _resolve_value(self, mapping: ContextMapping) -> Any:
        """解析單一映射的值"""
        if mapping.device_id is not None:
            raw = self._read_single_device(mapping)
        else:
            raw = self._read_trait_aggregate(mapping)

        if raw is None:
            return mapping.default

        if mapping.transform is not None:
            try:
                raw = mapping.transform(raw)
            except Exception:
                logger.warning(f"Transform failed for mapping '{mapping.context_field}', using default.")
                return mapping.default

        return raw

    def _read_single_device(self, mapping: ContextMapping) -> Any:
        """從快取讀取單一設備的點位值"""
        device_id = mapping.device_id
        if device_id is None:
            return None

        device_state = self._subscriber.device_states.get(device_id)
        if not device_state:
            return None

        return device_state.get(mapping.point_name)

    def _read_trait_aggregate(self, mapping: ContextMapping) -> Any:
        """從快取讀取 trait 下所有設備的點位值並聚合"""
        trait = mapping.trait
        if trait is None:
            return None

        device_ids = self._trait_device_map.get(trait, [])
        if not device_ids:
            return None

        values = []
        for device_id in device_ids:
            device_state = self._subscriber.device_states.get(device_id)
            if device_state:
                v = device_state.get(mapping.point_name)
                if v is not None:
                    values.append(v)

        if not values:
            return None

        if mapping.custom_aggregate is not None:
            try:
                return mapping.custom_aggregate(values)
            except Exception:
                logger.warning(f"Custom aggregate failed for mapping '{mapping.context_field}', using default.")
                return None

        return _apply_builtin_aggregate(mapping.aggregate, values)


def _set_context_field(ctx: StrategyContext, field: str, value: Any) -> None:
    """設定 StrategyContext 欄位值（與 ContextBuilder._set_context_field 相同邏輯）"""
    if field.startswith("extra."):
        key = field[len("extra.") :]
        ctx.extra[key] = value
    else:
        setattr(ctx, field, value)


__all__ = [
    "DeviceStateProvider",
    "VirtualContextBuilder",
]
