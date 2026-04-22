# =============== Equipment Device - Protocol ===============
#
# 設備通用協定
#
# 定義所有設備類型（Modbus、CAN 等）的最小公開介面。
# AsyncModbusDevice 無需修改即可結構性滿足此協定。

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from csp_lib.core.health import HealthReport
from csp_lib.equipment.alarm.state import AlarmState
from csp_lib.equipment.transport.writer import WriteResult

from .capability import Capability, CapabilityBinding
from .events import AsyncHandler


@runtime_checkable
class DeviceProtocol(Protocol):
    """
    設備通用協定

    所有設備類型的最小公開介面。
    AsyncModbusDevice 和 AsyncCANDevice 均結構性滿足此協定。
    """

    @property
    def device_id(self) -> str: ...

    @property
    def is_connected(self) -> bool: ...

    @property
    def is_responsive(self) -> bool: ...

    @property
    def latest_values(self) -> dict[str, Any]: ...

    @property
    def is_protected(self) -> bool: ...

    @property
    def active_alarms(self) -> list[AlarmState]: ...

    @property
    def capabilities(self) -> dict[str, CapabilityBinding]: ...

    def has_capability(self, capability: Capability | str) -> bool: ...

    def resolve_point(self, capability: Capability | str, slot: str) -> str: ...

    async def read_once(self) -> dict[str, Any]: ...

    async def write(self, name: str, value: Any, verify: bool = False) -> WriteResult: ...

    def on(self, event: str, handler: AsyncHandler) -> Callable[[], None]: ...

    def health(self) -> HealthReport: ...


@runtime_checkable
class ActionDeviceProtocol(DeviceProtocol, Protocol):
    """支援高階動作執行（``execute_action``）的設備協定。

    ``DeviceProtocol`` 的延伸，加入 ``execute_action`` 契約。orchestrator /
    maintenance procedure 等需要觸發 action（如 "start"、"stop"、"reset"）
    的流程用此型別。``AsyncModbusDevice`` 透過 ``WriteMixin.execute_action``
    結構性滿足；``AsyncCANDevice`` 等其他裝置可自行實作。
    """

    async def execute_action(self, action: str, **params: Any) -> Any: ...


__all__ = [
    "DeviceProtocol",
    "ActionDeviceProtocol",
]
