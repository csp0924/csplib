# =============== Manager - Base ===============
#
# 設備事件訂閱基底類別
#
# 提供通用的 subscribe/unsubscribe 框架：
#   - DeviceEventSubscriber: 管理設備事件訂閱的基底類別

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice

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

    def subscribe(self, device: AsyncModbusDevice) -> None:
        """
        訂閱設備事件

        若已訂閱則不重複訂閱。

        Args:
            device: 要訂閱的 Modbus 設備
        """
        device_id = device.device_id
        if device_id in self._unsubscribes:
            logger.debug(f"Device '{device_id}' already subscribed, skipping")
            return
        self._unsubscribes[device_id] = self._register_events(device)
        logger.info(f"Subscribed to device '{device_id}'")

    def unsubscribe(self, device: AsyncModbusDevice) -> None:
        """
        取消訂閱設備事件

        移除對指定設備的事件訂閱。若尚未訂閱則不做任何操作。

        Args:
            device: 要取消訂閱的 Modbus 設備
        """
        device_id = device.device_id
        if device_id not in self._unsubscribes:
            logger.debug(f"Device '{device_id}' not subscribed, skipping unsubscribe")
            return
        for unsub in self._unsubscribes.pop(device_id):
            unsub()
        self._on_unsubscribe(device_id)
        logger.info(f"Unsubscribed from device '{device_id}'")

    def _register_events(self, device: AsyncModbusDevice) -> list[Callable[[], None]]:
        """
        註冊設備事件（子類別必須覆寫）

        Args:
            device: 要訂閱的 Modbus 設備

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


__all__ = [
    "AsyncRepository",
    "DeviceEventSubscriber",
]
