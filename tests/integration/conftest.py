# =============== tests/integration/conftest.py ===============
#
# Integration 層共用測試 fixture。
#
# 提供 ``MockDeviceProtocol``：最小 ``DeviceProtocol`` 實作，**非**
# AsyncModbusDevice 實例，用來驗證 Integration 層（CommandRouter /
# HeartbeatService / SystemCommandOrchestrator）對 DeviceProtocol 的型別鬆綁
# 真正生效（不會退化回只接受 AsyncModbusDevice）。
#
# 與 tests/manager/conftest.py 的 MockDeviceProtocol 共享精神，但保留
# 獨立 class 以便兩層的演化獨立。

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock

import pytest

from csp_lib.core.health import HealthReport, HealthStatus
from csp_lib.equipment.transport import WriteResult, WriteStatus


class MockDeviceProtocol:
    """最小 ``DeviceProtocol`` 結構性實作（**非** AsyncModbusDevice）。

    用於驗證 Integration 層元件接受任何實作 DeviceProtocol 的設備。
    write 為 ``AsyncMock``，便於斷言被呼叫與引數。

    Attributes:
        write: ``AsyncMock``，呼叫即視為「設備被寫入」。
        execute_action: ``AsyncMock``，回傳帶 ``status.value == "success"``
            的 mock，供 SystemCommandOrchestrator 測試使用。
    """

    def __init__(
        self,
        device_id: str = "mock_dev_01",
        *,
        responsive: bool = True,
        protected: bool = False,
        connected: bool = True,
    ) -> None:
        self._device_id = device_id
        self._responsive = responsive
        self._protected = protected
        self._connected = connected
        self._handlers: dict[str, list[Callable[..., Any]]] = {}

        self.read_once = AsyncMock(return_value={})
        self.write = AsyncMock(
            return_value=WriteResult(
                status=WriteStatus.SUCCESS,
                point_name="",
                value=None,
            )
        )

        # SystemCommandOrchestrator 需要 execute_action；回傳 success ActionResult 風物件
        from unittest.mock import MagicMock

        action_result = MagicMock()
        action_result.status = MagicMock()
        action_result.status.value = "success"
        action_result.error_message = None
        self.execute_action = AsyncMock(return_value=action_result)

    # ---- DeviceProtocol 屬性 ----
    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_responsive(self) -> bool:
        return self._responsive

    @property
    def is_protected(self) -> bool:
        return self._protected

    @property
    def latest_values(self) -> dict[str, Any]:
        return {}

    @property
    def active_alarms(self) -> list[Any]:
        return []

    @property
    def capabilities(self) -> dict[str, Any]:
        return {}

    def has_capability(self, capability: Any) -> bool:
        return False

    def resolve_point(self, capability: Any, slot: str) -> str:
        raise KeyError(f"no capability {capability} slot {slot}")

    # ---- 事件系統（最小可用）----
    def on(self, event: str, handler: Callable[..., Any]) -> Callable[[], None]:
        self._handlers.setdefault(event, []).append(handler)

        def _unsub() -> None:
            if handler in self._handlers.get(event, []):
                self._handlers[event].remove(handler)

        return _unsub

    def emit(self, event: str, payload: Any = None) -> None:
        for h in list(self._handlers.get(event, [])):
            h(payload)

    def health(self) -> HealthReport:
        return HealthReport(
            status=HealthStatus.HEALTHY,
            component=f"mock:{self._device_id}",
        )


@pytest.fixture
def mock_device_protocol() -> MockDeviceProtocol:
    """單一 MockDeviceProtocol 實例（純 Protocol，不含 AsyncModbusDevice）。"""
    return MockDeviceProtocol("mock_integration_01")


@pytest.fixture
def make_mock_device_protocol():
    """MockDeviceProtocol factory（可指定 device_id 與旗標）。"""

    def _factory(
        device_id: str = "mock_integration_01",
        *,
        responsive: bool = True,
        protected: bool = False,
        connected: bool = True,
    ) -> MockDeviceProtocol:
        return MockDeviceProtocol(
            device_id,
            responsive=responsive,
            protected=protected,
            connected=connected,
        )

    return _factory
