# =============== Notification Tests - Batcher ===============
#
# NotificationBatcher 單元測試
#
# 測試覆蓋：
#   - 基本入隊 + flush
#   - 防抖：同一時間窗多則通知 → 單次 batch
#   - 去重：相同 alarm_key → 僅保留最新
#   - 分組：不同 level 分組發送
#   - 立即發送（dispatch_immediate / immediate event）
#   - 生命週期（start/stop、最終 flush）
#   - 通道失敗隔離
#   - 閾值 flush

from __future__ import annotations

from datetime import datetime
from typing import Sequence
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.alarm import AlarmLevel
from csp_lib.notification import (
    BatchNotificationConfig,
    EventCategory,
    EventNotification,
    Notification,
    NotificationBatcher,
    NotificationChannel,
    NotificationEvent,
    NotificationItem,
)

# ======================== Helpers ========================


class MockChannel(NotificationChannel):
    """測試用通知通道（記錄所有 send_batch 呼叫）"""

    def __init__(self, channel_name: str):
        self._name = channel_name
        self.send_batch_mock = AsyncMock()
        self.send_mock = AsyncMock()

    @property
    def name(self) -> str:
        return self._name

    async def send(self, notification: Notification) -> None:
        await self.send_mock(notification)

    async def send_batch(self, items: Sequence[NotificationItem]) -> None:
        await self.send_batch_mock(items)


class FailingBatchChannel(NotificationChannel):
    """send_batch 總是失敗的通道"""

    def __init__(self, channel_name: str):
        self._name = channel_name

    @property
    def name(self) -> str:
        return self._name

    async def send(self, notification: Notification) -> None:
        raise RuntimeError("send failed")

    async def send_batch(self, items: Sequence[NotificationItem]) -> None:
        raise RuntimeError("batch send failed")


def _make_notification(
    alarm_key: str = "dev1:device_alarm:OVER_TEMP",
    level: AlarmLevel = AlarmLevel.ALARM,
    event: NotificationEvent = NotificationEvent.TRIGGERED,
) -> Notification:
    return Notification(
        title=f"[{level.name}] test alarm",
        body="test body",
        level=level,
        device_id="dev1",
        alarm_key=alarm_key,
        event=event,
        occurred_at=datetime(2025, 1, 1, 12, 0, 0),
    )


def _make_event(
    category: EventCategory = EventCategory.REPORT,
    immediate: bool = False,
) -> EventNotification:
    return EventNotification(
        title="日報完成",
        body="report body",
        category=category,
        source="reporter",
        immediate=immediate,
    )


# ======================== Basic Queue + Flush ========================


