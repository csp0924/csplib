# =============== Notification Tests - Base ===============
#
# Notification / NotificationEvent / NotificationChannel / NotificationSender 單元測試

from __future__ import annotations

from datetime import datetime

import pytest

from csp_lib.equipment.alarm import AlarmLevel
from csp_lib.notification import (
    EventCategory,
    EventNotification,
    Notification,
    NotificationChannel,
    NotificationDispatcher,
    NotificationEvent,
    NotificationSender,
)

# ======================== NotificationEvent Tests ========================


class TestNotificationEvent:
    """NotificationEvent 枚舉測試"""

    def test_triggered_value(self):
        assert NotificationEvent.TRIGGERED == "triggered"

    def test_resolved_value(self):
        assert NotificationEvent.RESOLVED == "resolved"

    def test_enum_members(self):
        assert set(NotificationEvent) == {
            NotificationEvent.TRIGGERED,
            NotificationEvent.RESOLVED,
        }


# ======================== Notification Tests ========================


class TestNotification:
    """Notification frozen dataclass 測試"""

    def test_construct(self):
        """應能正確建構 Notification"""
        now = datetime.now()
        n = Notification(
            title="[ALARM] device_001 溫度過高",
            body="設備溫度超過閾值",
            level=AlarmLevel.ALARM,
            device_id="device_001",
            alarm_key="device_001:device_alarm:OVER_TEMP",
            event=NotificationEvent.TRIGGERED,
            occurred_at=now,
        )
        assert n.title == "[ALARM] device_001 溫度過高"
        assert n.body == "設備溫度超過閾值"
        assert n.level == AlarmLevel.ALARM
        assert n.device_id == "device_001"
        assert n.alarm_key == "device_001:device_alarm:OVER_TEMP"
        assert n.event == NotificationEvent.TRIGGERED
        assert n.occurred_at == now

    def test_frozen(self):
        """Notification 應為不可變"""
        now = datetime.now()
        n = Notification(
            title="test",
            body="body",
            level=AlarmLevel.INFO,
            device_id="d1",
            alarm_key="d1:disconnect:DISCONNECT",
            event=NotificationEvent.RESOLVED,
            occurred_at=now,
        )
        import pytest

        with pytest.raises(AttributeError):
            n.title = "changed"  # type: ignore[misc]


# ======================== NotificationChannel Tests ========================


class TestNotificationChannel:
    """NotificationChannel ABC 測試"""

    def test_cannot_instantiate_directly(self):
        """不應直接實例化 ABC"""
        import pytest

        with pytest.raises(TypeError):
            NotificationChannel()  # type: ignore[abstract]

    def test_subclass_must_implement(self):
        """子類別必須實作 name 和 send"""
        import pytest

        class IncompleteChannel(NotificationChannel):
            pass

        with pytest.raises(TypeError):
            IncompleteChannel()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_send_batch_default_calls_send(self):
        """send_batch 預設應逐一呼叫 send"""

        class SimpleChannel(NotificationChannel):
            def __init__(self):
                self.sent: list[Notification] = []

            @property
            def name(self) -> str:
                return "simple"

            async def send(self, notification: Notification) -> None:
                self.sent.append(notification)

        ch = SimpleChannel()
        now = datetime.now()
        n = Notification(
            title="test",
            body="body",
            level=AlarmLevel.INFO,
            device_id="d1",
            alarm_key="d1:test:1",
            event=NotificationEvent.TRIGGERED,
            occurred_at=now,
        )
        await ch.send_batch([n])
        assert len(ch.sent) == 1
        assert ch.sent[0] is n

    @pytest.mark.asyncio
    async def test_send_event_default_is_noop(self):
        """send_event 預設應為 no-op"""

        class SimpleChannel(NotificationChannel):
            @property
            def name(self) -> str:
                return "simple"

            async def send(self, notification: Notification) -> None:
                pass

        ch = SimpleChannel()
        event = EventNotification(
            title="test",
            body="body",
            category=EventCategory.SYSTEM,
        )
        # 應不拋錯
        await ch.send_event(event)

    @pytest.mark.asyncio
    async def test_send_batch_with_events_calls_send_event(self):
        """send_batch 預設應對 EventNotification 呼叫 send_event"""

        class TrackingChannel(NotificationChannel):
            def __init__(self):
                self.events: list[EventNotification] = []

            @property
            def name(self) -> str:
                return "tracking"

            async def send(self, notification: Notification) -> None:
                pass

            async def send_event(self, event: EventNotification) -> None:
                self.events.append(event)

        ch = TrackingChannel()
        event = EventNotification(
            title="test",
            body="body",
            category=EventCategory.REPORT,
        )
        await ch.send_batch([event])
        assert len(ch.events) == 1
        assert ch.events[0] is event


# ======================== NotificationSender Protocol Tests ========================


class TestNotificationSender:
    """NotificationSender 協議測試"""

    def test_dispatcher_satisfies_protocol(self):
        """NotificationDispatcher 應滿足 NotificationSender 協議"""
        dispatcher = NotificationDispatcher([])
        assert isinstance(dispatcher, NotificationSender)

    def test_custom_sender_satisfies_protocol(self):
        """自訂類別有 dispatch 方法應滿足 NotificationSender 協議"""

        class CustomSender:
            async def dispatch(self, notification: Notification) -> None:
                pass

        assert isinstance(CustomSender(), NotificationSender)
