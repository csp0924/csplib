# =============== Notification Tests - Dispatcher ===============
#
# NotificationDispatcher 單元測試
#
# 測試覆蓋：
#   - 多通道扇出
#   - 個別 channel 異常不影響其他
#   - from_alarm_record 工廠方法
#   - 空 channels 列表
#   - dispatch_batch 批次發送

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.alarm import AlarmLevel
from csp_lib.manager.alarm.schema import AlarmRecord, AlarmType
from csp_lib.notification import (
    Notification,
    NotificationChannel,
    NotificationDispatcher,
    NotificationEvent,
)

# ======================== Helpers ========================


class FakeChannel(NotificationChannel):
    """測試用通知通道"""

    def __init__(self, channel_name: str):
        self._name = channel_name
        self._send_mock = AsyncMock()

    @property
    def name(self) -> str:
        return self._name

    async def send(self, notification: Notification) -> None:
        await self._send_mock(notification)


class FailingChannel(NotificationChannel):
    """總是失敗的通知通道"""

    def __init__(self, channel_name: str):
        self._name = channel_name

    @property
    def name(self) -> str:
        return self._name

    async def send(self, notification: Notification) -> None:
        raise RuntimeError(f"{self._name} 發送失敗")


def _make_notification() -> Notification:
    return Notification(
        title="[ALARM] device_001 溫度過高",
        body="設備溫度超過閾值",
        level=AlarmLevel.ALARM,
        device_id="device_001",
        alarm_key="device_001:device_alarm:OVER_TEMP",
        event=NotificationEvent.TRIGGERED,
        occurred_at=datetime(2025, 1, 1, 12, 0, 0),
    )


# ======================== Dispatch Tests ========================


class TestNotificationDispatcherDispatch:
    """dispatch 扇出測試"""

    @pytest.mark.asyncio
    async def test_dispatch_to_all_channels(self):
        """應將通知發送到所有通道"""
        ch1 = FakeChannel("line")
        ch2 = FakeChannel("telegram")
        ch3 = FakeChannel("email")
        dispatcher = NotificationDispatcher([ch1, ch2, ch3])

        notification = _make_notification()
        await dispatcher.dispatch(notification)

        ch1._send_mock.assert_called_once_with(notification)
        ch2._send_mock.assert_called_once_with(notification)
        ch3._send_mock.assert_called_once_with(notification)

    @pytest.mark.asyncio
    async def test_channel_failure_does_not_affect_others(self):
        """個別通道失敗不應影響其他通道"""
        ch1 = FakeChannel("line")
        failing = FailingChannel("broken")
        ch2 = FakeChannel("email")
        dispatcher = NotificationDispatcher([ch1, failing, ch2])

        notification = _make_notification()
        await dispatcher.dispatch(notification)

        ch1._send_mock.assert_called_once_with(notification)
        ch2._send_mock.assert_called_once_with(notification)

    @pytest.mark.asyncio
    async def test_empty_channels_no_error(self):
        """空 channels 列表不應報錯"""
        dispatcher = NotificationDispatcher([])
        notification = _make_notification()
        await dispatcher.dispatch(notification)  # 不應拋錯

    @pytest.mark.asyncio
    async def test_all_channels_fail_no_error(self):
        """所有通道都失敗也不應拋錯"""
        failing1 = FailingChannel("ch1")
        failing2 = FailingChannel("ch2")
        dispatcher = NotificationDispatcher([failing1, failing2])

        notification = _make_notification()
        await dispatcher.dispatch(notification)  # 不應拋錯


# ======================== from_alarm_record Tests ========================


