# =============== Integration - Data Feed ===============
#
# 設備事件 → HistoryBuffer 資料餵入
#
# 訂閱設備的 read_complete 事件，將指定點位的值餵入對應的 HistoryBuffer：
#   - device_id 模式：訂閱指定設備，直接餵入該設備值
#   - trait 模式：訂閱所有匹配設備，依 aggregate 函式聚合後餵入
#   - 自行實作 subscribe/unsubscribe 模式，避免 import csp_lib.manager（含可選依賴）
#
# v0.9.x 起支援多來源：透過 keyword-only ``mappings`` / ``history_buffers``
# （dict[str, ...]）同時維護多個資料流。舊 API（單一 ``mapping`` / ``pv_service``）
# 仍可用，內部會正規化為 ``{"pv_power": ...}`` 的 dict 表達。

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Awaitable, Callable

from csp_lib.core import get_logger
from csp_lib.equipment.device import EVENT_READ_COMPLETE

from .registry import DeviceRegistry
from .schema import AggregateFunc, DataFeedMapping

if TYPE_CHECKING:
    from csp_lib.controller.services import HistoryBuffer, PVDataService
    from csp_lib.equipment.device import ReadCompletePayload

logger = get_logger(__name__)

# Legacy 單來源使用的內部 key
_LEGACY_PV_KEY = "pv_power"


