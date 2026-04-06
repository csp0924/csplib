"""DeviceEventType StrEnum 測試"""

from __future__ import annotations

import pytest

from csp_lib.equipment.device.events import (
    EVENT_ALARM_CLEARED,
    EVENT_ALARM_TRIGGERED,
    EVENT_CAPABILITY_ADDED,
    EVENT_CAPABILITY_REMOVED,
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_POINT_TOGGLED,
    EVENT_READ_COMPLETE,
    EVENT_READ_ERROR,
    EVENT_RECONFIGURED,
    EVENT_RESTARTED,
    EVENT_VALUE_CHANGE,
    EVENT_WRITE_COMPLETE,
    EVENT_WRITE_ERROR,
    DeviceEventType,
)


class TestDeviceEventTypeIsStr:
    """StrEnum 成員應為 str 實例"""

    def test_isinstance_str(self) -> None:
        assert isinstance(DeviceEventType.CONNECTED, str)

    def test_member_count(self) -> None:
        assert len(DeviceEventType) == 14


# 每個 StrEnum 成員與對應的字串常數必須相等
_PAIRS = [
    (DeviceEventType.CONNECTED, EVENT_CONNECTED),
    (DeviceEventType.DISCONNECTED, EVENT_DISCONNECTED),
    (DeviceEventType.READ_COMPLETE, EVENT_READ_COMPLETE),
    (DeviceEventType.READ_ERROR, EVENT_READ_ERROR),
    (DeviceEventType.VALUE_CHANGE, EVENT_VALUE_CHANGE),
    (DeviceEventType.ALARM_TRIGGERED, EVENT_ALARM_TRIGGERED),
    (DeviceEventType.ALARM_CLEARED, EVENT_ALARM_CLEARED),
    (DeviceEventType.WRITE_COMPLETE, EVENT_WRITE_COMPLETE),
    (DeviceEventType.WRITE_ERROR, EVENT_WRITE_ERROR),
    (DeviceEventType.RECONFIGURED, EVENT_RECONFIGURED),
    (DeviceEventType.RESTARTED, EVENT_RESTARTED),
    (DeviceEventType.POINT_TOGGLED, EVENT_POINT_TOGGLED),
    (DeviceEventType.CAPABILITY_ADDED, EVENT_CAPABILITY_ADDED),
    (DeviceEventType.CAPABILITY_REMOVED, EVENT_CAPABILITY_REMOVED),
]


@pytest.mark.parametrize("enum_val,const_val", _PAIRS, ids=[p[1] for p in _PAIRS])
def test_enum_equals_constant(enum_val: DeviceEventType, const_val: str) -> None:
    assert enum_val == const_val


def test_dict_key_compat() -> None:
    """StrEnum 成員可作為 dict key，與字串 key 互通"""
    d: dict[str, int] = {DeviceEventType.VALUE_CHANGE: 1}
    assert d["value_change"] == 1
    assert d[EVENT_VALUE_CHANGE] == 1
