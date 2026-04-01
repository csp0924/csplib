# =============== Integration - Data Feed ===============
#
# 設備事件 → PVDataService 資料餵入
#
# 訂閱設備的 read_complete 事件，將 PV 功率值餵入 PVDataService：
#   - device_id 模式：訂閱指定設備，直接餵入該設備值
#   - trait 模式：訂閱所有匹配設備，依 aggregate 函式聚合後餵入
#   - 自行實作 subscribe/unsubscribe 模式，避免 import csp_lib.manager（含可選依賴）

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from csp_lib.core import get_logger
from csp_lib.equipment.device import EVENT_READ_COMPLETE

from .registry import DeviceRegistry
from .schema import AggregateFunc, DataFeedMapping

if TYPE_CHECKING:
    from csp_lib.controller.services import PVDataService
    from csp_lib.equipment.device import ReadCompletePayload

logger = get_logger(__name__)


class DeviceDataFeed:
    """
    設備事件 → PVDataService 資料餵入

    訂閱設備的 ``read_complete`` 事件，將指定點位的值餵入 PVDataService。
    透過 DataFeedMapping 指定目標設備（device_id 或 trait 模式）。

    - device_id 模式：訂閱單一設備，直接餵入該設備的點位值
    - trait 模式：訂閱所有匹配設備，任一設備觸發 read_complete 時
      從所有 responsive 設備收集值並聚合（預設 FIRST，可設為 SUM 等）

    實作與 ``DeviceEventSubscriber`` 相同的 subscribe/unsubscribe 模式，
    但不繼承該類別以避免 import csp_lib.manager（其 __init__ 會載入可選依賴 motor）。
    """

    def __init__(self, registry: DeviceRegistry, mapping: DataFeedMapping, pv_service: PVDataService) -> None:
        """
        初始化資料餵入器

        Args:
            registry: 設備查詢索引
            mapping: PV 資料來源映射
            pv_service: PV 資料服務，接收 append() 呼叫
        """
        self._registry = registry
        self._mapping = mapping
        self._pv_service = pv_service
        self._unsubscribes: list[Callable[[], None]] = []

    def attach(self) -> None:
        """
        解析目標設備並訂閱 read_complete 事件

        device_id 模式：訂閱指定設備。
        trait 模式：訂閱所有匹配設備（含非 responsive），
        任一設備 read_complete 時觸發聚合計算。
        無法解析時 log warning 並跳過。

        部分訂閱失敗時自動回滾已完成的訂閱，避免洩漏。
        """
        if self._mapping.device_id is not None:
            device = self._registry.get_device(self._mapping.device_id)
            if device is None:
                logger.warning(
                    "DeviceDataFeed: device '%s' not found, data feed not attached.", self._mapping.device_id
                )
                return
            self._unsubscribes = [device.on(EVENT_READ_COMPLETE, self._on_read_complete)]
        else:
            devices = self._registry.get_devices_by_trait(self._mapping.trait)  # type: ignore[arg-type]
            if not devices:
                logger.warning(
                    "DeviceDataFeed: no devices with trait '%s', data feed not attached.", self._mapping.trait
                )
                return
            pending: list[Callable[[], None]] = []
            try:
                for device in devices:
                    pending.append(device.on(EVENT_READ_COMPLETE, self._on_read_complete))
            except Exception:
                logger.opt(exception=True).warning(
                    "DeviceDataFeed: partial subscribe failure for trait '%s', rolling back.", self._mapping.trait
                )
                for unsub in pending:
                    unsub()
                return
            self._unsubscribes.extend(pending)

    def detach(self) -> None:
        """取消訂閱所有設備的事件"""
        for unsub in self._unsubscribes:
            unsub()
        self._unsubscribes.clear()

    async def _on_read_complete(self, payload: ReadCompletePayload) -> None:
        """
        read_complete 事件處理

        device_id 模式：直接餵入 payload 中的值。
        trait 模式：從所有 responsive 設備收集值並聚合。
        """
        if self._mapping.device_id is not None:
            value = payload.values.get(self._mapping.point_name)
            if isinstance(value, (int, float)):
                self._pv_service.append(float(value))
            else:
                self._pv_service.append(None)
        else:
            self._feed_trait_aggregate()

    def _feed_trait_aggregate(self) -> None:
        """從所有 responsive 設備收集值，聚合後餵入 PVDataService"""
        devices = self._registry.get_responsive_devices_by_trait(self._mapping.trait)  # type: ignore[arg-type]
        values: list[float] = []
        for device in devices:
            v = device.latest_values.get(self._mapping.point_name)
            if isinstance(v, (int, float)):
                values.append(float(v))

        if not values:
            self._pv_service.append(None)
            return

        self._pv_service.append(self._apply_aggregate(values))

    def _apply_aggregate(self, values: list[float]) -> float:
        """套用聚合函式"""
        func = self._mapping.aggregate
        if func == AggregateFunc.SUM:
            return sum(values)
        if func == AggregateFunc.AVERAGE:
            return sum(values) / len(values)
        if func == AggregateFunc.MIN:
            return min(values)
        if func == AggregateFunc.MAX:
            return max(values)
        # FIRST
        return values[0]