class TestBatcherBasic:
    """基本入隊與 flush 測試"""

    @pytest.mark.asyncio
    async def test_dispatch_and_flush(self):
        """dispatch 後 flush 應透過 send_batch 發送"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        notification = _make_notification()
        await batcher.dispatch(notification)
        assert batcher.pending_count == 1

        await batcher.flush()
        assert batcher.pending_count == 0
        ch.send_batch_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_flush_empty_queue_no_call(self):
        """空佇列 flush 不應呼叫 send_batch"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(channels=[ch])
        await batcher.flush()
        ch.send_batch_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_event_and_flush(self):
        """dispatch_event 後 flush 應透過 send_batch 發送"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        event = _make_event()
        await batcher.dispatch_event(event)
        assert batcher.pending_count == 1

        await batcher.flush()
        assert batcher.pending_count == 0
        ch.send_batch_mock.assert_called()


# ======================== Deduplication ========================


class TestBatcherDeduplication:
    """去重測試"""

    @pytest.mark.asyncio
    async def test_same_alarm_key_keeps_latest(self):
        """同一 alarm_key 僅保留最新一則"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        n1 = _make_notification(alarm_key="dev1:device_alarm:A")
        n2 = _make_notification(alarm_key="dev1:device_alarm:A")
        n3 = _make_notification(alarm_key="dev1:device_alarm:A")

        await batcher.dispatch(n1)
        await batcher.dispatch(n2)
        await batcher.dispatch(n3)
        await batcher.flush()

        # 只有一組 send_batch 呼叫，且該組只有 1 則通知（n3，最新的）
        calls = ch.send_batch_mock.call_args_list
        all_items = []
        for call in calls:
            all_items.extend(call[0][0])
        assert len(all_items) == 1
        assert all_items[0] is n3

    @pytest.mark.asyncio
    async def test_different_alarm_keys_kept(self):
        """不同 alarm_key 全部保留"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        n1 = _make_notification(alarm_key="dev1:device_alarm:A")
        n2 = _make_notification(alarm_key="dev1:device_alarm:B")

        await batcher.dispatch(n1)
        await batcher.dispatch(n2)
        await batcher.flush()

        calls = ch.send_batch_mock.call_args_list
        all_items = []
        for call in calls:
            all_items.extend(call[0][0])
        assert len(all_items) == 2

    @pytest.mark.asyncio
    async def test_dedup_disabled(self):
        """關閉去重時同一 alarm_key 全部保留"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(
                flush_interval=60, batch_size_threshold=1000, deduplicate_by_key=False
            ),
        )
        n1 = _make_notification(alarm_key="dev1:device_alarm:A")
        n2 = _make_notification(alarm_key="dev1:device_alarm:A")

        await batcher.dispatch(n1)
        await batcher.dispatch(n2)
        await batcher.flush()

        calls = ch.send_batch_mock.call_args_list
        all_items = []
        for call in calls:
            all_items.extend(call[0][0])
        assert len(all_items) == 2

    @pytest.mark.asyncio
    async def test_event_notifications_not_deduped(self):
        """EventNotification 不參與去重"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        e1 = _make_event()
        e2 = _make_event()

        await batcher.dispatch_event(e1)
        await batcher.dispatch_event(e2)
        await batcher.flush()

        calls = ch.send_batch_mock.call_args_list
        all_items = []
        for call in calls:
            all_items.extend(call[0][0])
        assert len(all_items) == 2


# ======================== Grouping ========================


class TestBatcherGrouping:
    """分組測試"""

    @pytest.mark.asyncio
    async def test_different_levels_grouped_separately(self):
        """不同 level 的通知應分組發送"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        n_alarm = _make_notification(alarm_key="dev1:device_alarm:A", level=AlarmLevel.ALARM)
        n_warning = _make_notification(alarm_key="dev1:device_alarm:B", level=AlarmLevel.WARNING)

        await batcher.dispatch(n_alarm)
        await batcher.dispatch(n_warning)
        await batcher.flush()

        # 應有 2 次 send_batch 呼叫（每個分組一次）
        assert ch.send_batch_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_events_and_alarms_grouped_separately(self):
        """告警和事件應分組發送"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        n = _make_notification()
        e = _make_event()

        await batcher.dispatch(n)
        await batcher.dispatch_event(e)
        await batcher.flush()

        assert ch.send_batch_mock.call_count == 2


# ======================== Immediate Dispatch ========================


class TestBatcherImmediate:
    """立即發送測試"""

    @pytest.mark.asyncio
    async def test_dispatch_immediate_bypasses_queue(self):
        """dispatch_immediate 應立即發送，不進佇列"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        notification = _make_notification()
        await batcher.dispatch_immediate(notification)

        assert batcher.pending_count == 0
        ch.send_batch_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_immediate_event_bypasses_queue(self):
        """immediate=True 的 EventNotification 應立即發送"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        event = _make_event(immediate=True)
        await batcher.dispatch_event(event)

        assert batcher.pending_count == 0
        ch.send_batch_mock.assert_called_once()


# ======================== Lifecycle ========================


class TestBatcherLifecycle:
    """生命週期測試"""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """start/stop 應正常運作"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=0.1),
        )
        await batcher.start()
        await batcher.stop()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """async with 應正常運作"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=0.1),
        )
        async with batcher:
            pass

    @pytest.mark.asyncio
    async def test_final_flush_on_stop(self):
        """stop 時應 flush 所有殘留通知"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        await batcher.start()
        notification = _make_notification()
        await batcher.dispatch(notification)
        assert batcher.pending_count == 1

        await batcher.stop()
        assert batcher.pending_count == 0
        ch.send_batch_mock.assert_called()


# ======================== Channel Failure ========================


class TestBatcherChannelFailure:
    """通道失敗隔離測試"""

    @pytest.mark.asyncio
    async def test_one_channel_fails_others_still_called(self):
        """一個通道失敗不影響其他通道"""
        good_ch = MockChannel("line")
        bad_ch = FailingBatchChannel("broken")
        good_ch2 = MockChannel("email")

        batcher = NotificationBatcher(
            channels=[good_ch, bad_ch, good_ch2],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        notification = _make_notification()
        await batcher.dispatch(notification)
        await batcher.flush()

        good_ch.send_batch_mock.assert_called()
        good_ch2.send_batch_mock.assert_called()


# ======================== Threshold Flush ========================


class TestBatcherThreshold:
    """閾值 flush 測試"""

    @pytest.mark.asyncio
    async def test_threshold_triggers_flush(self):
        """達到 batch_size_threshold 應自動 flush"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(
                flush_interval=60,
                batch_size_threshold=3,
            ),
        )
        # 送入 3 則不同 key 的通知，第 3 則應觸發 flush
        await batcher.dispatch(_make_notification(alarm_key="dev1:device_alarm:A"))
        await batcher.dispatch(_make_notification(alarm_key="dev1:device_alarm:B"))
        await batcher.dispatch(_make_notification(alarm_key="dev1:device_alarm:C"))

        # flush 已自動觸發
        ch.send_batch_mock.assert_called()


# ======================== Multi-Channel ========================


class TestBatcherMultiChannel:
    """多通道測試"""

    @pytest.mark.asyncio
    async def test_batch_sent_to_all_channels(self):
        """批次應發送到所有通道"""
        ch1 = MockChannel("line")
        ch2 = MockChannel("telegram")
        ch3 = MockChannel("email")

        batcher = NotificationBatcher(
            channels=[ch1, ch2, ch3],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        await batcher.dispatch(_make_notification())
        await batcher.flush()

        ch1.send_batch_mock.assert_called()
        ch2.send_batch_mock.assert_called()
        ch3.send_batch_mock.assert_called()

    @pytest.mark.asyncio
    async def test_channels_property_returns_copy(self):
        """channels 應返回副本"""
        ch = MockChannel("line")
        batcher = NotificationBatcher(channels=[ch])
        channels = batcher.channels
        channels.clear()
        assert len(batcher.channels) == 1
