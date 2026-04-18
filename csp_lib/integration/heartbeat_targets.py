# =============== Integration - Heartbeat Targets ===============
#
# 心跳寫入目標協定與預設實作
#
# 將「心跳值要寫到哪裡」這件事抽出成 Protocol，讓 HeartbeatService
# 從 v0.8.1 起可接受任意符合該協定的寫入目標物件（AsyncModbusDevice
# 點位、Modbus Gateway register、Redis key、HTTP endpoint…）。
#
# 預設實作：
#   - DeviceHeartbeatTarget: 對 ``AsyncModbusDevice`` 的單一點位寫入；
#     DeviceError 只 log warning、不 raise（fire-and-forget 語義，
#     與舊版 HeartbeatService._safe_write 行為一致）。
#
# 其他 target 實作散落於各自所屬層（例如 modbus_gateway 層提供
# ``GatewayRegisterHeartbeatTarget``），避免 integration 層反向 import。
#
# 向後相容：舊 HeartbeatMapping(device_id=..., point_name=...) 路徑保留，
# HeartbeatService 內部會自動包裝為 DeviceHeartbeatTarget。

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from csp_lib.core import get_logger
from csp_lib.core.errors import DeviceError

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger(__name__)


@runtime_checkable
class HeartbeatTarget(Protocol):
    """心跳寫入目標協定

    任何實作 ``async write(value)`` 與 ``identity`` 屬性的物件皆可作為
    HeartbeatService 的寫入目標。

    Attributes:
        identity: 唯一識別字串（供 log / metrics / value-generator key 使用）。
    """

    async def write(self, value: int) -> None:
        """將 value 寫入目標；錯誤由實作自行決定處理方式"""
        ...

    @property
    def identity(self) -> str:
        """回傳 target 的唯一識別字串"""
        ...


class DeviceHeartbeatTarget:
    """以 ``AsyncModbusDevice`` 的單一點位作為心跳寫入目標

    封裝 ``device.write(point_name, value)``，並將 ``DeviceError`` 吞掉、
    僅 log warning（fire-and-forget 語義）。其他例外不攔截（讓 caller
    決定是否中止）。

    Args:
        device: 目標 ``AsyncModbusDevice``。
        point_name: 寫入點位名稱（必須存在於 ``device.all_point_names``）。
    """

    def __init__(self, device: AsyncModbusDevice, point_name: str) -> None:
        self._device = device
        self._point_name = point_name

    async def write(self, value: int) -> None:
        """將心跳值寫入設備點位，``DeviceError`` 僅 log warning 不 raise"""
        try:
            await self._device.write(self._point_name, value)
        except DeviceError:
            logger.opt(exception=True).warning(
                f"Heartbeat write failed: device='{self._device.device_id}' point='{self._point_name}'"
            )

    @property
    def identity(self) -> str:
        """回傳 ``device:{device_id}:{point_name}``"""
        return f"device:{self._device.device_id}:{self._point_name}"


__all__ = [
    "DeviceHeartbeatTarget",
    "HeartbeatTarget",
]
