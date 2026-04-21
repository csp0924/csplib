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
#   - Fan-out：同一設備可綁多個 UploadTarget，輸出到多個 collection
#   - Transform：每個 target 可帶自訂 transform（raw values → target schema）
#   - WritePolicy：ALWAYS / ON_CHANGE / INTERVAL（INTERVAL 尚未實作）

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, overload

from csp_lib.core import get_logger
from csp_lib.equipment.device.events import (
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    DisconnectPayload,
    ReadCompletePayload,
)
from csp_lib.manager.base import DeviceEventSubscriber

from .targets import TransformFn, TransformResult, UploadTarget, WritePolicy

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


# ================ 內部 runtime 容器 ================


@dataclass
class _TargetRuntime:
    """每個 (device_id, target) 配對的執行期狀態。

    Attributes:
        target: 對應的 ``UploadTarget``。
        legacy: 是否為 legacy（舊 1:1）配置路徑；True 時走 ``{device_id, timestamp, **values}`` 舊 schema
                並忽略 ``target.transform``。
        save_interval: legacy 節流秒數；``None`` 代表每次都寫。僅 legacy 路徑使用。
        last_raw_values: legacy 斷線空值記錄用的上次原始 values。僅 legacy 路徑使用。
        last_result: 上次 transform 的正規化輸出（用於 ON_CHANGE 比對）。
        last_shape_cache: 上次 ALWAYS 寫入的文件快取（斷線時拿來 nullify）。
        last_save_time: 上次寫入的 ``time.monotonic()``（legacy save_interval 節流用）。
    """

    target: UploadTarget
    legacy: bool = False
    save_interval: float | None = None
    last_raw_values: dict[str, Any] | None = None
    last_result: list[dict[str, Any]] | None = None
    last_shape_cache: list[dict[str, Any]] | None = None
    last_save_time: float | None = None


# ================ 正規化工具 ================


def _normalize_result(result: TransformResult) -> list[dict[str, Any]] | None:
    """將 transform 結果正規化為 ``list[dict]`` 或 ``None``。

    - ``None`` → ``None``（跳過）
    - ``dict`` → ``[dict]``
    - ``list[dict]`` → 原樣
    """
    if result is None:
        return None
    if isinstance(result, dict):
        return [result]
    return list(result)


# ================ DataUploadManager ================


