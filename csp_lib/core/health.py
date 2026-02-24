# =============== Core - Health ===============
#
# 健康檢查介面
#
# 提供統一的健康狀態報告：
#   - HealthStatus: 健康狀態枚舉
#   - HealthReport: 健康報告資料
#   - HealthCheckable: 健康檢查協定

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class HealthStatus(Enum):
    """健康狀態"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class HealthReport:
    """健康報告"""

    status: HealthStatus
    component: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    children: list[HealthReport] = field(default_factory=list)


@runtime_checkable
class HealthCheckable(Protocol):
    """健康檢查協定"""

    def health(self) -> HealthReport: ...


__all__ = [
    "HealthStatus",
    "HealthReport",
    "HealthCheckable",
]