class TestNotificationDispatcherFromAlarmRecord:
    """from_alarm_record 工廠方法測試"""

    def test_triggered_notification(self):
        """TRIGGERED 通知應正確建構"""
        record = AlarmRecord(
            alarm_key="device_001:device_alarm:OVER_TEMP",
            device_id="device_001",
            alarm_type=AlarmType.DEVICE_ALARM,
            name="溫度過高",
            level=AlarmLevel.ALARM,
            description="設備溫度超過閾值",
            occurred_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        notification = NotificationDispatcher.from_alarm_record(record, NotificationEvent.TRIGGERED)

        assert notification.event == NotificationEvent.TRIGGERED
        assert notification.device_id == "device_001"
        assert notification.alarm_key == "device_001:device_alarm:OVER_TEMP"
        assert notification.level == AlarmLevel.ALARM
        assert "觸發" in notification.title
        assert "device_001" in notification.title
        assert notification.occurred_at == datetime(2025, 1, 1, 12, 0, 0)

    def test_resolved_notification(self):
        """RESOLVED 通知應正確建構"""
        record = AlarmRecord(
            alarm_key="device_001:disconnect:DISCONNECT",
            device_id="device_001",
            alarm_type=AlarmType.DISCONNECT,
            name="設備斷線",
            level=AlarmLevel.WARNING,
            description="Connection timeout",
            occurred_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        notification = NotificationDispatcher.from_alarm_record(record, NotificationEvent.RESOLVED)

        assert notification.event == NotificationEvent.RESOLVED
        assert notification.device_id == "device_001"
        assert notification.level == AlarmLevel.WARNING
        assert "解除" in notification.title

    def test_no_description_uses_name(self):
        """無 description 時 body 應使用 name"""
        record = AlarmRecord(
            alarm_key="device_001:device_alarm:CODE1",
            device_id="device_001",
            alarm_type=AlarmType.DEVICE_ALARM,
            name="某告警",
            level=AlarmLevel.INFO,
            description="",
            occurred_at=datetime(2025, 1, 1),
        )
        notification = NotificationDispatcher.from_alarm_record(record, NotificationEvent.TRIGGERED)
        assert notification.body == "某告警"

    def test_no_occurred_at_uses_now(self):
        """無 occurred_at 時應使用 datetime.now()"""
        record = AlarmRecord(
            alarm_key="device_001:device_alarm:CODE1",
            device_id="device_001",
            alarm_type=AlarmType.DEVICE_ALARM,
            name="某告警",
            level=AlarmLevel.INFO,
        )
        notification = NotificationDispatcher.from_alarm_record(record, NotificationEvent.TRIGGERED)
        assert notification.occurred_at is not None


# ======================== Properties Tests ========================


class TestNotificationDispatcherDispatchBatch:
    """dispatch_batch 批次發送測試"""

    @pytest.mark.asyncio
    async def test_dispatch_batch_calls_send_batch(self):
        """dispatch_batch 應呼叫各通道的 send_batch"""
        ch1 = FakeChannel("line")
        ch2 = FakeChannel("telegram")
        dispatcher = NotificationDispatcher([ch1, ch2])

        notifications = [_make_notification(), _make_notification()]
        await dispatcher.dispatch_batch(notifications)

        # send_batch 是 NotificationChannel 的預設實作，會逐一呼叫 send
        assert ch1._send_mock.call_count == 2
        assert ch2._send_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_dispatch_batch_channel_failure_isolated(self):
        """dispatch_batch 通道失敗不影響其他通道"""
        ch = FakeChannel("line")
        failing = FailingChannel("broken")
        dispatcher = NotificationDispatcher([failing, ch])

        notifications = [_make_notification()]
        await dispatcher.dispatch_batch(notifications)

        ch._send_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_batch_empty(self):
        """空列表不應報錯"""
        ch = FakeChannel("line")
        dispatcher = NotificationDispatcher([ch])
        await dispatcher.dispatch_batch([])
        ch._send_mock.assert_not_called()


# ======================== Properties Tests ========================


class TestNotificationDispatcherProperties:
    """屬性測試"""

    def test_channels_returns_copy(self):
        """channels 應返回副本"""
        ch = FakeChannel("line")
        dispatcher = NotificationDispatcher([ch])
        channels = dispatcher.channels
        channels.clear()
        assert len(dispatcher.channels) == 1
