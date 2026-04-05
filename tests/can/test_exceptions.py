"""CAN Exception error context 測試"""

from __future__ import annotations

import pytest

from csp_lib.can.exceptions import CANConnectionError, CANError, CANSendError, CANTimeoutError


class TestCANErrorBackwardCompat:
    """向後相容：現有用法不受影響"""

    def test_bare_message(self) -> None:
        e = CANError("something failed")
        assert str(e) == "something failed"

    def test_empty(self) -> None:
        e = CANError()
        assert str(e) == ""

    def test_no_context_attrs(self) -> None:
        e = CANError("msg")
        assert e.can_id is None
        assert e.bus_index is None


class TestCANErrorContext:
    """新增的 can_id / bus_index context"""

    def test_can_id_only(self) -> None:
        e = CANError("timeout", can_id=0x100)
        assert "[can_id=0x100] timeout" in str(e)
        assert e.can_id == 0x100
        assert e.bus_index is None

    def test_bus_index_only(self) -> None:
        e = CANError("fail", bus_index=2)
        assert "[bus=2] fail" in str(e)
        assert e.bus_index == 2

    def test_both_context(self) -> None:
        e = CANError("err", can_id=0x0FF, bus_index=0)
        assert "bus=0" in str(e)
        assert "can_id=0x0FF" in str(e)

    def test_hex_format(self) -> None:
        e = CANError("x", can_id=0xA)
        assert "can_id=0x00A" in str(e)


@pytest.mark.parametrize("cls", [CANConnectionError, CANTimeoutError, CANSendError])
class TestSubclassInheritance:
    """子類別自動繼承 context"""

    def test_with_context(self, cls: type[CANError]) -> None:
        e = cls("sub err", can_id=0x200, bus_index=1)
        assert e.can_id == 0x200
        assert e.bus_index == 1
        assert "[bus=1, can_id=0x200]" in str(e)

    def test_bare(self, cls: type[CANError]) -> None:
        e = cls("plain")
        assert str(e) == "plain"
        assert e.can_id is None

    def test_isinstance(self, cls: type[CANError]) -> None:
        e = cls("x")
        assert isinstance(e, CANError)
