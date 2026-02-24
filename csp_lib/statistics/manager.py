# =============== Statistics - Manager ===============
#
# 統計管理器
#
# 提供事件驅動的能源統計整合：
#   - StatisticsManager: 訂閱設備 read_complete 事件，驅動統計引擎
#
# 設計模式：
#   - 觀察者模式：訂閱 AsyncModbusDevice 的 read_complete 事件
#   - 事件驅動：讀取完成 → 更新統計 → 上傳完成的區間記錄

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from csp_lib.core import get_logger
from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, ReadCompletePayload
from csp_lib.manager.base import DeviceEventSubscriber
from csp_lib.statistics.config import StatisticsConfig
from csp_lib.statistics.engine import StatisticsEngine

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice
    from csp_lib.integration.registry import DeviceRegistry
    from csp_lib.mongo import MongoBatchUploader

logger = get_logger(__name__)


class StatisticsManager(DeviceEventSubscriber):
    """
    統計管理器

    訂閱設備的 read_complete 事件，驅動 StatisticsEngine 進行能耗計算。
    區間完成時自動將記錄上傳至 MongoDB。

    職責：
        1. 訂閱 AsyncModbusDevice 的 read_complete 事件
        2. 驅動 StatisticsEngine.process_read()
        3. 將完成的 IntervalRecord / PowerSumRecord 上傳至 MongoDB
        4. 透過 DeviceRegistry 解析 trait → device_ids 以建立功率加總

    Example:
        ```python
        from csp_lib.statistics import StatisticsConfig, StatisticsManager

        config = StatisticsConfig(metrics=[...], power_sums=[...])
        manager = StatisticsManager(config, uploader, registry)

        manager.subscribe(device)
        # 設備讀取時自動計算統計並上傳
        ```
    """

    def __init__(
        self,
        config: StatisticsConfig,
        uploader: MongoBatchUploader,
        registry: DeviceRegistry | None = None,
    ) -> None:
        """
        初始化統計管理器

        Args:
            config: 統計配置
            uploader: MongoDB 批次上傳器
            registry: 設備 Registry（功率加總用，可選）
        """
        super().__init__()
        self._config = config
        self._uploader = uploader
        self._engine = StatisticsEngine(config)
        self._collection_name = config.collection_name

        self._uploader.register_collection(self._collection_name)

        # 解析 power sum trait → device_ids
        if registry:
            for ps in config.power_sums:
                devices = registry.get_devices_by_trait(ps.trait)
                device_ids = [d.device_id for d in devices]
                self._engine.register_power_sum_devices(ps.name, device_ids)

    @property
    def engine(self) -> StatisticsEngine:
        """統計引擎（供外部查詢 real-time 功率加總）"""
        return self._engine

    # ================ 訂閱管理 ================

    def subscribe(self, device: AsyncModbusDevice, collection_name: str | None = None) -> None:  # type: ignore[override]
        """
        訂閱設備事件

        Args:
            device: 要訂閱的 Modbus 設備
            collection_name: 未使用，保持介面一致性
        """
        device_id = device.device_id
        if device_id in self._unsubscribes:
            return

        self._unsubscribes[device_id] = self._register_events(device)
        logger.info(f"統計管理器已訂閱設備: {device_id}")

    def _register_events(self, device: AsyncModbusDevice) -> list[Callable[[], None]]:
        """註冊設備的 read_complete 事件"""
        return [
            device.on(EVENT_READ_COMPLETE, self._on_read_complete),
        ]

    def _on_unsubscribe(self, device_id: str) -> None:
        logger.info(f"統計管理器已取消訂閱設備: {device_id}")

    # ================ 事件處理器 ================

    async def _on_read_complete(self, payload: ReadCompletePayload) -> None:
        """
        處理讀取完成事件

        驅動引擎計算，並將完成的記錄上傳至 MongoDB。

        Args:
            payload: 讀取完成事件資料
        """
        records = self._engine.process_read(payload.device_id, payload.values, payload.timestamp)

        now = datetime.now(timezone.utc)

        # Upload energy records
        for record in records:
            document = {
                "type": "energy",
                "device_id": record.device_id,
                "interval_minutes": record.interval_minutes,
                "period_start": record.period_start,
                "period_end": record.period_end,
                "kwh": record.kwh,
                "sample_count": record.sample_count,
                "meter_type": record.meter_type,
                "timestamp": now,
            }
            await self._uploader.enqueue(self._collection_name, document)

        # Build and upload power sum records for completed intervals
        if records and self._config.power_sums:
            seen: set[int] = set()
            for record in records:
                if record.interval_minutes not in seen:
                    seen.add(record.interval_minutes)
                    power_records = self._engine.build_power_sum_records(
                        record.interval_minutes, record.period_start, record.period_end
                    )
                    for pr in power_records:
                        document = {
                            "type": "power_sum",
                            "name": pr.name,
                            "interval_minutes": pr.interval_minutes,
                            "period_start": pr.period_start,
                            "period_end": pr.period_end,
                            "total_power": pr.total_power,
                            "device_count": pr.device_count,
                            "timestamp": now,
                        }
                        await self._uploader.enqueue(self._collection_name, document)


__all__ = [
    "StatisticsManager",
]
