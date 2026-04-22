# =============== tests/manager/conftest.py ===============
#
# Manager 層共用測試 fixture。
#
# 提供 ``MockDeviceProtocol``：最小 ``DeviceProtocol`` 實作，**非** AsyncModbusDevice
# 實例，用來驗證 Manager 層對 DeviceProtocol 的型別鬆綁真正生效（不會退化回
# 只接受 AsyncModbusDevice）。

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.transport import WriteResult, WriteStatus


class MockDeviceProtocol:
    """最小 ``DeviceProtocol`` 結構性實作（非 AsyncModbusDevice）。

    用於驗證 Manager 層方法接受任何實作 DeviceProtocol 的設備。
    預設 **不設** ``used_unit_ids``，以便測試沒有此屬性時的 skip 行為。
    """

    def __init__(self, device_id: str = "mock_protocol_01") -> None:
        self._device_id = device_id
        self._handlers: dict[str, list[Callable[..., Any]]] = {}
        # AsyncMock 供呼叫追蹤
        self.read_once = AsyncMock(return_value={})
        self.write = AsyncMock(
            return_value=WriteResult(
                status=WriteStatus.SUCCESS,
                point_name="",
                value=None,
            )
        )

    # ---- DeviceProtocol 屬性 ----
    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def is_connected(self) -> bool:
        return True

    @property
    def is_responsive(self) -> bool:
        return True

    @property
    def is_protected(self) -> bool:
        return False

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
        """同步發送事件（測試用）。"""
        for h in list(self._handlers.get(event, [])):
            h(payload)

    def health(self) -> Any:
        return None


@pytest.fixture
def mock_device_protocol() -> MockDeviceProtocol:
    """單一 MockDeviceProtocol 實例。"""
    return MockDeviceProtocol("mock_protocol_01")


@pytest.fixture
def make_mock_device_protocol():
    """MockDeviceProtocol factory（可指定 device_id）。"""

    def _factory(device_id: str = "mock_protocol_01") -> MockDeviceProtocol:
        return MockDeviceProtocol(device_id)

    return _factory
