# =============== Notification Tests - Event ===============
#
# EventCategory / EventNotification 單元測試

from __future__ import annotations

from datetime import datetime

import pytest

from csp_lib.notification import EventCategory, EventNotification

# ======================== EventCategory Tests ========================


class TestEventCategory:
    """EventCategory 枚舉測試"""

    def test_system_value(self):
        assert EventCategory.SYSTEM == "system"

    def test_report_value(self):
        assert EventCategory.REPORT == "report"

    def test_maintenance_value(self):
        assert EventCategory.MAINTENANCE == "maintenance"

    def test_custom_value(self):
        assert EventCategory.CUSTOM == "custom"

    def test_enum_members(self):
        assert set(EventCategory) == {
            EventCategory.SYSTEM,
            EventCategory.REPORT,
            EventCategory.MAINTENANCE,
            EventCategory.CUSTOM,
        }


# ======================== EventNotification Tests ========================


class TestEventNotification:
    """EventNotification frozen dataclass 測試"""

    def test_construct_minimal(self):
        """最小參數應能正確建構"""
        event = EventNotification(
            title="日報產出完成",
            body="2025-01-01 日報已產出",
            category=EventCategory.REPORT,
        )
        assert event.title == "日報產出完成"
        assert event.body == "2025-01-01 日報已產出"
        assert event.category == EventCategory.REPORT
        assert event.source == ""
        assert event.immediate is False
        assert event.metadata == {}
        assert isinstance(event.occurred_at, datetime)

    def test_construct_full(self):
        """完整參數應能正確建構"""
        now = datetime(2025, 6, 15, 10, 30, 0)
        event = EventNotification(
            title="系統啟動",
            body="控制器已完成初始化",
            category=EventCategory.SYSTEM,
            source="controller",
            immediate=True,
            metadata={"version": "1.0.0"},
            occurred_at=now,
        )
        assert event.title == "系統啟動"
        assert event.category == EventCategory.SYSTEM
        assert event.source == "controller"
        assert event.immediate is True
        assert event.metadata == {"version": "1.0.0"}
        assert event.occurred_at == now

    def test_frozen(self):
        """EventNotification 應為不可變"""
        event = EventNotification(
            title="test",
            body="body",
            category=EventCategory.CUSTOM,
        )
        with pytest.raises(AttributeError):
            event.title = "changed"  # type: ignore[misc]

    def test_metadata_default_is_independent(self):
        """每個實例的 metadata 預設值應獨立"""
        e1 = EventNotification(title="a", body="b", category=EventCategory.CUSTOM)
        e2 = EventNotification(title="c", body="d", category=EventCategory.CUSTOM)
        assert e1.metadata is not e2.metadata
