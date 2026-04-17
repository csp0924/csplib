# =============== Registry Aggregating Sync Source ===============
#
# RegistryAggregatingSource — DataSyncSource 實作
#
# 依 trait 從 DeviceRegistry 取得設備，對 latest_values 指定 point 做聚合
# （平均 / 加總 / 最小 / 最大，或自訂 callable），將結果寫入 gateway register。
#
# 同時支援將聚合結果回寫 RuntimeParameters（writable_param），
# 讓 strategy 能透過 RuntimeParameters 動態調整行為。

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from csp_lib.core import get_logger
from csp_lib.core.runtime_params import RuntimeParameters
from csp_lib.integration.registry import DeviceRegistry

from .protocol import UpdateRegisterCallback

logger = get_logger(__name__)


# Callable 型別：輸入 float list（已過濾 None），回傳單一 float
AggregateCallable = Callable[[list[float]], float]


class AggregateFunc(Enum):
    """內建聚合函式列舉。"""

    AVERAGE = "average"
    SUM = "sum"
    MIN = "min"
    MAX = "max"


@dataclass(frozen=True, slots=True)
class RegisterAggregateMapping:
    """單一 register 的聚合映射定義。

    Attributes:
        register: 目標 gateway register 邏輯名稱。
        trait: 設備 trait 標籤（決定聚合來源設備集合）。
        point: 設備 ``latest_values`` 的 key 名稱。
        aggregate: 聚合函式，內建 ``AggregateFunc`` 或自訂 callable。
            預設為 ``AggregateFunc.AVERAGE``。
        offline_fallback: 全設備離線 / 無資料時的回退值。
            * 設為 ``None`` → 該週期跳過（不呼叫 ``update_callback``）
            * 設為數值 → 寫入該值
        writable_param: 若非 ``None`` 且 ``RegistryAggregatingSource`` 有注入 ``params``，
            聚合結果會額外 ``params.set(writable_param, result)``，供 strategy 讀取。
    """

    register: str
    trait: str
    point: str
    aggregate: AggregateFunc | AggregateCallable = AggregateFunc.AVERAGE
    offline_fallback: float | None = None
    writable_param: str | None = None


def _apply_aggregate(
    func: AggregateFunc | AggregateCallable,
    values: list[float],
) -> float:
    """套用聚合函式。values 必須非空（呼叫端保證）。"""
    if isinstance(func, AggregateFunc):
        if func is AggregateFunc.AVERAGE:
            return sum(values) / len(values)
        if func is AggregateFunc.SUM:
            return sum(values)
        if func is AggregateFunc.MIN:
            return min(values)
        if func is AggregateFunc.MAX:
            return max(values)
        # Enum 列舉已窮盡；保底回傳避免型別系統警告
        raise ValueError(f"Unsupported AggregateFunc: {func}")
    # Callable
    return func(values)


