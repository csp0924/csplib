# =============== Manager - Base ===============
#
# Manager 層共用基底與 Protocol
#
# 提供：
#   - AsyncRepository: Repository 標記 Protocol（健康檢查）
#   - BatchUploader: 批次上傳器 Protocol（解耦 MongoBatchUploader）
#   - DeviceEventSubscriber: 設備事件訂閱基底類別
#   - LeaderGate / AlwaysLeaderGate: Cluster / HA 部署的 leader 閘門 Protocol

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.equipment.device.protocol import DeviceProtocol

logger = get_logger(__name__)


@runtime_checkable
class AsyncRepository(Protocol):
    """
    Repository 標記 Protocol

    所有 Repository 介面的共同基底，定義健康檢查方法。
    """

    async def health_check(self) -> bool:
        """檢查 Repository 連線是否正常"""
        ...


@runtime_checkable
class BatchUploader(Protocol):
    """
    批次上傳器 Protocol

    解耦 DataUploadManager / StatisticsManager 對 MongoBatchUploader 的直接依賴，
    讓上層模組可以注入任何實作此 Protocol 的上傳器。

    Methods:
        register_collection: 註冊 collection 名稱
        enqueue: 將文件加入上傳佇列
    """

    def register_collection(self, collection_name: str) -> None:
        """
        註冊 collection 名稱

        Args:
            collection_name: MongoDB collection 名稱
        """
        ...

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        """
        將文件加入上傳佇列

        Args:
            collection_name: 目標 collection 名稱
            document: 要上傳的文件
        """
        ...


class DeviceEventSubscriber:
    """
    設備事件訂閱基底類別

    提供通用的事件訂閱管理框架，子類別只需覆寫 ``_register_events()``
    即可定義要訂閱的事件。取消訂閱時可覆寫 ``_on_unsubscribe()`` 進行額外清理。

    使用範例::

        class MyManager(DeviceEventSubscriber):
            def _register_events(self, device: AsyncModbusDevice) -> list[Callable[[], None]]:
                return [
                    device.on("event_a", self._on_event_a),
                    device.on("event_b", self._on_event_b),
                ]
    """

    def __init__(self) -> None:
        self._unsubscribes: dict[str, list[Callable[[], None]]] = {}

    def subscribe(self, device: DeviceProtocol) -> None:
        """
        訂閱設備事件

        若已訂閱則不重複訂閱。

        Args:
            device: 要訂閱的設備（任何實作 DeviceProtocol 的裝置）
        """
        device_id = device.device_id
        if device_id in self._unsubscribes:
            logger.debug(f"Device '{device_id}' already subscribed, skipping")
            return
        self._unsubscribes[device_id] = self._register_events(device)
        logger.info(f"Subscribed to device '{device_id}'")

    def unsubscribe(self, device: DeviceProtocol) -> None:
        """
        取消訂閱設備事件

        移除對指定設備的事件訂閱。若尚未訂閱則不做任何操作。

        Args:
            device: 要取消訂閱的設備（任何實作 DeviceProtocol 的裝置）
        """
        device_id = device.device_id
        if device_id not in self._unsubscribes:
            logger.debug(f"Device '{device_id}' not subscribed, skipping unsubscribe")
            return
        for unsub in self._unsubscribes.pop(device_id):
            unsub()
        self._on_unsubscribe(device_id)
        logger.info(f"Unsubscribed from device '{device_id}'")

    def _register_events(self, device: DeviceProtocol) -> list[Callable[[], None]]:
        """
        註冊設備事件（子類別必須覆寫）

        Args:
            device: 要訂閱的設備（任何實作 DeviceProtocol 的裝置）

        Returns:
            取消訂閱的 callback 列表
        """
        raise NotImplementedError

    def _on_unsubscribe(self, device_id: str) -> None:
        """
        取消訂閱後的額外清理（子類別可選覆寫）

        Args:
            device_id: 被取消訂閱的設備 ID
        """


# ================ Leader Gate ================


@runtime_checkable
class LeaderGate(Protocol):
    """Leader 閘門 Protocol — 供 Manager 在 cluster / HA 部署下判斷是否應執行
    「只能由 leader 做」的動作（寫 Redis、執行 write command、啟動 read I/O 等）。

    單節點部署可注入 ``AlwaysLeaderGate`` 停用 gating。

    語意：
        - ``is_leader``: 快速、非阻塞快照讀取；呼叫者每事件檢查一次，**必須 O(1)**、
          不得有 I/O。實作可背景更新內部旗標。
        - ``wait_until_leader``: 用於啟動路徑；非 leader 時 await 直到升格。
          允許取消（CancelledError 向上拋）。
    """

    @property
    def is_leader(self) -> bool: ...

    async def wait_until_leader(self) -> None: ...


class AlwaysLeaderGate:
    """單節點部署用 no-op 實作，永遠是 leader。"""

    @property
    def is_leader(self) -> bool:
        return True

    async def wait_until_leader(self) -> None:
        return None


__all__ = [
    "AsyncRepository",
    "BatchUploader",
    "DeviceEventSubscriber",
    "LeaderGate",
    "AlwaysLeaderGate",
]
