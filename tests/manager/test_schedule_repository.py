# =============== Manager Schedule Tests - Repository ===============
#
# MongoScheduleRepository 單元測試
#
# 測試覆蓋：
# - 每日/每週/單次排程匹配
# - 跨午夜時段處理
# - Priority 排序
# - 停用規則過濾
# - 時間邊界條件

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from csp_lib.manager.schedule.repository import MongoScheduleRepository
from csp_lib.manager.schedule.schema import ScheduleRule, ScheduleType, StrategyType


def _make_rule(
    name: str = "rule",
    schedule_type: ScheduleType = ScheduleType.DAILY,
    strategy_type: StrategyType = StrategyType.PQ,
    start_time: str = "00:00",
    end_time: str = "23:59",
    priority: int = 0,
    enabled: bool = True,
    days_of_week: list[int] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ScheduleRule:
    return ScheduleRule(
        name=name,
        site_id="site_001",
        schedule_type=schedule_type,
        strategy_type=strategy_type,
        start_time=start_time,
        end_time=end_time,
        priority=priority,
        enabled=enabled,
        days_of_week=days_of_week or [],
        start_date=start_date,
        end_date=end_date,
    )


class _MockCursor:
    """模擬 Motor async cursor"""

    def __init__(self, docs: list[dict]):
        self._docs = docs
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return doc


def _build_repo_with_rules(rules: list[ScheduleRule]) -> MongoScheduleRepository:
    """建立帶有預設規則的 Repository"""
    docs = [rule.to_document() for rule in rules]

    db = MagicMock()
    collection = MagicMock()
    # 每次呼叫 find 都回傳新的 cursor（避免 cursor 被耗盡）
    collection.find = MagicMock(side_effect=lambda *args, **kwargs: _MockCursor(docs))
    db.__getitem__ = MagicMock(return_value=collection)

    return MongoScheduleRepository(db)


class TestMatchesTime:
    """時間匹配測試"""

    def test_normal_range(self):
        rule = _make_rule(start_time="09:00", end_time="17:00")
        assert MongoScheduleRepository._matches_time(rule, "09:00") is True
        assert MongoScheduleRepository._matches_time(rule, "12:00") is True
        assert MongoScheduleRepository._matches_time(rule, "17:00") is True
        assert MongoScheduleRepository._matches_time(rule, "08:59") is False
        assert MongoScheduleRepository._matches_time(rule, "17:01") is False

    def test_cross_midnight(self):
        rule = _make_rule(start_time="22:00", end_time="06:00")
        assert MongoScheduleRepository._matches_time(rule, "22:00") is True
        assert MongoScheduleRepository._matches_time(rule, "23:30") is True
        assert MongoScheduleRepository._matches_time(rule, "00:00") is True
        assert MongoScheduleRepository._matches_time(rule, "05:59") is True
        assert MongoScheduleRepository._matches_time(rule, "06:00") is True
        assert MongoScheduleRepository._matches_time(rule, "21:59") is False
        assert MongoScheduleRepository._matches_time(rule, "06:01") is False

    def test_full_day(self):
        rule = _make_rule(start_time="00:00", end_time="23:59")
        assert MongoScheduleRepository._matches_time(rule, "00:00") is True
        assert MongoScheduleRepository._matches_time(rule, "12:00") is True
        assert MongoScheduleRepository._matches_time(rule, "23:59") is True


class TestMatchesSchedule:
    """排程類型匹配測試"""

    def test_daily_always_matches(self):
        rule = _make_rule(schedule_type=ScheduleType.DAILY)
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 1, 1)) is True
        assert MongoScheduleRepository._matches_schedule(rule, 6, date(2026, 12, 31)) is True

    def test_weekly_matches_day(self):
        rule = _make_rule(schedule_type=ScheduleType.WEEKLY, days_of_week=[0, 2, 4])
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 1, 1)) is True  # Mon
        assert MongoScheduleRepository._matches_schedule(rule, 2, date(2026, 1, 1)) is True  # Wed
        assert MongoScheduleRepository._matches_schedule(rule, 4, date(2026, 1, 1)) is True  # Fri
        assert MongoScheduleRepository._matches_schedule(rule, 1, date(2026, 1, 1)) is False  # Tue
        assert MongoScheduleRepository._matches_schedule(rule, 5, date(2026, 1, 1)) is False  # Sat

    def test_once_within_range(self):
        rule = _make_rule(
            schedule_type=ScheduleType.ONCE,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 3, 1)) is True
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 3, 15)) is True
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 3, 31)) is True
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 2, 28)) is False
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 4, 1)) is False

    def test_once_no_dates(self):
        rule = _make_rule(schedule_type=ScheduleType.ONCE)
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 1, 1)) is True

    def test_once_only_start_date(self):
        rule = _make_rule(schedule_type=ScheduleType.ONCE, start_date=date(2026, 6, 1))
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 6, 1)) is True
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 12, 31)) is True
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 5, 31)) is False

    def test_once_only_end_date(self):
        rule = _make_rule(schedule_type=ScheduleType.ONCE, end_date=date(2026, 6, 30))
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 1, 1)) is True
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 6, 30)) is True
        assert MongoScheduleRepository._matches_schedule(rule, 0, date(2026, 7, 1)) is False


