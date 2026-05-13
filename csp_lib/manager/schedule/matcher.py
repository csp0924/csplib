# =============== Manager Schedule - Matcher ===============
#
# 排程時間匹配邏輯
#
# 從 MongoScheduleRepository 提取的純函式，供所有 Repository 實作共用：
#   - matches_time: 檢查當前時間是否在排程時段內（支援跨午夜）
#   - matches_schedule: 檢查排程類型條件是否匹配（支援跨午夜尾段歸屬起算日）

from __future__ import annotations

from datetime import date, timedelta

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


def _is_post_midnight_tail(rule: ScheduleRule, now_time_str: str | None) -> bool:
    """判斷現在是否落在「跨午夜規則的午夜後尾段」。

    僅當 rule 為跨午夜時段（``start_time > end_time``）且當前時間 <= ``end_time``
    才回傳 True；此時尾段在語意上仍屬於前一日（起算日）的排程延伸。

    當 ``now_time_str`` 為 None（呼叫端未提供）時一律回傳 False —— 對應
    舊呼叫慣例保留 backward compat（不調整 weekday/date）。
    """
    if now_time_str is None:
        return False
    return rule.start_time > rule.end_time and now_time_str <= rule.end_time


def matches_schedule(
    rule: ScheduleRule,
    now_weekday: int,
    now_date: date,
    now_time_str: str | None = None,
) -> bool:
    """檢查排程類型條件是否匹配

    跨午夜尾段語意：若 rule 時段跨午夜（``start_time > end_time``）且 ``now_time_str``
    落於午夜後尾段（``<= end_time``），則 ``now_weekday`` / ``now_date`` 在語意上
    應對應「起算日」（前一日），因此在比對 WEEKLY ``days_of_week`` 與 ONCE
    ``start_date`` / ``end_date`` 前會先回推一日。

    Args:
        rule: 排程規則
        now_weekday: 當前星期幾（0=Mon..6=Sun）
        now_date: 當前日期
        now_time_str: 當前時間（"HH:MM"），用於辨識跨午夜尾段；
            若為 ``None`` 則退化為舊行為（不調整 weekday/date），
            僅保留給未升級呼叫端使用。

    Returns:
        是否匹配
    """
    # 跨午夜尾段：回推一日做比對
    if _is_post_midnight_tail(rule, now_time_str):
        now_weekday = (now_weekday - 1) % 7
        now_date = now_date - timedelta(days=1)

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
