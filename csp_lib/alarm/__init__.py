# =============== Alarm Module ===============
#
# In-process 告警聚合與 Redis pub/sub 橋接。
#
# Public API:
#   - AlarmAggregator: 多來源告警聚合器（OR 語義，同步 on_change callback）
#   - WatchdogProtocol: Watchdog 結構化協定
#   - AlarmChangeCallback: on_change callback 型別別名
#   - RedisAlarmPublisher / RedisAlarmSource: Redis pub/sub 橋接
#     （需 ``csp_lib[redis]`` extra，採 lazy import）

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .aggregator import AlarmAggregator
from .protocols import AlarmChangeCallback, WatchdogProtocol

if TYPE_CHECKING:
    from .redis_adapter import RedisAlarmPublisher, RedisAlarmSource

__all__ = [
    "AlarmAggregator",
    "AlarmChangeCallback",
    "RedisAlarmPublisher",
    "RedisAlarmSource",
    "WatchdogProtocol",
]


def __getattr__(name: str) -> Any:
    """Lazy import Redis adapter（需 optional extra）。"""
    if name in ("RedisAlarmPublisher", "RedisAlarmSource"):
        from .redis_adapter import RedisAlarmPublisher, RedisAlarmSource

        return {"RedisAlarmPublisher": RedisAlarmPublisher, "RedisAlarmSource": RedisAlarmSource}[name]
    raise AttributeError(f"module 'csp_lib.alarm' has no attribute {name!r}")