class DataUploadManager(DeviceEventSubscriber):
    """
    資料上傳管理器

    自動將設備讀取資料上傳至 MongoDB。採用觀察者模式訂閱 AsyncModbusDevice
    的 read_complete 與 disconnected 事件，實現事件驅動的資料上傳。

    支援兩種配置模式：

    1. **Legacy 模式**（向後相容）::

        manager.configure(device_id, collection_name, save_interval=30)

       會把設備資料以 ``{device_id, timestamp, **values}`` 的形式寫入
       單一 collection，行為與 v0.8 之前完全一致。

    2. **Fan-out 模式**（新）::

        manager.configure(device_id, outputs=[
            UploadTarget(collection="summary", transform=summary_transform,
                         policy=WritePolicy.ON_CHANGE),
            UploadTarget(collection="detail",  transform=detail_transform,
                         policy=WritePolicy.ALWAYS),
        ])

       同一次讀取會 fan-out 到多個 target，每個 target 可以有獨立的
       transform 與 WritePolicy。

    職責：
        1. 訂閱多個 AsyncModbusDevice 的事件
        2. read_complete → 依 target 列表 transform + 寫入
        3. disconnected → 針對 ALWAYS target 上傳空值記錄（保留結構，
           讓前端圖表正確顯示斷線區間）

    Example:
        ```python
        from csp_lib.mongo import MongoBatchUploader
        from csp_lib.manager.data import DataUploadManager

        uploader = MongoBatchUploader(db).start()
        data_manager = DataUploadManager(uploader)

        # 舊式配置（單一 collection）
        data_manager.configure(device.device_id, collection_name="device_data")
        data_manager.subscribe(device)
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

        # 主要狀態：device_id -> 多個 target runtime
        self._device_targets: dict[str, list[_TargetRuntime]] = {}

    # ================ 訂閱管理 ================

    @overload
    def configure(
        self,
        device_id: str,
        collection_name: str,
        save_interval: float | None = ...,
    ) -> None: ...

    @overload
    def configure(
        self,
        device_id: str,
        *,
        outputs: list[UploadTarget],
    ) -> None: ...

    def configure(
        self,
        device_id: str,
        collection_name: str | None = None,
        save_interval: float | None = None,
        *,
        outputs: list[UploadTarget] | None = None,
    ) -> None:
        """
        預先配置設備的上傳參數

        必須在 ``subscribe()`` 之前呼叫。支援兩種模式（二擇一，不可同時提供）：

        **Legacy 模式**（位置參數 ``collection_name``）：
            把設備資料以 ``{device_id, timestamp, **values}`` 寫到單一 collection。
            可選 ``save_interval`` 做降頻。

        **Fan-out 模式**（keyword ``outputs``）：
            提供一組 ``UploadTarget``，同一次讀取會 fan-out 到多個 collection。
            每個 target 可帶自訂 transform 與 ``WritePolicy``。

        Args:
            device_id: 設備 ID
            collection_name: Legacy 模式的 collection 名稱
            save_interval: Legacy 模式的最小儲存間隔（秒）
            outputs: Fan-out 模式的 target 列表（keyword-only）

        Raises:
            ValueError: 同時提供 ``collection_name`` 與 ``outputs``，或兩者皆未提供。
            NotImplementedError: 任一 target 使用 ``WritePolicy.INTERVAL``。
        """
        if collection_name is not None and outputs is not None:
            raise ValueError("configure(): collection_name 與 outputs 不可同時提供")
        if collection_name is None and outputs is None:
            raise ValueError("configure(): 必須提供 collection_name（legacy）或 outputs（fan-out）其中一個")

        if outputs is not None:
            if not outputs:
                raise ValueError("configure(): outputs 不可為空 list")
            for target in outputs:
                if target.policy is WritePolicy.INTERVAL:
                    raise NotImplementedError(f"WritePolicy.INTERVAL 尚未實作（target collection={target.collection}）")

            self._device_targets[device_id] = [_TargetRuntime(target=t) for t in outputs]
            for target in outputs:
                self._uploader.register_collection(target.collection)

            logger.debug(
                "資料上傳管理器: 已配置設備 {} fan-out 到 {} 個 target: {}",
                device_id,
                len(outputs),
                [t.collection for t in outputs],
            )
            return

        assert collection_name is not None  # narrow type for mypy
        warnings.warn(
            "configure(device_id, collection_name, save_interval=...) 將在 1.0 移除，"
            "請改用 configure(device_id, outputs=[UploadTarget(...)])。",
            DeprecationWarning,
            stacklevel=2,
        )
        self._install_legacy_target(device_id, collection_name, save_interval)

    def _install_legacy_target(
        self,
        device_id: str,
        collection_name: str,
        save_interval: float | None,
    ) -> None:
        # 提供給 configure() 舊路徑與 subscribe() 的預設 fallback 共用。
        # 預設 fallback 不走 configure() 是為了避免對 library 自身發出 DeprecationWarning。
        legacy_target = UploadTarget(
            collection=collection_name,
            transform=lambda v: v,  # placeholder；legacy 路徑不呼叫 transform
            policy=WritePolicy.ALWAYS,
        )
        normalized_interval = save_interval if save_interval and save_interval > 0 else None
        self._device_targets[device_id] = [
            _TargetRuntime(target=legacy_target, legacy=True, save_interval=normalized_interval)
        ]
        self._uploader.register_collection(collection_name)
        logger.debug(
            "資料上傳管理器: 已配置設備 {} -> {} (save_interval={})",
            device_id,
            collection_name,
            save_interval,
        )

    def subscribe(self, device: AsyncModbusDevice) -> None:
        """
        訂閱設備事件

        訂閱設備的 read_complete 與 disconnected 事件。
        若已訂閱則不重複訂閱。

        若未呼叫 ``configure()`` 先行設定，會使用 legacy 模式的預設 collection
        ``"device_data"``。

        Args:
            device: 要訂閱的 Modbus 設備
        """
        device_id = device.device_id
        if device_id in self._unsubscribes:
            return

        if device_id not in self._device_targets:
            # 預設 fallback：走內部路徑避免對 library 自己發 DeprecationWarning。
            self._install_legacy_target(device_id, "device_data", None)

        self._unsubscribes[device_id] = self._register_events(device)

        runtimes = self._device_targets[device_id]
        collections = [rt.target.collection for rt in runtimes]
        logger.info(
            "資料上傳管理器已訂閱設備: {} -> {}",
            device_id,
            collections,
        )

    def _register_events(self, device: AsyncModbusDevice) -> list[Callable[[], None]]:
        """註冊設備的 read_complete 與 disconnected 事件"""
        return [
            device.on(EVENT_READ_COMPLETE, self._on_read_complete),
            device.on(EVENT_DISCONNECTED, self._on_disconnected),
        ]

    def _on_unsubscribe(self, device_id: str) -> None:
        self._device_targets.pop(device_id, None)
        logger.info("資料上傳管理器已取消訂閱設備: {}", device_id)

    # ================ 內部工具 ================

    async def _safe_enqueue(self, collection: str, document: dict[str, Any], device_id: str) -> bool:
        # 任何 enqueue 錯誤都不應影響其他 target；以 logger.exception 記錄 traceback 並吞掉。
        # 回傳是否成功，供呼叫端決定要不要 commit 去重 / 節流狀態（避免失敗後資料被去重吞掉）。
        try:
            await self._uploader.enqueue(collection, document)
            return True
        except Exception:
            logger.exception(
                "資料上傳管理器: enqueue 失敗 device={} collection={}",
                device_id,
                collection,
            )
            return False

    # ================ 事件處理器 ================

    async def _on_read_complete(self, payload: ReadCompletePayload) -> None:
        """
        處理讀取完成事件

        依據設備綁定的 target 列表 fan-out：每個 target 各自 transform、
        套用 ``WritePolicy``、寫入對應 collection。
        Transform / enqueue 均以 per-target try/except 隔離，單一 target 失敗
        不影響其他 target。

        Args:
            payload: 讀取完成事件資料
        """
        device_id = payload.device_id
        runtimes = self._device_targets.get(device_id)
        if not runtimes:
            return

        for rt in runtimes:
            if rt.legacy:
                await self._handle_legacy_read(rt, payload)
                continue

            target = rt.target
            try:
                result = target.transform(payload.values)
            except Exception:
                logger.exception(
                    "資料上傳管理器: target transform 失敗 device={} collection={}",
                    device_id,
                    target.collection,
                )
                continue

            docs = _normalize_result(result)
            if not docs:
                continue

            if target.policy is WritePolicy.ON_CHANGE and rt.last_result == docs:
                continue

            all_ok = True
            for doc in docs:
                if not await self._safe_enqueue(target.collection, doc, device_id):
                    all_ok = False

            # 只在全部 enqueue 成功時才 commit 快取：失敗時保持舊狀態，
            # 下次同樣輸出會再試一次，避免資料被去重或空洞吞掉。
            if not all_ok:
                continue
            if target.policy is WritePolicy.ON_CHANGE:
                rt.last_result = docs
            elif target.policy is WritePolicy.ALWAYS:
                rt.last_shape_cache = docs

    async def _handle_legacy_read(self, rt: _TargetRuntime, payload: ReadCompletePayload) -> None:
        # 保留舊 1:1 配置的 wire output：{device_id, timestamp, **values} + save_interval 節流。
        device_id = payload.device_id
        rt.last_raw_values = payload.values

        interval = rt.save_interval
        now: float | None = None
        if interval is not None:
            now = time.monotonic()
            last_save = rt.last_save_time
            if last_save is not None and (now - last_save) < interval:
                return

        document = {
            "device_id": device_id,
            "timestamp": payload.timestamp,
            **payload.values,
        }
        # 節流時戳只在成功 enqueue 後才更新；否則下次 read 仍會再試，
        # 避免 enqueue 失敗後整段節流窗內完全沒有資料落庫。
        if await self._safe_enqueue(rt.target.collection, document, device_id) and now is not None:
            rt.last_save_time = now

    async def _on_disconnected(self, payload: DisconnectPayload) -> None:
        """
        處理斷線事件

        針對 ``WritePolicy.ALWAYS`` 的 target：使用最後一次寫入的文件 shape
        產生空值記錄並上傳，讓前端圖表能正確顯示斷線區間。
        ``ON_CHANGE`` / ``INTERVAL`` target 不上傳空值（避免污染去重/節流語意）。

        Legacy target 走特別路徑：nullify values 部分，但保留
        ``device_id`` / ``timestamp`` 為真實值（維持 v0.8 之前的行為）。

        Args:
            payload: 斷線事件資料
        """
        device_id = payload.device_id
        runtimes = self._device_targets.get(device_id)
        if not runtimes:
            return

        for rt in runtimes:
            if rt.legacy:
                if not rt.last_raw_values:
                    logger.warning(
                        "資料上傳管理器: 設備 {} 斷線但無快取結構，跳過空值記錄",
                        device_id,
                    )
                    continue
                null_values = {k: nullify_nested(v) for k, v in rt.last_raw_values.items()}
                document = {
                    "device_id": device_id,
                    "timestamp": payload.timestamp,
                    **null_values,
                }
                await self._safe_enqueue(rt.target.collection, document, device_id)
                continue

            if rt.target.policy is not WritePolicy.ALWAYS:
                continue
            if not rt.last_shape_cache:
                continue

            for cached_doc in rt.last_shape_cache:
                null_doc = nullify_nested(cached_doc)
                await self._safe_enqueue(rt.target.collection, null_doc, device_id)


__all__ = [
    "DataUploadManager",
    "TransformFn",
    "TransformResult",
    "UploadTarget",
    "WritePolicy",
    "nullify_nested",
]
