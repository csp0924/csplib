# =============== Manager Schedule - Matcher ===============
#
# 排程時間匹配邏輯
#
# 從 MongoScheduleRepository 提取的純函式，供所有 Repository 實作共用：
#   - matches_time: 檢查當前時間是否在排程時段內（支援跨午夜）
#   - matches_schedule: 檢查排程類型條件是否匹配

from __future__ import annotations

from datetime import date

from .schema import ScheduleRule, ScheduleType


def matches_time(rule: ScheduleRule, now_time_str: str) -> bool:
    """檢查時間是否匹配

    支援跨午夜：若 start_time > end_time（如 22:00-06:00），
    匹配 now >= start_time OR now <= end_time。

    Args:
        rule: 排程規則
        now_time_str: 當前時間（"HH:MM" 格式）

    Returns:
        是否匹配
    """
    start = rule.start_time
    end = rule.end_time

    if start <= end:
        # 正常時段：start <= now <= end
        return start <= now_time_str <= end
    else:
        # 跨午夜：22:00-06:00 → now >= 22:00 OR now <= 06:00
        return now_time_str >= start or now_time_str <= end


def matches_schedule(rule: ScheduleRule, now_weekday: int, now_date: date) -> bool:
    """檢查排程類型條件是否匹配

    Args:
        rule: 排程規則
        now_weekday: 當前星期幾（0=Mon..6=Sun）
        now_date: 當前日期

    Returns:
        是否匹配
    """
    if rule.schedule_type == ScheduleType.DAILY:
        return True
    elif rule.schedule_type == ScheduleType.WEEKLY:
        return now_weekday in rule.days_of_week
    elif rule.schedule_type == ScheduleType.ONCE:
        if rule.start_date and now_date < rule.start_date:
            return False
        if rule.end_date and now_date > rule.end_date:
            return False
        return True
    return False


__all__ = [
    "matches_schedule",
    "matches_time",
]
