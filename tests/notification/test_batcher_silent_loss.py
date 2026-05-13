# =============== Notification Tests - Batcher Silent Loss ===============
#
# NotificationBatcher silent-loss bug fix 驗證測試
#
# 對應 bug:
#   - H2: _final_flush retry path 不可達 → shutdown 時 channel 失敗 silently discard
#   - H3: _dedup_key 只用 alarm_key → 同 alarm_key 不同 event 互蓋
#         （TRIGGERED + RESOLVED 在同一 flush window → 只剩 RESOLVED）

from __future__ import annotations

from datetime import datetime
from typing import Sequence

import pytest

from csp_lib.equipment.alarm import AlarmLevel
from csp_lib.notification import (
    BatchNotificationConfig,
    Notification,
    NotificationBatcher,
    NotificationChannel,
    NotificationEvent,
    NotificationItem,
)

# ======================== Helpers ========================


class RecordingChannel(NotificationChannel):
    """記錄所有收到的 notification（event, alarm_key）"""

    def __init__(self, channel_name: str = "record") -> None:
        self._name = channel_name
        self.received: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return self._name

    async def send(self, notification: Notification) -> None:
        self.received.append((notification.event.value, notification.alarm_key))

    async def send_batch(self, items: Sequence[NotificationItem]) -> None:
        for item in items:
            if isinstance(item, Notification):
                self.received.append((item.event.value, item.alarm_key))


class AlwaysFailingChannel(NotificationChannel):
    """所有 send_batch 都 raise，模擬 broker 斷線"""

    def __init__(self, channel_name: str = "broken") -> None:
        self._name = channel_name
        self.attempts = 0

    @property
    def name(self) -> str:
        return self._name

    async def send(self, notification: Notification) -> None:
        self.attempts += 1
        raise RuntimeError("simulated channel failure")

    async def send_batch(self, items: Sequence[NotificationItem]) -> None:
        self.attempts += 1
        raise RuntimeError("simulated batch failure")


def _make_notification(
    alarm_key: str,
    event: NotificationEvent = NotificationEvent.TRIGGERED,
    level: AlarmLevel = AlarmLevel.WARNING,
) -> Notification:
    return Notification(
        title=f"alarm {alarm_key} {event.value}",
        body="body",
        level=level,
        device_id="dev1",
        alarm_key=alarm_key,
        event=event,
        occurred_at=datetime(2026, 1, 1, 12, 0, 0),
    )


# ======================== H3: Dedup must distinguish event type ========================


class TestDedupRespectsEventType:
    """H3: dedup 必須區分 TRIGGERED / RESOLVED，不可互蓋"""

    @pytest.mark.asyncio
    async def test_dedup_preserves_triggered_and_resolved(self) -> None:
        """同 alarm_key 但 TRIGGERED + RESOLVED 在同 flush window：兩筆都該 dispatched"""
        ch = RecordingChannel()
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        trig = _make_notification("dev1:alarm:OVER_TEMP", event=NotificationEvent.TRIGGERED)
        resolve = _make_notification("dev1:alarm:OVER_TEMP", event=NotificationEvent.RESOLVED)

        await batcher.dispatch(trig)
        await batcher.dispatch(resolve)
        await batcher.flush()

        events_received = {e for e, _ in ch.received}
        assert "triggered" in events_received, "TRIGGERED should be delivered"
        assert "resolved" in events_received, "RESOLVED should be delivered"
        assert len(ch.received) == 2

    @pytest.mark.asyncio
    async def test_dedup_still_collapses_repeated_same_event(self) -> None:
        """同 alarm_key + 同 event（連續兩次 TRIGGERED）仍 dedup keep-latest"""
        ch = RecordingChannel()
        batcher = NotificationBatcher(
            channels=[ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        t1 = _make_notification("dev1:alarm:OVER_TEMP", event=NotificationEvent.TRIGGERED)
        t2 = _make_notification("dev1:alarm:OVER_TEMP", event=NotificationEvent.TRIGGERED)
        t3 = _make_notification("dev1:alarm:OVER_TEMP", event=NotificationEvent.TRIGGERED)

        await batcher.dispatch(t1)
        await batcher.dispatch(t2)
        await batcher.dispatch(t3)
        await batcher.flush()

        # 三筆同 (alarm_key, event) → 只剩一筆
        assert len(ch.received) == 1
        assert ch.received[0] == ("triggered", "dev1:alarm:OVER_TEMP")


# ======================== H2: Aggregate failure visibility ========================


class TestFinalFlushAggregateFailures:
    """H2: shutdown 時 channel 失敗應有 aggregate observable signal"""

    @pytest.mark.asyncio
    async def test_final_flush_logs_aggregate_error_when_channels_fail(self) -> None:
        """shutdown 時 channel 全失敗應有 ERROR-level aggregate log（非 silent）

        穩定信號優先：
          1. shutdown 後 ``batcher.last_flush_failure_count`` 應非 0（不依賴 log 文字）
          2. log 端 match batcher prefix + 「停止時」（_final_flush ERROR），
             避開依賴 exception 文字（"simulated ... failure"）的 fragile 比對。
        """
        from loguru import logger as loguru_logger

        records: list[tuple[str, str]] = []
        sink_id = loguru_logger.add(
            lambda msg: records.append((msg.record["level"].name, msg.record["message"])),
            level="DEBUG",
        )

        try:
            bad_ch = AlwaysFailingChannel()
            batcher = NotificationBatcher(
                channels=[bad_ch],
                config=BatchNotificationConfig(
                    flush_interval=60,
                    batch_size_threshold=1000,
                    max_queue_size=5000,
                    deduplicate_by_key=False,
                ),
            )
            async with batcher:
                for i in range(10):
                    await batcher.dispatch(_make_notification(f"k#{i}"))

            # shutdown 完成（__aexit__ → _on_stop → _final_flush）
            # 穩定信號 1：last_flush_failure_count 暴露失敗 channel 數
            assert batcher.last_flush_failure_count >= 1, (
                f"Expected last_flush_failure_count >= 1 after shutdown with failing channel, "
                f"got {batcher.last_flush_failure_count}"
            )
            # 穩定信號 2：用 batcher log prefix + 「停止時」 match _final_flush 的 aggregate ERROR
            error_msgs = [m for lvl, m in records if lvl == "ERROR"]
            aggregate = [m for m in error_msgs if "NotificationBatcher" in m and "停止時" in m]
            assert aggregate, (
                f"Expected aggregate ERROR log with 'NotificationBatcher' + '停止時' during shutdown, "
                f"got records: {records}"
            )
        finally:
            loguru_logger.remove(sink_id)

    @pytest.mark.asyncio
    async def test_send_to_channels_reports_failure_count(self) -> None:
        """flush() 完成後 batcher 應暴露失敗 channel 計數（可觀測）"""
        bad_ch = AlwaysFailingChannel()
        good_ch = RecordingChannel("good")
        batcher = NotificationBatcher(
            channels=[bad_ch, good_ch],
            config=BatchNotificationConfig(flush_interval=60, batch_size_threshold=1000),
        )
        await batcher.dispatch(_make_notification("k1"))
        await batcher.flush()

        # 失敗一個 channel，成功一個
        assert batcher.last_flush_failure_count == 1
        # good channel 仍有收到
        assert len(good_ch.received) == 1
