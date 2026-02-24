# =============== Manager Schedule Tests - Schema ===============
#
# ScheduleRule Schema 單元測試
#
# 測試覆蓋：
# - ScheduleType / StrategyType 枚舉值
# - ScheduleRule 建立與預設值
# - to_document / from_document 轉換
# - 日期欄位解析
# - 循環轉換一致性

from __future__ import annotations

from datetime import date

from csp_lib.manager.schedule.schema import ScheduleRule, ScheduleType, StrategyType


class TestScheduleType:
    """ScheduleType Enum 測試"""

    def test_values(self):
        assert ScheduleType.ONCE.value == "once"
        assert ScheduleType.DAILY.value == "daily"
        assert ScheduleType.WEEKLY.value == "weekly"

    def test_from_value(self):
        assert ScheduleType("once") == ScheduleType.ONCE
        assert ScheduleType("daily") == ScheduleType.DAILY
        assert ScheduleType("weekly") == ScheduleType.WEEKLY


class TestStrategyType:
    """StrategyType Enum 測試"""

    def test_values(self):
        assert StrategyType.PQ.value == "pq"
        assert StrategyType.PV_SMOOTH.value == "pv_smooth"
        assert StrategyType.QV.value == "qv"
        assert StrategyType.FP.value == "fp"
        assert StrategyType.ISLAND.value == "island"
        assert StrategyType.BYPASS.value == "bypass"
        assert StrategyType.STOP.value == "stop"

    def test_from_value(self):
        assert StrategyType("pq") == StrategyType.PQ
        assert StrategyType("pv_smooth") == StrategyType.PV_SMOOTH


class TestScheduleRule:
    """ScheduleRule 測試"""

    def test_create_with_defaults(self):
        rule = ScheduleRule(
            name="test_rule",
            site_id="site_001",
            schedule_type=ScheduleType.DAILY,
            strategy_type=StrategyType.PQ,
        )

        assert rule.name == "test_rule"
        assert rule.site_id == "site_001"
        assert rule.schedule_type == ScheduleType.DAILY
        assert rule.strategy_type == StrategyType.PQ
        assert rule.strategy_config == {}
        assert rule.start_time == "00:00"
        assert rule.end_time == "23:59"
        assert rule.priority == 0
        assert rule.enabled is True
        assert rule.days_of_week == []
        assert rule.start_date is None
        assert rule.end_date is None

    def test_create_full(self):
        rule = ScheduleRule(
            name="peak_shaving",
            site_id="site_001",
            schedule_type=ScheduleType.WEEKLY,
            strategy_type=StrategyType.PQ,
            strategy_config={"p": 100, "q": 50},
            start_time="09:00",
            end_time="17:00",
            priority=10,
            enabled=True,
            days_of_week=[0, 1, 2, 3, 4],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )

        assert rule.name == "peak_shaving"
        assert rule.strategy_config == {"p": 100, "q": 50}
        assert rule.start_time == "09:00"
        assert rule.end_time == "17:00"
        assert rule.priority == 10
        assert rule.days_of_week == [0, 1, 2, 3, 4]
        assert rule.start_date == date(2026, 1, 1)
        assert rule.end_date == date(2026, 12, 31)

    def test_to_document(self):
        rule = ScheduleRule(
            name="test",
            site_id="site_001",
            schedule_type=ScheduleType.ONCE,
            strategy_type=StrategyType.PV_SMOOTH,
            strategy_config={"capacity": 1000},
            start_time="08:00",
            end_time="16:00",
            priority=5,
            enabled=True,
            days_of_week=[],
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

        doc = rule.to_document()

        assert doc["name"] == "test"
        assert doc["site_id"] == "site_001"
        assert doc["type"] == "once"  # DB field name
        assert doc["strategy_type"] == "pv_smooth"  # Enum.value
        assert doc["strategy_config"] == {"capacity": 1000}
        assert doc["start_time"] == "08:00"
        assert doc["end_time"] == "16:00"
        assert doc["priority"] == 5
        assert doc["enabled"] is True
        assert doc["start_date"] == "2026-03-01"  # ISO string
        assert doc["end_date"] == "2026-03-31"

    def test_to_document_none_dates(self):
        rule = ScheduleRule(
            name="daily",
            site_id="site_001",
            schedule_type=ScheduleType.DAILY,
            strategy_type=StrategyType.STOP,
        )

        doc = rule.to_document()
        assert doc["start_date"] is None
        assert doc["end_date"] is None

    def test_from_document(self):
        doc = {
            "_id": "mongo_object_id_12345",
            "name": "morning",
            "site_id": "site_001",
            "type": "weekly",
            "strategy_type": "pq",
            "strategy_config": {"p": 200, "q": 0},
            "start_time": "06:00",
            "end_time": "12:00",
            "priority": 3,
            "enabled": True,
            "days_of_week": [0, 1, 2, 3, 4],
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        }

        rule = ScheduleRule.from_document(doc)

        assert rule.name == "morning"
        assert rule.site_id == "site_001"
        assert rule.schedule_type == ScheduleType.WEEKLY
        assert rule.strategy_type == StrategyType.PQ
        assert rule.strategy_config == {"p": 200, "q": 0}
        assert rule.start_time == "06:00"
        assert rule.end_time == "12:00"
        assert rule.priority == 3
        assert rule.days_of_week == [0, 1, 2, 3, 4]
        assert rule.start_date == date(2026, 1, 1)
        assert rule.end_date == date(2026, 12, 31)

    def test_from_document_removes_id(self):
        doc = {
            "_id": "mongo_object_id",
            "name": "test",
            "site_id": "site_001",
            "type": "daily",
            "strategy_type": "stop",
            "strategy_config": {},
            "start_time": "00:00",
            "end_time": "23:59",
            "priority": 0,
            "enabled": True,
            "days_of_week": [],
            "start_date": None,
            "end_date": None,
        }

        rule = ScheduleRule.from_document(doc)
        assert rule.name == "test"

    def test_from_document_none_dates(self):
        doc = {
            "name": "daily_rule",
            "site_id": "site_001",
            "type": "daily",
            "strategy_type": "bypass",
            "start_date": None,
            "end_date": None,
        }

        rule = ScheduleRule.from_document(doc)
        assert rule.start_date is None
        assert rule.end_date is None

    def test_roundtrip(self):
        original = ScheduleRule(
            name="roundtrip_test",
            site_id="site_002",
            schedule_type=ScheduleType.WEEKLY,
            strategy_type=StrategyType.FP,
            strategy_config={"f_base": 60.0, "f1": -0.5},
            start_time="10:00",
            end_time="18:00",
            priority=7,
            enabled=True,
            days_of_week=[0, 2, 4],
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )

        doc = original.to_document()
        restored = ScheduleRule.from_document(doc)

        assert restored.name == original.name
        assert restored.site_id == original.site_id
        assert restored.schedule_type == original.schedule_type
        assert restored.strategy_type == original.strategy_type
        assert restored.strategy_config == original.strategy_config
        assert restored.start_time == original.start_time
        assert restored.end_time == original.end_time
        assert restored.priority == original.priority
        assert restored.enabled == original.enabled
        assert restored.days_of_week == original.days_of_week
        assert restored.start_date == original.start_date
        assert restored.end_date == original.end_date
