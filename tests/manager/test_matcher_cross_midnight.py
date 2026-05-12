# =============== Manager Schedule Tests - Matcher 跨午夜 ===============
#
# 針對 ``csp_lib.manager.schedule.matcher`` 的跨午夜回歸測試。
#
# 背景：當 ScheduleRule 的時段跨午夜（``start_time > end_time``）時，
# ``matches_time`` 會正確匹配「午夜前 + 午夜後」兩段；但 ``matches_schedule``
# 過去只比對「呼叫當下的 weekday/date」對應 ``rule.days_of_week`` / 日期範圍，
# 導致午夜後尾段（屬於規則 "起算日" 的延伸）被錯誤淘汰，產生 silent skip。
#
# 範例：WEEKLY rule days_of_week=[6] (Sunday), 23:30-00:30
#   - Sun 23:45 → weekday=6, 應 match
#   - Mon 00:15 → weekday=0，但屬於 Sun 23:30 的延伸 → 仍應 match
#
# 對稱情境：WEEKLY rule days_of_week=[0] (Monday), 23:30-00:30
#   - Sun 23:45 → 不該 match（午夜前不屬於 Mon）
#   - Mon 00:15 → 屬於 Sun 23:30 的延伸 → 不該被誤判為 Mon
#
# ONCE rule 採類比邏輯：午夜後尾段隸屬於 ``now_date - 1 day``。

from __future__ import annotations

from datetime import date

import pytest

from csp_lib.manager.schedule.matcher import matches_schedule, matches_time
from csp_lib.manager.schedule.schema import ScheduleRule, ScheduleType, StrategyType


def _rule(
    *,
    schedule_type: ScheduleType = ScheduleType.WEEKLY,
    start_time: str = "23:30",
    end_time: str = "00:30",
    days_of_week: list[int] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ScheduleRule:
    return ScheduleRule(
        name="cross_midnight",
        site_id="site_001",
        schedule_type=schedule_type,
        strategy_type=StrategyType.PQ,
        start_time=start_time,
        end_time=end_time,
        days_of_week=days_of_week or [],
        start_date=start_date,
        end_date=end_date,
    )


class TestWeeklyCrossMidnight:
    """WEEKLY × 跨午夜：午夜後尾段必須仍 match 起算日的 weekday。"""

    def test_pre_midnight_on_listed_day_matches(self):
        # Sun (weekday=6) 23:45，rule days=[6]，rule 23:30-00:30
        rule = _rule(days_of_week=[6])
        # Mon 2026-03-16 為 weekday=0，故 Sun 為 2026-03-15
        assert matches_time(rule, "23:45") is True
        assert matches_schedule(rule, now_weekday=6, now_date=date(2026, 3, 15), now_time_str="23:45") is True

    def test_post_midnight_tail_still_matches_origin_day(self):
        # 跨午夜尾段：Mon 00:15 屬於 Sun 23:30 的延伸 → 仍應 match
        rule = _rule(days_of_week=[6])  # Sunday
        assert matches_time(rule, "00:15") is True
        # 此時 now.weekday()=0 (Mon)，now.date()=2026-03-16
        # 應 match，因為這是 Sun rule 的延伸
        assert matches_schedule(rule, now_weekday=0, now_date=date(2026, 3, 16), now_time_str="00:15") is True

    def test_post_midnight_tail_does_not_overcorrect(self):
        # 對稱：rule days=[0] (Mon)，Sun 23:45 不該 match
        rule = _rule(days_of_week=[0])
        assert matches_time(rule, "23:45") is True
        assert matches_schedule(rule, now_weekday=6, now_date=date(2026, 3, 15), now_time_str="23:45") is False

    def test_post_midnight_tail_matches_only_when_origin_day_listed(self):
        # rule days=[0] (Mon)，Mon 00:15 為 Sun 延伸 → 起算日是 Sun → 不該 match
        rule = _rule(days_of_week=[0])
        assert matches_schedule(rule, now_weekday=0, now_date=date(2026, 3, 16), now_time_str="00:15") is False

    def test_post_midnight_tail_matches_when_tail_day_origin_listed(self):
        # rule days=[6] (Sun)，Mon 00:15 為 Sun 延伸 → 起算日 Sun ∈ [6] → match
        rule = _rule(days_of_week=[6])
        assert matches_schedule(rule, now_weekday=0, now_date=date(2026, 3, 16), now_time_str="00:15") is True

    def test_normal_window_unaffected(self):
        # 非跨午夜時段不應觸發調整
        rule = _rule(days_of_week=[0], start_time="09:00", end_time="17:00")
        assert matches_schedule(rule, now_weekday=0, now_date=date(2026, 3, 16), now_time_str="12:00") is True
        assert matches_schedule(rule, now_weekday=1, now_date=date(2026, 3, 17), now_time_str="12:00") is False


class TestOnceCrossMidnight:
    """ONCE × 跨午夜：午夜後尾段必須仍 match 起算日的日期範圍。"""

    def test_pre_midnight_within_range(self):
        rule = _rule(
            schedule_type=ScheduleType.ONCE,
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 15),
        )
        assert matches_schedule(rule, now_weekday=6, now_date=date(2026, 3, 15), now_time_str="23:45") is True

    def test_post_midnight_tail_belongs_to_previous_day(self):
        # rule 只允許 2026-03-15，現在是 03-16 00:15 跨午夜尾段 → 起算 03-15 → 應 match
        rule = _rule(
            schedule_type=ScheduleType.ONCE,
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 15),
        )
        assert matches_schedule(rule, now_weekday=0, now_date=date(2026, 3, 16), now_time_str="00:15") is True

    def test_post_midnight_tail_out_of_range_still_rejected(self):
        # rule 允許 2026-03-15，但現在是 03-17 00:15 → 起算 03-16 → 仍超出
        rule = _rule(
            schedule_type=ScheduleType.ONCE,
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 15),
        )
        assert matches_schedule(rule, now_weekday=1, now_date=date(2026, 3, 17), now_time_str="00:15") is False

    def test_post_midnight_tail_before_start_date(self):
        # rule 從 2026-03-15 起，現在 03-15 00:15 → 起算 03-14 → 早於 start_date → 不該 match
        rule = _rule(
            schedule_type=ScheduleType.ONCE,
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 20),
        )
        assert matches_schedule(rule, now_weekday=6, now_date=date(2026, 3, 15), now_time_str="00:15") is False


