# =============== Manager Data - Upload ===============
#
# 資料上傳管理器
#
# 提供設備資料自動上傳功能：
#   - DataUploadManager: 訂閱設備事件並自動上傳資料至 MongoDB
#
# 設計模式：
#   - 觀察者模式：訂閱 AsyncModbusDevice 的 read_complete/disconnected 事件
#   - 事件驅動：讀取完成 → 上傳資料，斷線 → 上傳空值記錄
#   - 降頻儲存：透過 save_interval 控制每台設備的儲存頻率

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

from csp_lib.core import get_logger
from csp_lib.equipment.device.events import (
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    DisconnectPayload,
    ReadCompletePayload,
)
from csp_lib.manager.base import DeviceEventSubscriber

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice
    from csp_lib.manager.base import BatchUploader
    from csp_lib.mongo.local_buffer import LocalBufferedUploader

logger = get_logger(__name__)


def nullify_nested(value: Any) -> Any:
    """
    遞歸將值轉為 None 結構

    保留 dict 和 list 的結構，但將所有葉節點值替換為 None。

    Args:
        value: 任意值

    Returns:
        對應的 None 結構

    Examples:
        >>> nullify_nested(25.5)
        None
        >>> nullify_nested({"a": 1, "b": 2})
        {"a": None, "b": None}
        >>> nullify_nested([1, 2, 3])
        [None, None, None]
        >>> nullify_nested({"status": {"running": True, "mode": 2}})
        {"status": {"running": None, "mode": None}}
    """
    if isinstance(value, dict):
        return {k: nullify_nested(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [nullify_nested(item) for item in value]
    else:
        return None


class DataUploadManager(DeviceEventSubscriber):
    """
    資料上傳管理器

    自動將設備讀取資料上傳至 MongoDB。採用觀察者模式訂閱 AsyncModbusDevice
    的 read_complete 與 disconnected 事件，實現事件驅動的資料上傳。

    職責：
        1. 訂閱多個 AsyncModbusDevice 的事件
        2. read_complete → 上傳讀取資料並快取結構
        3. disconnected → 上傳空值記錄（保留巢狀結構，讓前端圖表正確顯示斷線區間）

    Attributes:
        _uploader: MongoDB 批次上傳器
        _device_collection: 設備對應的 collection 名稱
        _last_values: 最後讀取值（用於推斷巢狀結構）

    Example:
        ```python
        from csp_lib.mongo import MongoBatchUploader
        from csp_lib.manager.data import DataUploadManager

        uploader = MongoBatchUploader(db).start()
        data_manager = DataUploadManager(uploader)

        # 配置並訂閱設備
        data_manager.configure(device.device_id, collection_name="device_data")
        data_manager.subscribe(device)

        # 設備讀取時資料自動上傳
        # 設備斷線時自動上傳空值記錄
        ```
    """

    def __init__(
        self,
        uploader: BatchUploader,
        *,
        buffered_uploader: LocalBufferedUploader | None = None,
    ) -> None:
        """
        初始化資料上傳管理器

        Args:
            uploader: 批次上傳器實例（實作 BatchUploader Protocol）
            buffered_uploader: 選擇性的 ``LocalBufferedUploader``。若提供，
                所有 enqueue 會改走本地 buffer，避免下游 MongoDB 故障時
                資料遺失。
        """
        super().__init__()
        # 優先使用 buffered_uploader 以啟用 local buffer fail-safe
        self._uploader: BatchUploader = buffered_uploader if buffered_uploader is not None else uploader
        self._device_collection: dict[str, str] = {}  # device_id -> collection_name
        self._last_values: dict[str, dict[str, Any]] = {}  # device_id -> last values
        self._save_intervals: dict[str, float] = {}  # device_id -> save_interval (seconds)
        self._last_save_times: dict[str, float] = {}  # device_id -> monotonic timestamp

    # ================ 訂閱管理 ================

    def configure(
        self,
        device_id: str,
        collection_name: str,
        save_interval: float | None = None,
    ) -> None:
        """
        預先配置設備的上傳參數

        必須在 ``subscribe()`` 之前呼叫，設定該設備對應的 MongoDB collection
        與儲存間隔。若未呼叫 ``configure()`` 就直接 ``subscribe()``，將使用
        預設 collection ``"device_data"``。

        Args:
            device_id: 設備 ID
            collection_name: 資料上傳的 MongoDB collection 名稱
            save_interval: 最小儲存間隔（秒）。``None`` 或 ``0`` 表示每次讀取都儲存。
        """
        self._device_collection[device_id] = collection_name
        self._uploader.register_collection(collection_name)
        if save_interval and save_interval > 0:
            self._save_intervals[device_id] = save_interval
        else:
            self._save_intervals.pop(device_id, None)
        logger.debug(f"資料上傳管理器: 已配置設備 {device_id} -> {collection_name} (save_interval={save_interval})")

    def subscribe(self, device: AsyncModbusDevice) -> None:
        """
        訂閱設備事件

        訂閱設備的 read_complete 與 disconnected 事件。
        若已訂閱則不重複訂閱。

        需先呼叫 ``configure()`` 設定 collection_name，否則使用預設值 ``"device_data"``。

        Args:
            device: 要訂閱的 Modbus 設備
        """
        device_id = device.device_id
        if device_id in self._unsubscribes:
            return

        # 若未 configure，使用預設 collection
        collection_name = self._device_collection.get(device_id)
        if not collection_name:
            collection_name = "device_data"
            self._device_collection[device_id] = collection_name
            self._uploader.register_collection(collection_name)

        save_interval = self._save_intervals.get(device_id, 0)
        self._unsubscribes[device_id] = self._register_events(device)
        logger.info(f"資料上傳管理器已訂閱設備: {device_id} -> {collection_name} (save_interval={save_interval}s)")

    def _register_events(self, device: AsyncModbusDevice) -> list[Callable[[], None]]:
        """註冊設備的 read_complete 與 disconnected 事件"""
        return [
            device.on(EVENT_READ_COMPLETE, self._on_read_complete),
            device.on(EVENT_DISCONNECTED, self._on_disconnected),
        ]

    def _on_unsubscribe(self, device_id: str) -> None:
        self._device_collection.pop(device_id, None)
        self._last_values.pop(device_id, None)
        self._save_intervals.pop(device_id, None)
        self._last_save_times.pop(device_id, None)
        logger.info(f"資料上傳管理器已取消訂閱設備: {device_id}")

    # ================ 事件處理器 ================

    async def _on_read_complete(self, payload: ReadCompletePayload) -> None:
        """
        處理讀取完成事件

        將讀取資料加入上傳佇列，並快取值結構供斷線時使用。
        若設有 save_interval，僅在距上次儲存超過指定秒數時才上傳。

        Args:
            payload: 讀取完成事件資料
        """
        device_id = payload.device_id
        collection_name = self._device_collection.get(device_id)
        if not collection_name:
            return

        # 快取結構供斷線時使用（無論是否降頻都要更新）
        self._last_values[device_id] = payload.values

        # 降頻檢查
        interval = self._save_intervals.get(device_id)
        if interval is not None:
            now = time.monotonic()
            last_save = self._last_save_times.get(device_id)
            if last_save is not None and (now - last_save) < interval:
                return
            self._last_save_times[device_id] = now

        # 建立文件並上傳
        document = {
            "device_id": device_id,
            "timestamp": payload.timestamp,
            **payload.values,
        }
        await self._uploader.enqueue(collection_name, document)

    async def _on_disconnected(self, payload: DisconnectPayload) -> None:
        """
        處理斷線事件

        使用快取的結構產生空值記錄並上傳，讓前端圖表能正確顯示斷線區間。

        Args:
            payload: 斷線事件資料
        """
        device_id = payload.device_id
        collection_name = self._device_collection.get(device_id)
        if not collection_name:
            return

        # 從快取取得結構，產生空值
        last_values = self._last_values.get(device_id)
        if last_values:
            null_values = {k: nullify_nested(v) for k, v in last_values.items()}
        else:
            # 無快取時，無法產生空值記錄
            logger.warning(f"資料上傳管理器: 設備 {device_id} 斷線但無快取結構，跳過空值記錄")
            return

        document = {
            "device_id": device_id,
            "timestamp": payload.timestamp,
            **null_values,
        }
        await self._uploader.enqueue(collection_name, document)
        logger.debug(f"資料上傳管理器: 已上傳設備 {device_id} 斷線空值記錄")


__all__ = [
    "DataUploadManager",
    "nullify_nested",
]