class DeviceDataFeed:
    """
    設備事件 → HistoryBuffer 資料餵入

    訂閱設備的 ``read_complete`` 事件，將指定點位的值餵入對應的 HistoryBuffer。
    透過 DataFeedMapping 指定目標設備（device_id 或 trait 模式）。

    - device_id 模式：訂閱單一設備，直接餵入該設備的點位值
    - trait 模式：訂閱所有匹配設備，任一設備觸發 read_complete 時
      從所有 responsive 設備收集值並聚合（預設 FIRST，可設為 SUM 等）

    **v0.9.x 起支援多來源**：傳入 keyword-only ``mappings`` / ``history_buffers``
    （``dict[str, DataFeedMapping]`` / ``dict[str, HistoryBuffer]``）以同時維護
    多個獨立的資料流；每個 key 對應的 mapping 與 buffer 獨立訂閱 / 聚合。

    實作與 ``DeviceEventSubscriber`` 相同的 subscribe/unsubscribe 模式，
    但不繼承該類別以避免 import csp_lib.manager（其 __init__ 會載入可選依賴 motor）。
    """

    def __init__(
        self,
        registry: DeviceRegistry,
        mapping: DataFeedMapping | None = None,
        pv_service: "PVDataService | HistoryBuffer | None" = None,
        *,
        mappings: Mapping[str, DataFeedMapping] | None = None,
        history_buffers: Mapping[str, HistoryBuffer] | None = None,
    ) -> None:
        """
        初始化資料餵入器。

        支援兩種 API：

        **Legacy（單一來源，v0.9.x 前）**::

            DeviceDataFeed(registry, mapping, pv_service)

        內部會正規化為 ``{"pv_power": mapping}`` / ``{"pv_power": pv_service}``。

        **v0.9.x+（多來源）**::

            DeviceDataFeed(
                registry,
                mappings={"pv_power": m1, "grid_power": m2},
                history_buffers={"pv_power": b1, "grid_power": b2},
            )

        Args:
            registry: 設備查詢索引
            mapping: （legacy）PV 資料來源映射；與 ``mappings`` / ``history_buffers`` 互斥
            pv_service: （legacy）PV 資料服務；與 ``mappings`` / ``history_buffers`` 互斥
            mappings: （keyword-only）多來源映射字典 ``{key: DataFeedMapping}``
            history_buffers: （keyword-only）多來源緩衝字典 ``{key: HistoryBuffer}``

        Raises:
            ValueError: legacy 參數與新 keyword 參數混用時
        """
        # 混用拒絕：新舊 API 不得共用
        legacy_used = mapping is not None or pv_service is not None
        new_used = mappings is not None or history_buffers is not None
        if legacy_used and new_used:
            raise ValueError(
                "DeviceDataFeed: cannot mix legacy parameters (mapping, pv_service) "
                "with new keyword parameters (mappings, history_buffers). Use one or the other."
            )

        self._registry = registry
        self._unsubscribes: list[Callable[[], None]] = []

        # 正規化為 dict-based 內部表達
        self._mappings: dict[str, DataFeedMapping]
        self._buffers: dict[str, HistoryBuffer]
        if new_used:
            self._mappings = dict(mappings) if mappings else {}
            self._buffers = dict(history_buffers) if history_buffers else {}
        elif legacy_used:
            self._mappings = {_LEGACY_PV_KEY: mapping} if mapping is not None else {}
            # pv_service 可能是 PVDataService；PVDataService 是 HistoryBuffer 的 subclass，
            # 在 runtime 合法；type annotation 已放寬到兩者聯集。
            self._buffers = {_LEGACY_PV_KEY: pv_service} if pv_service is not None else {}  # type: ignore[dict-item]
        else:
            self._mappings = {}
            self._buffers = {}

    # ---- 公開 accessor ----

    def get_buffer(self, key: str) -> "HistoryBuffer | None":
        """
        依 key 取得 HistoryBuffer。

        Args:
            key: buffer 的識別鍵（例如 "pv_power"、"grid_power"）

        Returns:
            對應的 HistoryBuffer；不存在則回 None。
        """
        return self._buffers.get(key)

    @property
    def buffers(self) -> Mapping[str, "HistoryBuffer"]:
        """取得所有 buffers 的不可變視圖（``MappingProxyType``，零複製）。"""
        return MappingProxyType(self._buffers)

    @property
    def pv_service(self) -> "HistoryBuffer | None":
        """
        Backward-compat：取得 legacy "pv_power" buffer。

        .. deprecated:: 0.9.x
            改用 :meth:`get_buffer` 或 :attr:`buffers`。
        """
        return self._buffers.get(_LEGACY_PV_KEY)

    # ---- 訂閱生命週期 ----

    def attach(self) -> None:
        """
        解析每個 key 對應的目標設備並訂閱 read_complete 事件。

        device_id 模式：訂閱指定設備。
        trait 模式：訂閱所有匹配設備（含非 responsive），
        任一設備 read_complete 時觸發聚合計算。
        無法解析時 log warning 並跳過該 key。

        部分訂閱失敗時自動回滾**所有**已完成的訂閱，避免洩漏。
        """
        pending: list[Callable[[], None]] = []
        try:
            for key, mapping in self._mappings.items():
                # 未提供對應 buffer 就跳過（無處餵入）
                if key not in self._buffers:
                    logger.warning(
                        "DeviceDataFeed: mapping '{}' has no corresponding history buffer, skipping.",
                        key,
                    )
                    continue

                handler = self._make_handler(key, mapping)
                if mapping.device_id is not None:
                    device = self._registry.get_device(mapping.device_id)
                    if device is None:
                        logger.warning(
                            "DeviceDataFeed[{}]: device '{}' not found, data feed not attached.",
                            key,
                            mapping.device_id,
                        )
                        continue
                    pending.append(device.on(EVENT_READ_COMPLETE, handler))
                else:
                    devices = self._registry.get_devices_by_trait(mapping.trait)  # type: ignore[arg-type]
                    if not devices:
                        logger.warning(
                            "DeviceDataFeed[{}]: no devices with trait '{}', data feed not attached.",
                            key,
                            mapping.trait,
                        )
                        continue
                    for device in devices:
                        pending.append(device.on(EVENT_READ_COMPLETE, handler))
        except Exception:
            logger.opt(exception=True).warning(
                "DeviceDataFeed: partial subscribe failure, rolling back all pending attaches."
            )
            for unsub in pending:
                try:
                    unsub()
                except Exception:
                    logger.opt(exception=True).warning("Rollback unsub raised")
            return

        self._unsubscribes.extend(pending)

    def detach(self) -> None:
        """取消訂閱所有設備的事件"""
        for unsub in self._unsubscribes:
            unsub()
        self._unsubscribes.clear()

    # ---- Handler 建構 ----

    def _make_handler(self, key: str, mapping: DataFeedMapping) -> Callable[["ReadCompletePayload"], Awaitable[None]]:
        """為特定 (key, mapping) 建立 read_complete handler closure。

        由 ``attach()`` 呼叫一次，handler 於建立時已 capture buffer reference
        （attach 已先驗證 key 存在於 ``_buffers``），避免每次 read_complete 走
        dict lookup。
        """
        # Capture buffer at attach time — attach() 已驗證 key in self._buffers
        buffer = self._buffers[key]

        async def handler(payload: "ReadCompletePayload") -> None:
            if mapping.device_id is not None:
                value = payload.values.get(mapping.point_name)
                if isinstance(value, (int, float)):
                    buffer.append(float(value))
                else:
                    buffer.append(None)
            else:
                self._feed_trait_aggregate(key, mapping, buffer)

        return handler

    def _feed_trait_aggregate(
        self,
        key: str,
        mapping: DataFeedMapping,
        buffer: "HistoryBuffer",
    ) -> None:
        """從所有 responsive 設備收集值，聚合後餵入對應 buffer"""
        devices = self._registry.get_responsive_devices_by_trait(mapping.trait)  # type: ignore[arg-type]
        values: list[float] = []
        for device in devices:
            v = device.latest_values.get(mapping.point_name)
            if isinstance(v, (int, float)):
                values.append(float(v))

        if not values:
            buffer.append(None)
            return

        buffer.append(self._apply_aggregate(mapping, values))

    @staticmethod
    def _apply_aggregate(mapping: DataFeedMapping, values: list[float]) -> float:
        """套用聚合函式"""
        func = mapping.aggregate
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