class TestBackwardCompatibility:
    """now_time_str 為可選參數：未提供時保持舊行為（不調整 weekday/date）。"""

    def test_weekly_without_now_time_str_keeps_old_behavior(self):
        rule = _rule(days_of_week=[6])
        # 不傳 now_time_str → 退化為舊邏輯（依當下 weekday 比對）
        assert matches_schedule(rule, now_weekday=6, now_date=date(2026, 3, 15)) is True
        assert matches_schedule(rule, now_weekday=0, now_date=date(2026, 3, 16)) is False

    def test_daily_always_matches_regardless(self):
        rule = _rule(schedule_type=ScheduleType.DAILY, start_time="23:30", end_time="00:30")
        assert matches_schedule(rule, now_weekday=0, now_date=date(2026, 3, 16), now_time_str="00:15") is True
        assert matches_schedule(rule, now_weekday=6, now_date=date(2026, 3, 15), now_time_str="23:45") is True


@pytest.mark.asyncio
async def test_in_memory_repo_weekly_cross_midnight_tail():
    """整合層回歸：InMemoryScheduleRepository.find_active_rules 必須 fire 整段。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from csp_lib.manager.schedule.in_memory import InMemoryScheduleRepository

    repo = InMemoryScheduleRepository()
    rule = ScheduleRule(
        name="weekly_cross",
        site_id="site_001",
        schedule_type=ScheduleType.WEEKLY,
        strategy_type=StrategyType.PQ,
        start_time="23:30",
        end_time="00:30",
        days_of_week=[6],  # Sunday
    )
    await repo.upsert(rule)

    tz = ZoneInfo("UTC")
    # Sun 2026-03-15 23:45
    pre = datetime(2026, 3, 15, 23, 45, tzinfo=tz)
    assert len(await repo.find_active_rules("site_001", pre)) == 1

    # Mon 2026-03-16 00:15 (跨午夜尾段 — 修補前漏 fire)
    tail = datetime(2026, 3, 16, 0, 15, tzinfo=tz)
    assert len(await repo.find_active_rules("site_001", tail)) == 1

    # Mon 12:00 — 完全不在 window 內，不該 match
    noon = datetime(2026, 3, 16, 12, 0, tzinfo=tz)
    assert len(await repo.find_active_rules("site_001", noon)) == 0
