# =============== Alarm - Protocols ===============
#
# Alarm 模組的結構化協定（Structural Typing）。
#
# 本模組不依賴任何特定實作（modbus_gateway / equipment 等），僅以 Protocol
# 描述 AlarmAggregator 所需的外部介面，避免下層 import 上層造成循環依賴。

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class WatchdogProtocol(Protocol):
    """Watchdog 結構化協定（Structural Typing）。

    只要物件提供 ``on_timeout(cb)`` 與 ``on_recover(cb)`` 兩個方法且
    接受 ``Callable[[], Awaitable[None]]``，即可被 ``AlarmAggregator``
    綁定。目前相容：

        * ``csp_lib.modbus_gateway.watchdog.CommunicationWatchdog``
        * 任何自行實作相同介面的 watchdog

    使用結構化 typing 的理由：
        alarm 模組屬於 Layer 2（Core 之上），不應依賴 Layer 8 的
        ``modbus_gateway`` 或其他上層模組；透過 Protocol 僅描述介面
        即可保持依賴方向正確。
    """

    def on_timeout(self, callback: Callable[[], Awaitable[None]]) -> None:
        """註冊 timeout 事件 callback（async）。"""
        ...

    def on_recover(self, callback: Callable[[], Awaitable[None]]) -> None:
        """註冊 recover 事件 callback（async）。"""
        ...


# AlarmAggregator 對外廣播用的 callback（同步）。
# 參數為「目前聚合旗標」：True=至少一個 source active；False=全部 cleared。
AlarmChangeCallback = Callable[[bool], None]


__all__ = [
    "AlarmChangeCallback",
    "WatchdogProtocol",
]
