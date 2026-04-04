# =============== Manager Schedule - In-Memory Repository ===============
#
# 記憶體內排程規則資料存取層
#
# 提供不依賴 MongoDB 的 ScheduleRepository 實作：
#   - InMemoryScheduleRepository: 記憶體內實作（供測試與開發使用）

from __future__ import annotations

import threading
from datetime import datetime

from csp_lib.core import get_logger

from . import matcher
from .schema import ScheduleRule

logger = get_logger(__name__)


class InMemoryScheduleRepository:
    """
    記憶體內排程 Repository 實作

    實作 ScheduleRepository Protocol，將排程規則儲存在記憶體中。
    使用 (site_id, name) 作為唯一鍵。

    Attributes:
        _lock: 執行緒安全鎖
        _rules: (site_id, name) → ScheduleRule 的映射
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rules: dict[tuple[str, str], ScheduleRule] = {}

    async def health_check(self) -> bool:
        """檢查健康狀態

        Returns:
            永遠回傳 True
        """
        return True

    async def find_active_rules(self, site_id: str, now: datetime) -> list[ScheduleRule]:
        """查詢當前時間匹配的啟用規則

        先取得所有啟用的規則，再過濾時間/星期/日期條件，
        最後依 priority DESC 排序。

        Args:
            site_id: 站點識別碼
            now: 當前時間（含時區）

        Returns:
            匹配的規則列表（priority DESC）
        """
        all_enabled = await self.get_all_enabled(site_id)

        now_time = now.strftime("%H:%M")
        now_weekday = now.weekday()
        now_date = now.date()

        matched: list[ScheduleRule] = []
        for rule in all_enabled:
            if not matcher.matches_time(rule, now_time):
                continue
            if not matcher.matches_schedule(rule, now_weekday, now_date):
                continue
            matched.append(rule)

        matched.sort(key=lambda r: r.priority, reverse=True)
        return matched

    async def get_all_enabled(self, site_id: str) -> list[ScheduleRule]:
        """取得指定站點所有啟用的規則

        Args:
            site_id: 站點識別碼

        Returns:
            啟用的規則列表
        """
        with self._lock:
            return [r for key, r in self._rules.items() if key[0] == site_id and r.enabled]

    async def upsert(self, rule: ScheduleRule) -> str:
        """新增或更新排程規則

        使用 (site_id, name) 作為唯一鍵。

        Args:
            rule: 排程規則

        Returns:
            規則名稱
        """
        with self._lock:
            self._rules[(rule.site_id, rule.name)] = rule
        return rule.name

    # === 測試輔助方法 ===

    def get_all_rules(self) -> dict[tuple[str, str], ScheduleRule]:
        """取得所有排程規則

        Returns:
            (site_id, name) → ScheduleRule 的映射副本
        """
        with self._lock:
            return dict(self._rules)

    def clear(self) -> None:
        """清除所有規則"""
        with self._lock:
            self._rules.clear()


__all__ = [
    "InMemoryScheduleRepository",
]