class TestFindActiveRules:
    """find_active_rules 整合測試"""

    @pytest.mark.asyncio
    async def test_priority_sorting(self):
        rules = [
            _make_rule(name="low", priority=1),
            _make_rule(name="high", priority=10),
            _make_rule(name="mid", priority=5),
        ]
        repo = _build_repo_with_rules(rules)

        tz = ZoneInfo("Asia/Taipei")
        now = datetime(2026, 3, 15, 12, 0, tzinfo=tz)
        result = await repo.find_active_rules("site_001", now)

        assert len(result) == 3
        assert result[0].name == "high"
        assert result[1].name == "mid"
        assert result[2].name == "low"

    @pytest.mark.asyncio
    async def test_time_filtering(self):
        rules = [
            _make_rule(name="morning", start_time="06:00", end_time="12:00"),
            _make_rule(name="afternoon", start_time="13:00", end_time="18:00"),
        ]
        repo = _build_repo_with_rules(rules)

        tz = ZoneInfo("Asia/Taipei")
        now = datetime(2026, 3, 15, 10, 0, tzinfo=tz)  # 10:00
        result = await repo.find_active_rules("site_001", now)

        assert len(result) == 1
        assert result[0].name == "morning"

    @pytest.mark.asyncio
    async def test_weekly_filtering(self):
        # 2026-03-16 is Monday (weekday=0)
        rules = [
            _make_rule(name="weekday", schedule_type=ScheduleType.WEEKLY, days_of_week=[0, 1, 2, 3, 4]),
            _make_rule(name="weekend", schedule_type=ScheduleType.WEEKLY, days_of_week=[5, 6]),
        ]
        repo = _build_repo_with_rules(rules)

        tz = ZoneInfo("Asia/Taipei")
        now = datetime(2026, 3, 16, 12, 0, tzinfo=tz)  # Monday
        result = await repo.find_active_rules("site_001", now)

        assert len(result) == 1
        assert result[0].name == "weekday"

    @pytest.mark.asyncio
    async def test_cross_midnight_rule(self):
        rules = [
            _make_rule(name="night", start_time="22:00", end_time="06:00"),
        ]
        repo = _build_repo_with_rules(rules)

        tz = ZoneInfo("Asia/Taipei")

        # 23:00 should match
        now_late = datetime(2026, 3, 15, 23, 0, tzinfo=tz)
        result = await repo.find_active_rules("site_001", now_late)
        assert len(result) == 1

        # 03:00 should match
        now_early = datetime(2026, 3, 16, 3, 0, tzinfo=tz)
        result = await repo.find_active_rules("site_001", now_early)
        assert len(result) == 1

        # 12:00 should not match
        now_noon = datetime(2026, 3, 15, 12, 0, tzinfo=tz)
        result = await repo.find_active_rules("site_001", now_noon)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_no_matching_rules(self):
        rules = [
            _make_rule(name="afternoon", start_time="13:00", end_time="18:00"),
        ]
        repo = _build_repo_with_rules(rules)

        tz = ZoneInfo("Asia/Taipei")
        now = datetime(2026, 3, 15, 10, 0, tzinfo=tz)  # 10:00
        result = await repo.find_active_rules("site_001", now)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_upsert(self):
        db = MagicMock()
        collection = MagicMock()
        collection.update_one = AsyncMock(return_value=MagicMock(upserted_id="new_id"))
        db.__getitem__ = MagicMock(return_value=collection)

        repo = MongoScheduleRepository(db)
        rule = _make_rule(name="test_upsert")
        result = await repo.upsert(rule)

        assert result == "new_id"
        collection.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_existing(self):
        db = MagicMock()
        collection = MagicMock()
        collection.update_one = AsyncMock(return_value=MagicMock(upserted_id=None))
        db.__getitem__ = MagicMock(return_value=collection)

        repo = MongoScheduleRepository(db)
        rule = _make_rule(name="existing_rule")
        result = await repo.upsert(rule)

        assert result == "existing_rule"

    @pytest.mark.asyncio
    async def test_ensure_indexes(self):
        db = MagicMock()
        collection = MagicMock()
        collection.create_indexes = AsyncMock()
        db.__getitem__ = MagicMock(return_value=collection)

        repo = MongoScheduleRepository(db)
        await repo.ensure_indexes()

        collection.create_indexes.assert_called_once()