class RegistryAggregatingSource:
    """DataSyncSource 實作：從 DeviceRegistry 聚合設備讀值寫入 gateway register。

    每 ``interval`` 秒輪詢一次；對每個 ``RegisterAggregateMapping``：

        1. 呼叫 ``registry.get_devices_by_trait(trait)`` 取得設備列表
        2. 篩選 ``is_responsive=True`` 且 ``latest_values`` 包含 ``point`` 的設備
        3. 將這些 ``latest_values[point]`` 轉為 float，收集為 ``values``
        4. 若 ``values`` 非空 → 套 ``aggregate`` 取得 ``result``
           若 ``values`` 為空且 ``offline_fallback`` 非 ``None`` → ``result = offline_fallback``
           若 ``values`` 為空且 ``offline_fallback`` 為 ``None`` → 本週期跳過此 mapping
        5. ``await update_callback(register, result)``
        6. 若 ``writable_param`` 設且 ``params`` 非 ``None`` → ``params.set(writable_param, result)``

    錯誤處理策略：
        - ``update_callback`` 拋 ``PermissionError`` / ``KeyError`` → warning log，繼續下一 mapping
        - Callable ``aggregate`` 拋例外 → warning log，該 mapping 本週期跳過
        - 其他未預期例外 → warning log，該週期結束後 sleep、繼續下輪

    Args:
        registry: DeviceRegistry 實例。
        mappings: register 聚合映射列表。
        interval: 輪詢週期（秒），預設 1.0。
        params: 選擇性 RuntimeParameters，用於 ``writable_param`` 回寫。

    Example:
        mappings = [
            RegisterAggregateMapping(
                register="avg_soc",
                trait="pcs",
                point="soc",
                aggregate=AggregateFunc.AVERAGE,
                offline_fallback=50.0,
            ),
        ]
        source = RegistryAggregatingSource(registry, mappings, interval=2.0)
        server = ModbusGatewayServer(..., data_sync_sources=[source])
    """

    def __init__(
        self,
        registry: DeviceRegistry,
        mappings: list[RegisterAggregateMapping],
        interval: float = 1.0,
        params: RuntimeParameters | None = None,
    ) -> None:
        self._registry = registry
        self._mappings = list(mappings)
        self._interval = interval
        self._params = params
        self._update_cb: UpdateRegisterCallback | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self, update_callback: UpdateRegisterCallback) -> None:
        """啟動輪詢 task。由 ModbusGatewayServer 於 gateway start 時呼叫。"""
        self._update_cb = update_callback
        self._task = asyncio.create_task(self._poll_loop(), name="registry_aggregating_sync")
        logger.info(f"RegistryAggregatingSource started: interval={self._interval}s, mappings={len(self._mappings)}")

    async def stop(self) -> None:
        """停止輪詢 task。"""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("RegistryAggregatingSource stopped")

    async def _poll_loop(self) -> None:
        """主輪詢迴圈：每 interval 秒處理所有 mappings。"""
        try:
            while True:
                try:
                    await self._process_all_mappings()
                except Exception:
                    logger.opt(exception=True).warning("RegistryAggregatingSource: poll cycle error")
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass

    async def _process_all_mappings(self) -> None:
        """處理所有 mappings；個別失敗不影響其他。"""
        for mapping in self._mappings:
            await self._process_mapping(mapping)

    async def _process_mapping(self, mapping: RegisterAggregateMapping) -> None:
        """處理單一 mapping：收值 → 聚合 → 分派。"""
        devices = self._registry.get_devices_by_trait(mapping.trait)

        # 收集 responsive 且有 point 值的 float 值
        values: list[float] = []
        for device in devices:
            if not device.is_responsive:
                continue
            latest = device.latest_values
            if mapping.point not in latest:
                continue
            raw = latest[mapping.point]
            if raw is None:
                continue
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                logger.debug(
                    f"RegistryAggregatingSource: non-numeric value for "
                    f"trait={mapping.trait} point={mapping.point}, skipping"
                )
                continue

        # 決定 result
        if values:
            try:
                result = _apply_aggregate(mapping.aggregate, values)
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"RegistryAggregatingSource: aggregate callable failed for register={mapping.register}: {e}"
                )
                return
        elif mapping.offline_fallback is not None:
            result = float(mapping.offline_fallback)
        else:
            # 全離線且無 fallback → 本週期跳過
            return

        # 分派到 gateway register
        await self._dispatch(mapping.register, result)

        # 回寫 RuntimeParameters（若設定）
        if mapping.writable_param is not None and self._params is not None:
            try:
                self._params.set(mapping.writable_param, result)
            except Exception:
                logger.opt(exception=True).warning(
                    f"RegistryAggregatingSource: failed to write runtime param '{mapping.writable_param}'"
                )

    async def _dispatch(self, register: str, value: Any) -> None:
        """呼叫 update_callback；已知例外降級為 warning。"""
        if self._update_cb is None:
            return
        try:
            await self._update_cb(register, value)
        except KeyError:
            logger.debug(f"RegistryAggregatingSource: unknown register '{register}', skipping")
        except PermissionError as e:
            logger.warning(f"RegistryAggregatingSource: rejected write — {e}")


__all__ = [
    "AggregateCallable",
    "AggregateFunc",
    "RegisterAggregateMapping",
    "RegistryAggregatingSource",
]
