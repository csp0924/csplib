# =============== Modbus Gateway - Heartbeat Target ===============
#
# 以 Modbus Gateway register 作為心跳寫入目標
#
# 提供 ``GatewayRegisterHeartbeatTarget``：實作 integration 層的
# ``HeartbeatTarget`` Protocol，將心跳值寫入 ``ModbusGatewayServer``
# 暴露的 register（供 EMS / SCADA 端讀取控制器是否仍在線）。
#
# 注意：
#   - ``ModbusGatewayServer.set_register`` 目前為同步方法（純記憶體寫入
#     Modbus datastore），此 target 的 ``async write`` 不 await、直接呼叫；
#     保留 async 簽名是為了與 Protocol 介面統一，並預留未來若 set_register
#     改為 async 時的相容性。
#   - 使用 ``TYPE_CHECKING`` import ``ModbusGatewayServer``，避免
#     執行期循環依賴。

from __future__ import annotations

from typing import TYPE_CHECKING

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from .server import ModbusGatewayServer

logger = get_logger(__name__)


class GatewayRegisterHeartbeatTarget:
    """以 Modbus Gateway register 作為心跳寫入目標

    將心跳值寫入 ``ModbusGatewayServer`` 的指定 register，讓上游 EMS /
    SCADA 端可讀取此 register 判斷控制器存活。

    Args:
        gateway: 目標 ``ModbusGatewayServer``。
        register_name: 在 gateway 註冊的 register 名稱（必須對應
            ``GatewayRegisterDef.name``）。
    """

    def __init__(self, gateway: ModbusGatewayServer, register_name: str) -> None:
        self._gateway = gateway
        self._register_name = register_name

    async def write(self, value: int) -> None:
        """將心跳值寫入 Gateway register

        ``set_register`` 目前為同步呼叫（純記憶體運算），本 coroutine
        不 await 任何物件；若未來 gateway 改為 async API，此處可平滑升級。
        異常不攔截 — 呼叫端（HeartbeatService）會 log 警告並繼續其他目標。
        """
        self._gateway.set_register(self._register_name, value)

    @property
    def identity(self) -> str:
        """回傳 ``gateway:{register_name}``"""
        return f"gateway:{self._register_name}"


__all__ = [
    "GatewayRegisterHeartbeatTarget",
]
