# =============== Hierarchical Status Report ===============
#
# 子執行器狀態回報資料結構
#
# 定義子站點向上層回報的狀態資訊：
#   - ExecutorStatus: 子執行器即時狀態
#   - StatusReport: 帶時間戳與站點標識的狀態封包

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from csp_lib.controller.core import Command


@dataclass(frozen=True, slots=True)
class ExecutorStatus:
    """
    子執行器即時狀態

    描述單一站點控制器的當前運作狀態，供上層編排器決策。

    Attributes:
        strategy_name: 當前生效策略名稱（如 "pq", "cascading(pq+qv)"）
        last_command: 最近一次執行的命令
        active_overrides: 當前啟用的覆蓋模式列表
        base_modes: 當前設定的基礎模式列表
        is_running: 控制器是否正在運行
        device_count: 管理的設備數量
        healthy_device_count: 健康設備數量
    """

    strategy_name: str = ""
    last_command: Command = field(default_factory=Command)
    active_overrides: tuple[str, ...] = ()
    base_modes: tuple[str, ...] = ()
    is_running: bool = False
    device_count: int = 0
    healthy_device_count: int = 0


@dataclass(frozen=True, slots=True)
class StatusReport:
    """
    狀態回報封包

    子站點向上層控制器回報的完整狀態資訊，
    包含站點標識、時間戳、執行器狀態與額外指標。

    Attributes:
        site_id: 回報站點 ID
        status: 執行器即時狀態
        timestamp: 回報時間 (UTC)
        metrics: 額外指標（如 SOC、電壓、頻率等）
    """

    site_id: str
    status: ExecutorStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化為字典"""
        return {
            "site_id": self.site_id,
            "status": {
                "strategy_name": self.status.strategy_name,
                "last_command": {
                    "p_target": self.status.last_command.p_target,
                    "q_target": self.status.last_command.q_target,
                    "is_fallback": self.status.last_command.is_fallback,
                },
                "active_overrides": list(self.status.active_overrides),
                "base_modes": list(self.status.base_modes),
                "is_running": self.status.is_running,
                "device_count": self.status.device_count,
                "healthy_device_count": self.status.healthy_device_count,
            },
            "timestamp": self.timestamp.isoformat(),
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusReport:
        """從字典反序列化"""
        status_data = data.get("status", {})
        cmd_data = status_data.get("last_command", {})
        return cls(
            site_id=data["site_id"],
            status=ExecutorStatus(
                strategy_name=status_data.get("strategy_name", ""),
                last_command=Command(
                    p_target=float(cmd_data.get("p_target", 0.0)),
                    q_target=float(cmd_data.get("q_target", 0.0)),
                    is_fallback=bool(cmd_data.get("is_fallback", False)),
                ),
                active_overrides=tuple(status_data.get("active_overrides", [])),
                base_modes=tuple(status_data.get("base_modes", [])),
                is_running=status_data.get("is_running", False),
                device_count=status_data.get("device_count", 0),
                healthy_device_count=status_data.get("healthy_device_count", 0),
            ),
            timestamp=(
                datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc)
            ),
            metrics=data.get("metrics", {}),
        )


__all__ = [
    "ExecutorStatus",
    "StatusReport",
]
