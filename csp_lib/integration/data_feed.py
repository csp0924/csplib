# =============== Integration - Data Feed ===============
#
# 設備事件 → PVDataService 資料餵入
#
# 訂閱單一設備的 read_complete 事件，將 PV 功率值餵入 PVDataService：
#   - device_id 模式：訂閱指定設備
#   - trait 模式：訂閱第一台 responsive 設備
#   - 自行實作 subscribe/unsubscribe 模式，避免 import csp_lib.manager（含可選依賴）

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from csp_lib.core import get_logger
from csp_lib.equipment.device import EVENT_READ_COMPLETE

from .registry import DeviceRegistry
from .schema import DataFeedMapping

if TYPE_CHECKING:
    from csp_lib.controller.services import PVDataService
    from csp_lib.equipment.device import AsyncModbusDevice, ReadCompletePayload

logger = get_logger("csp_lib.integration.data_feed")


class DeviceDataFeed:
    """
    設備事件 → PVDataService 資料餵入

    訂閱單一設備的 ``read_complete`` 事件，將指定點位的值餵入 PVDataService。
    透過 DataFeedMapping 指定目標設備（device_id 或 trait 模式）。

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
        self._device: AsyncModbusDevice | None = None
        self._unsubscribes: list[Callable[[], None]] = []  # 取消訂閱的 callback 列表

    def attach(self) -> None:
        """
        解析目標設備並訂閱 read_complete 事件

        device_id 模式直接查詢；trait 模式取第一台 responsive 設備。
        無法解析時 log warning 並跳過。
        """
        device = self._resolve_device()
        if device is None:
            logger.warning("DeviceDataFeed: no device resolved, data feed not attached.")
            return
        self._device = device
        self._unsubscribes = [device.on(EVENT_READ_COMPLETE, self._on_read_complete)]

    def detach(self) -> None:
        """取消訂閱當前設備的事件"""
        for unsub in self._unsubscribes:
            unsub()
        self._unsubscribes.clear()
        self._device = None

    def _resolve_device(self) -> AsyncModbusDevice | None:
        """依映射設定解析目標設備"""
        if self._mapping.device_id is not None:
            return self._registry.get_device(self._mapping.device_id)
        return self._registry.get_first_responsive_device_by_trait(self._mapping.trait)  # type: ignore[arg-type]

    async def _on_read_complete(self, payload: ReadCompletePayload) -> None:
        """
        read_complete 事件處理

        將點位值餵入 PVDataService：
        - 數值型 (int/float) → append(float(value))
        - 非數值或缺失 → append(None)
        """
        value = payload.values.get(self._mapping.point_name)
        if isinstance(value, (int, float)):
            self._pv_service.append(float(value))
        else:
            self._pv_service.append(None)
