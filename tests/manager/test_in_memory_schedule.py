# =============== Manager Tests - In-Memory Schedule Repository + Matcher ===============
#
# InMemoryScheduleRepository + matcher 單元測試
#
# 測試覆蓋：
# - upsert / get_all_enabled 基本流程
# - find_active_rules 時間過濾
# - find_active_rules 跨午夜排程
# - matcher.matches_time 正常 / 跨午夜
# - matcher.matches_schedule 各種 ScheduleType
# - 測試輔助方法：clear, get_all_rules

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from csp_lib.manager.schedule.in_memory import InMemoryScheduleRepository
from csp_lib.manager.schedule.matcher import matches_schedule, matches_time
from csp_lib.manager.schedule.schema import ScheduleRule, ScheduleType, StrategyType


def _make_rule(
    name: str = "rule_1",
    site_id: str = "site_a",
    schedule_type: ScheduleType = ScheduleType.DAILY,
    start_time: str = "08:00",
    end_time: str = "18:00",
    priority: int = 10,
    enabled: bool = True,
    days_of_week: list[int] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ScheduleRule:
    """建立測試用 ScheduleRule"""
    return ScheduleRule(
        name=name,
        site_id=site_id,
        schedule_type=schedule_type,
        strategy_type=StrategyType.PQ,
        strategy_config={"p": 100},
        start_time=start_time,
        end_time=end_time,
        priority=priority,
        enabled=enabled,
        days_of_week=days_of_week or [],
        start_date=start_date,
        end_date=end_date,
    )


# ======================== Matcher - matches_time ========================


class TestMatchesTime:
    """matches_time 純函式測試"""

    def test_normal_time_range_inside(self):
        """正常時段內：08:00 <= 12:00 <= 18:00"""
        rule = _make_rule(start_time="08:00", end_time="18:00")
        assert matches_time(rule, "12:00") is True

    def test_normal_time_range_at_start(self):
        """正常時段邊界：start_time"""
        rule = _make_rule(start_time="08:00", end_time="18:00")
        assert matches_time(rule, "08:00") is True

    def test_normal_time_range_at_end(self):
        """正常時段邊界：end_time"""
        rule = _make_rule(start_time="08:00", end_time="18:00")
        assert matches_time(rule, "18:00") is True

    def test_normal_time_range_outside_before(self):
        """正常時段外（早）"""
        rule = _make_rule(start_time="08:00", end_time="18:00")
        assert matches_time(rule, "07:59") is False

    def test_normal_time_range_outside_after(self):
        """正常時段外（晚）"""
        rule = _make_rule(start_time="08:00", end_time="18:00")
        assert matches_time(rule, "18:01") is False

    def test_midnight_crossing_late_night(self):
        """跨午夜：22:00-06:00，23:00 應匹配"""
        rule = _make_rule(start_time="22:00", end_time="06:00")
        assert matches_time(rule, "23:00") is True

    def test_midnight_crossing_early_morning(self):
        """跨午夜：22:00-06:00，03:00 應匹配"""
        rule = _make_rule(start_time="22:00", end_time="06:00")
        assert matches_time(rule, "03:00") is True

    def test_midnight_crossing_outside(self):
        """跨午夜：22:00-06:00，12:00 不匹配"""
        rule = _make_rule(start_time="22:00", end_time="06:00")
        assert matches_time(rule, "12:00") is False

    def test_midnight_crossing_at_start(self):
        """跨午夜邊界：start_time"""
        rule = _make_rule(start_time="22:00", end_time="06:00")
        assert matches_time(rule, "22:00") is True

    def test_midnight_crossing_at_end(self):
        """跨午夜邊界：end_time"""
        rule = _make_rule(start_time="22:00", end_time="06:00")
        assert matches_time(rule, "06:00") is True


# ======================== Matcher - matches_schedule ========================


class TestMatchesSchedule:
    """matches_schedule 純函式測試"""

    def test_daily_always_matches(self):
        """DAILY 永遠匹配"""
        rule = _make_rule(schedule_type=ScheduleType.DAILY)
        assert matches_schedule(rule, now_weekday=0, now_date=date(2024, 1, 1)) is True

    def test_weekly_matching_day(self):
        """WEEKLY 匹配的星期幾"""
        rule = _make_rule(schedule_type=ScheduleType.WEEKLY, days_of_week=[0, 2, 4])  # 一三五
        assert matches_schedule(rule, now_weekday=0, now_date=date(2024, 1, 1)) is True

    def test_weekly_non_matching_day(self):
        """WEEKLY 不匹配的星期幾"""
        rule = _make_rule(schedule_type=ScheduleType.WEEKLY, days_of_week=[0, 2, 4])
        assert matches_schedule(rule, now_weekday=1, now_date=date(2024, 1, 1)) is False

    def test_once_within_range(self):
        """ONCE 在日期範圍內"""
        rule = _make_rule(
            schedule_type=ScheduleType.ONCE,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        assert matches_schedule(rule, now_weekday=0, now_date=date(2024, 1, 15)) is True

    def test_once_before_start(self):
        """ONCE 在開始日期之前"""
        rule = _make_rule(
            schedule_type=ScheduleType.ONCE,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 28),
        )
        assert matches_schedule(rule, now_weekday=0, now_date=date(2024, 1, 31)) is False

    def test_once_after_end(self):
        """ONCE 在結束日期之後"""
        rule = _make_rule(
            schedule_type=ScheduleType.ONCE,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )
        assert matches_schedule(rule, now_weekday=0, now_date=date(2024, 2, 1)) is False

    def test_once_no_dates(self):
        """ONCE 無日期限制 → 永遠匹配"""
        rule = _make_rule(schedule_type=ScheduleType.ONCE)
        assert matches_schedule(rule, now_weekday=3, now_date=date(2024, 6, 1)) is True

    def test_once_only_start_date(self):
        """ONCE 只有 start_date"""
        rule = _make_rule(schedule_type=ScheduleType.ONCE, start_date=date(2024, 3, 1))
        assert matches_schedule(rule, now_weekday=0, now_date=date(2024, 3, 1)) is True
        assert matches_schedule(rule, now_weekday=0, now_date=date(2024, 2, 28)) is False


# ======================== InMemoryScheduleRepository ========================


class TestInMemoryScheduleRepository:
    """InMemoryScheduleRepository 功能測試"""

    async def test_upsert_and_get_all_enabled(self):
        """upsert + get_all_enabled 基本流程"""
        repo = InMemoryScheduleRepository()
        rule = _make_rule(name="r1", site_id="s1")
        name = await repo.upsert(rule)
        assert name == "r1"

        enabled = await repo.get_all_enabled("s1")
        assert len(enabled) == 1
        assert enabled[0].name == "r1"

    async def test_upsert_updates_existing(self):
        """upsert 相同 (site_id, name) 會覆蓋"""
        repo = InMemoryScheduleRepository()
        await repo.upsert(_make_rule(name="r1", site_id="s1", priority=5))
        await repo.upsert(_make_rule(name="r1", site_id="s1", priority=99))

        enabled = await repo.get_all_enabled("s1")
        assert len(enabled) == 1
        assert enabled[0].priority == 99

    async def test_get_all_enabled_filters_disabled(self):
        """get_all_enabled 不回傳 disabled 規則"""
        repo = InMemoryScheduleRepository()
        await repo.upsert(_make_rule(name="active", enabled=True))
        await repo.upsert(_make_rule(name="disabled", enabled=False))

        enabled = await repo.get_all_enabled("site_a")
        assert len(enabled) == 1
        assert enabled[0].name == "active"

    async def test_get_all_enabled_filters_site(self):
        """get_all_enabled 依 site_id 過濾"""
        repo = InMemoryScheduleRepository()
        await repo.upsert(_make_rule(name="r1", site_id="s1"))
        await repo.upsert(_make_rule(name="r2", site_id="s2"))

        s1_rules = await repo.get_all_enabled("s1")
        assert len(s1_rules) == 1
        assert s1_rules[0].name == "r1"

    async def test_find_active_rules_time_match(self):
        """find_active_rules 時間匹配"""
        repo = InMemoryScheduleRepository()
        await repo.upsert(_make_rule(name="morning", start_time="06:00", end_time="12:00", priority=10))
        await repo.upsert(_make_rule(name="evening", start_time="18:00", end_time="23:00", priority=20))

        # 10:00 只匹配 morning
        now = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
        active = await repo.find_active_rules("site_a", now)
        assert len(active) == 1
        assert active[0].name == "morning"

    async def test_find_active_rules_priority_desc(self):
        """find_active_rules 按 priority DESC 排序"""
        repo = InMemoryScheduleRepository()
        await repo.upsert(_make_rule(name="low", priority=1, start_time="00:00", end_time="23:59"))
        await repo.upsert(_make_rule(name="high", priority=100, start_time="00:00", end_time="23:59"))
        await repo.upsert(_make_rule(name="mid", priority=50, start_time="00:00", end_time="23:59"))

        now = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)
        active = await repo.find_active_rules("site_a", now)
        assert [r.name for r in active] == ["high", "mid", "low"]

    async def test_find_active_rules_midnight_crossing(self):
        """find_active_rules 跨午夜排程"""
        repo = InMemoryScheduleRepository()
        await repo.upsert(_make_rule(name="night", start_time="22:00", end_time="06:00"))

        # 23:30 應匹配
        now_late = datetime(2024, 3, 1, 23, 30, tzinfo=timezone.utc)
        active = await repo.find_active_rules("site_a", now_late)
        assert len(active) == 1

        # 03:00 也應匹配
        now_early = datetime(2024, 3, 2, 3, 0, tzinfo=timezone.utc)
        active = await repo.find_active_rules("site_a", now_early)
        assert len(active) == 1

        # 12:00 不匹配
        now_noon = datetime(2024, 3, 2, 12, 0, tzinfo=timezone.utc)
        active = await repo.find_active_rules("site_a", now_noon)
        assert len(active) == 0

    async def test_find_active_rules_weekly_filter(self):
        """find_active_rules 星期過濾"""
        repo = InMemoryScheduleRepository()
        # 只在星期一(0)生效
        await repo.upsert(
            _make_rule(
                name="monday_only",
                schedule_type=ScheduleType.WEEKLY,
                days_of_week=[0],
                start_time="00:00",
                end_time="23:59",
            )
        )

        # 2024-01-01 是星期一
        monday = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert len(await repo.find_active_rules("site_a", monday)) == 1

        # 2024-01-02 是星期二
        tuesday = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
        assert len(await repo.find_active_rules("site_a", tuesday)) == 0

    async def test_clear(self):
        """clear 清除所有規則"""
        repo = InMemoryScheduleRepository()
        await repo.upsert(_make_rule())
        repo.clear()
        assert repo.get_all_rules() == {}

    async def test_get_all_rules(self):
        """get_all_rules 回傳所有規則"""
        repo = InMemoryScheduleRepository()
        await repo.upsert(_make_rule(name="a", site_id="s1"))
        await repo.upsert(_make_rule(name="b", site_id="s1"))
        assert len(repo.get_all_rules()) == 2

    async def test_health_check(self):
        """health_check 回傳 True"""
        repo = InMemoryScheduleRepository()
        assert await repo.health_check() is True


# ======================== Parametrized Edge Cases ========================


class TestMatcherEdgeCases:
    """Matcher 邊界情況"""

    @pytest.mark.parametrize(
        ("start", "end", "now", "expected"),
        [
            ("00:00", "23:59", "12:00", True),  # 全天
            ("00:00", "00:00", "00:00", True),  # 零長度（start == end）
            ("12:00", "12:00", "12:00", True),  # 零長度 at noon
            ("12:00", "12:00", "13:00", False),  # 零長度 miss
        ],
    )
    def test_edge_time_ranges(self, start: str, end: str, now: str, expected: bool):
        """邊界時間範圍測試"""
        rule = _make_rule(start_time=start, end_time=end)
        assert matches_time(rule, now) is expected
