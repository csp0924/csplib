# =============== TransportAdapter Protocol ===============
#
# 傳輸抽象協定
#
# 統一 Redis / gRPC / HTTP 等傳輸層介面：
#   - TransportAdapter: 傳輸抽象協定
#   - DispatchCommand: 調度命令資料結構
#
# 放置於 Layer 6 (Integration)，具體實作由 Layer 7 (Redis) / Layer 8 (gRPC) 提供。

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from csp_lib.controller.core import NO_CHANGE, Command, NoChange, is_no_change


class DispatchPriority(IntEnum):
    """
    調度命令優先序

    對應 ModePriority 層級，用於區分命令來源與緊急程度。
    """

    NORMAL = 10
    SCHEDULE = 20
    MANUAL = 50
    PROTECTION = 100


@dataclass(frozen=True, slots=True)
class DispatchCommand:
    """
    調度命令

    上層控制器下發給子執行器的命令封包。
    包含來源追溯、目標定位、命令本體與時間戳。

    Attributes:
        source_site_id: 發送方站點 ID（用於審計追溯）
        target_site_id: 目標子執行器站點 ID
        command: 功率控制命令
        priority: 命令優先序
        timestamp: 命令建立時間 (UTC)
        metadata: 額外資訊（如 correlation_id、parent_context 等）
    """

    source_site_id: str
    target_site_id: str
    command: Command
    priority: DispatchPriority = DispatchPriority.NORMAL
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化為字典

        v0.8.0：``NO_CHANGE`` sentinel 以 JSON ``null`` 表示，方便跨語言互通；
        反序列化時（``from_dict``）``None`` 會還原為 ``NO_CHANGE``。
        """
        return {
            "source_site_id": self.source_site_id,
            "target_site_id": self.target_site_id,
            "command": {
                "p_target": None if is_no_change(self.command.p_target) else self.command.p_target,
                "q_target": None if is_no_change(self.command.q_target) else self.command.q_target,
            },
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DispatchCommand:
        """從字典反序列化

        v0.8.0：``p_target`` / ``q_target`` 為 ``None`` 時還原為 ``NO_CHANGE``
        sentinel，對應 ``to_dict`` 的 null 編碼。
        """
        cmd_data = data.get("command", {})
        p_raw = cmd_data.get("p_target", 0.0)
        q_raw = cmd_data.get("q_target", 0.0)
        p_target: float | NoChange = NO_CHANGE if p_raw is None else float(p_raw)
        q_target: float | NoChange = NO_CHANGE if q_raw is None else float(q_raw)
        return cls(
            source_site_id=data["source_site_id"],
            target_site_id=data["target_site_id"],
            command=Command(p_target=p_target, q_target=q_target),
            priority=DispatchPriority(data.get("priority", DispatchPriority.NORMAL)),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
        )


@runtime_checkable
class TransportAdapter(Protocol):
    """
    傳輸抽象協定

    提供 command dispatch 與 state subscription 的統一介面，
    使上層編排邏輯不依賴具體傳輸技術（Redis / gRPC / HTTP）。

    設計原則：
    - 下行：publish_command() 將調度命令推送至目標站點
    - 上行：subscribe_status() 訂閱子站點狀態更新
    - 生命週期：connect() / disconnect() 管理連線

    Usage::

        adapter: TransportAdapter = RedisTransportAdapter(redis_client, ...)
        await adapter.connect()

        # 下發命令
        cmd = DispatchCommand(...)
        await adapter.publish_command(cmd)

        # 訂閱狀態
        await adapter.subscribe_status(on_status_callback)

        await adapter.disconnect()
    """

    async def connect(self) -> None:
        """建立傳輸連線"""
        ...

    async def disconnect(self) -> None:
        """斷開傳輸連線"""
        ...

    async def publish_command(self, command: DispatchCommand) -> None:
        """
        發送調度命令至目標站點

        Args:
            command: 調度命令
        """
        ...

    async def subscribe_status(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """
        訂閱子站點狀態更新

        Args:
            callback: 收到狀態更新時的回呼函式，參數為狀態字典
        """
        ...

    async def health_check(self) -> bool:
        """
        傳輸層健康檢查

        Returns:
            True 表示傳輸層可用
        """
        ...


__all__ = [
    "DispatchCommand",
    "DispatchPriority",
    "TransportAdapter",
]
