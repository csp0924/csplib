# =============== Monitor - Distributed ===============
#
# 分散式監控聚合
#
# 提供多節點監控聚合功能：
#   - NodeRegistration: 節點註冊資料
#   - NodeMetricsSummary: 節點指標摘要
#   - ClusterHealthSnapshot: 叢集健康快照
#   - ClusterMonitorAggregator: 叢集監控聚合器

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from csp_lib.core import AsyncLifecycleMixin, HealthReport, HealthStatus, get_logger

if TYPE_CHECKING:
    from csp_lib.monitor.config import DistributedMonitorConfig, MonitorConfig
    from csp_lib.redis import RedisClient

logger = get_logger(__name__)


@dataclass(frozen=True)
class NodeRegistration:
    """
    節點註冊資料

    Attributes:
        instance_id: 節點 ID
        hostname: 主機名稱
        started_at: 啟動時間
        last_seen: 最後活動時間
    """

    instance_id: str
    hostname: str
    started_at: str
    last_seen: str

    def to_dict(self) -> dict[str, Any]:
        """轉換為字典"""
        return {
            "instance_id": self.instance_id,
            "hostname": self.hostname,
            "started_at": self.started_at,
            "last_seen": self.last_seen,
        }


@dataclass(frozen=True)
class NodeMetricsSummary:
    """
    節點指標摘要

    Attributes:
        instance_id: 節點 ID
        metrics: 指標字典
        active_alarms: 活躍告警代碼
        is_online: 是否在線
        updated_at: 更新時間
    """

    instance_id: str
    metrics: dict[str, Any] = field(default_factory=dict)
    active_alarms: list[str] = field(default_factory=list)
    is_online: bool = True
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """轉換為字典"""
        return {
            "instance_id": self.instance_id,
            "metrics": self.metrics,
            "active_alarms": self.active_alarms,
            "is_online": self.is_online,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ClusterHealthSnapshot:
    """
    叢集健康快照

    Attributes:
        nodes: 節點指標摘要列表
        overall_status: 整體健康狀態
        node_count: 節點總數
        online_count: 在線節點數
        unhealthy_nodes: 不健康節點 ID 列表
    """

    nodes: list[NodeMetricsSummary]
    overall_status: HealthStatus
    node_count: int
    online_count: int
    unhealthy_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """轉換為字典"""
        return {
            "overall_status": self.overall_status.value,
            "node_count": self.node_count,
            "online_count": self.online_count,
            "unhealthy_nodes": self.unhealthy_nodes,
            "nodes": {n.instance_id: n.to_dict() for n in self.nodes},
        }


class ClusterMonitorAggregator(AsyncLifecycleMixin):
    """
    叢集監控聚合器

    定期探索已註冊節點，收集各節點指標與告警，
    產生叢集級健康快照並可選發布至 Redis。
    """

    def __init__(
        self,
        redis_client: RedisClient,
        config: DistributedMonitorConfig,
        monitor_config: MonitorConfig | None = None,
    ) -> None:
        self._redis = redis_client
        self._config = config
        self._monitor_config = monitor_config
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_snapshot: ClusterHealthSnapshot | None = None
        self._known_nodes: dict[str, NodeRegistration] = {}

    # ================ Lifecycle ================

    async def _on_start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("叢集監控聚合器已啟動")

    async def _on_stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("叢集監控聚合器已停止")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._aggregate()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("叢集聚合迴圈異常", exc_info=True)

            try:
                await asyncio.sleep(self._config.aggregation_interval)
            except asyncio.CancelledError:
                raise

    # ================ Core Logic ================

    async def _aggregate(self) -> None:
        """執行一次聚合"""
        nodes = await self._discover_nodes()
        self._known_nodes = {n.instance_id: n for n in nodes}

        summaries: list[NodeMetricsSummary] = []
        for node in nodes:
            summary = await self._collect_node_summary(node.instance_id)
            summaries.append(summary)

        snapshot = self._compute_cluster_health(summaries)
        self._last_snapshot = snapshot

        if self._config.publish_cluster_health:
            await self._publish_cluster_health(snapshot)

    async def _discover_nodes(self) -> list[NodeRegistration]:
        """探索已註冊節點"""
        pattern = self._config.node_pattern()
        keys = await self._redis.keys(pattern)

        nodes: list[NodeRegistration] = []
        for key in keys:
            try:
                raw = await self._redis.get(key)
                if raw:
                    data = json.loads(raw)
                    nodes.append(
                        NodeRegistration(
                            instance_id=data["instance_id"],
                            hostname=data["hostname"],
                            started_at=data["started_at"],
                            last_seen=data["last_seen"],
                        )
                    )
            except Exception:
                logger.warning(f"讀取節點註冊失敗: {key}", exc_info=True)

        return nodes

    async def _collect_node_summary(self, instance_id: str) -> NodeMetricsSummary:
        """收集單一節點指標摘要"""
        prefix = self._config.metrics_prefix(instance_id)
        metrics_key = f"{prefix}:metrics"
        alarms_key = f"{prefix}:alarms"

        metrics: dict[str, Any] = {}
        active_alarms: list[str] = []
        updated_at = ""

        try:
            raw_metrics = await self._redis.hgetall(metrics_key)
            if raw_metrics:
                updated_at = raw_metrics.pop("updated_at", "")
                metrics = raw_metrics
        except Exception:
            logger.warning(f"讀取節點指標失敗: {instance_id}", exc_info=True)

        try:
            alarm_set = await self._redis.smembers(alarms_key)
            active_alarms = sorted(alarm_set)
        except Exception:
            logger.warning(f"讀取節點告警失敗: {instance_id}", exc_info=True)

        # 判斷是否在線：節點是否仍在 known_nodes 中（TTL 存活代表在線）
        is_online = instance_id in self._known_nodes

        return NodeMetricsSummary(
            instance_id=instance_id,
            metrics=metrics,
            active_alarms=active_alarms,
            is_online=is_online,
            updated_at=updated_at,
        )

    @staticmethod
    def _compute_cluster_health(summaries: list[NodeMetricsSummary]) -> ClusterHealthSnapshot:
        """計算叢集健康狀態"""
        online_count = sum(1 for s in summaries if s.is_online)
        unhealthy: list[str] = []

        for s in summaries:
            if not s.is_online:
                unhealthy.append(s.instance_id)
            elif s.active_alarms:
                unhealthy.append(s.instance_id)

        if any(not s.is_online for s in summaries):
            overall = HealthStatus.UNHEALTHY
        elif unhealthy:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return ClusterHealthSnapshot(
            nodes=summaries,
            overall_status=overall,
            node_count=len(summaries),
            online_count=online_count,
            unhealthy_nodes=unhealthy,
        )

    async def _publish_cluster_health(self, snapshot: ClusterHealthSnapshot) -> None:
        """發布叢集健康至 Redis"""
        key = self._config.cluster_health_key()
        data = snapshot.to_dict()
        now = datetime.now(timezone.utc).isoformat()

        flat: dict[str, str] = {}
        flat["overall_status"] = data["overall_status"]
        flat["node_count"] = str(data["node_count"])
        flat["online_count"] = str(data["online_count"])
        flat["unhealthy_nodes"] = json.dumps(data["unhealthy_nodes"])
        flat["nodes"] = json.dumps(data["nodes"])
        flat["updated_at"] = now

        await self._redis.hset(key, flat)

        ttl = self._monitor_config.metrics_ttl if self._monitor_config else 60
        await self._redis.expire(key, ttl)

    # ================ HealthCheckable ================

    def health(self) -> HealthReport:
        """回報聚合器自身健康狀態"""
        if not self._running:
            return HealthReport(
                status=HealthStatus.UNHEALTHY,
                component="ClusterMonitorAggregator",
                message="聚合器未運行",
            )

        if self._last_snapshot and self._last_snapshot.unhealthy_nodes:
            return HealthReport(
                status=HealthStatus.DEGRADED,
                component="ClusterMonitorAggregator",
                message=f"不健康節點: {', '.join(self._last_snapshot.unhealthy_nodes)}",
                details={"unhealthy_nodes": self._last_snapshot.unhealthy_nodes},
            )

        return HealthReport(
            status=HealthStatus.HEALTHY,
            component="ClusterMonitorAggregator",
            message="正常運行",
        )

    # ================ Properties ================

    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self._running

    @property
    def last_snapshot(self) -> ClusterHealthSnapshot | None:
        """最近一次叢集健康快照"""
        return self._last_snapshot

    @property
    def known_nodes(self) -> dict[str, NodeRegistration]:
        """已知節點"""
        return dict(self._known_nodes)


__all__ = [
    "ClusterHealthSnapshot",
    "ClusterMonitorAggregator",
    "NodeMetricsSummary",
    "NodeRegistration",
]
