# =============== Monitor - Publisher ===============
#
# Redis 監控資料發布器
#
# 將系統指標、模組健康、告警事件發布至 Redis：
#   - RedisMonitorPublisher: Redis 發布器

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from csp_lib.core import get_logger
from csp_lib.equipment.alarm.state import AlarmEvent, AlarmEventType

if TYPE_CHECKING:
    from csp_lib.monitor.collector import ModuleHealthSnapshot, SystemMetrics
    from csp_lib.monitor.config import DistributedMonitorConfig, MonitorConfig
    from csp_lib.redis import RedisClient

logger = get_logger(__name__)


class RedisMonitorPublisher:
    """
    Redis 監控資料發布器

    發布系統指標、模組健康、告警事件至 Redis Hash + Pub/Sub。

    Redis Key 結構：
        - {prefix}:metrics  — Hash，最新系統指標（有 TTL）
        - {prefix}:modules  — Hash，最新模組健康（有 TTL）
        - {prefix}:alarms   — Set，活躍系統告警代碼（無 TTL）

    Pub/Sub Channel：
        - channel:{prefix}:metrics — 即時指標串流
        - channel:{prefix}:modules — 即時模組健康串流
        - channel:{prefix}:alarm   — 告警觸發/解除事件
    """

    def __init__(
        self,
        redis_client: RedisClient,
        config: MonitorConfig,
        distributed_config: DistributedMonitorConfig | None = None,
    ) -> None:
        self._redis = redis_client
        self._config = config
        self._prefix = config.redis_key_prefix
        self._distributed_config = distributed_config

    # ================ Key / Channel 命名 ================

    @property
    def _metrics_key(self) -> str:
        return f"{self._prefix}:metrics"

    @property
    def _modules_key(self) -> str:
        return f"{self._prefix}:modules"

    @property
    def _alarms_key(self) -> str:
        return f"{self._prefix}:alarms"

    @property
    def _metrics_channel(self) -> str:
        return f"channel:{self._prefix}:metrics"

    @property
    def _modules_channel(self) -> str:
        return f"channel:{self._prefix}:modules"

    @property
    def _alarm_channel(self) -> str:
        return f"channel:{self._prefix}:alarm"

    # ================ 節點註冊（分散式模式） ================

    async def register_node(self) -> None:
        """註冊節點（分散式模式）"""
        if not self._distributed_config:
            return

        import platform

        dc = self._distributed_config
        now = datetime.now(timezone.utc).isoformat()
        registration = json.dumps(
            {
                "instance_id": dc.instance_id,
                "hostname": platform.node(),
                "started_at": now,
                "last_seen": now,
            }
        )
        await self._redis.set(dc.node_key(dc.instance_id), registration, ex=dc.node_ttl)
        logger.info(f"節點已註冊: {dc.instance_id}")

    async def refresh_node_registration(self) -> None:
        """刷新節點註冊 TTL（分散式模式心跳）"""
        if not self._distributed_config:
            return

        dc = self._distributed_config
        key = dc.node_key(dc.instance_id)
        existing = await self._redis.get(key)
        if existing:
            data = json.loads(existing)
            data["last_seen"] = datetime.now(timezone.utc).isoformat()
            await self._redis.set(key, json.dumps(data), ex=dc.node_ttl)

    # ================ 發布方法 ================

    async def publish_metrics(self, metrics: SystemMetrics) -> None:
        """發布系統指標至 Redis Hash + Pub/Sub"""
        data = metrics.to_dict()
        now = datetime.now(timezone.utc).isoformat()

        # Hash + TTL
        flat: dict[str, str] = {}
        for k, v in data.items():
            flat[k] = json.dumps(v) if not isinstance(v, str) else v
        flat["updated_at"] = now

        await self._redis.hset(self._metrics_key, flat)
        await self._redis.expire(self._metrics_key, self._config.metrics_ttl)

        # Per-interface network data
        if metrics.interface_metrics:
            iface_data: dict[str, str] = {}
            for iface_name, iface_m in metrics.interface_metrics.items():
                iface_data[iface_name] = json.dumps(iface_m.to_dict())
            network_key = f"{self._prefix}:network"
            await self._redis.hset(network_key, iface_data)
            await self._redis.expire(network_key, self._config.metrics_ttl)

        # Pub/Sub
        message = json.dumps({"timestamp": now, **data}, default=str)
        await self._redis.publish(self._metrics_channel, message)

        # Distributed dual-publish
        if self._distributed_config:
            dc = self._distributed_config
            dist_metrics_key = f"{dc.metrics_prefix(dc.instance_id)}:metrics"
            await self._redis.hset(dist_metrics_key, flat)
            await self._redis.expire(dist_metrics_key, self._config.metrics_ttl)
            await self.refresh_node_registration()

    async def publish_module_health(self, snapshot: ModuleHealthSnapshot) -> None:
        """發布模組健康至 Redis Hash + Pub/Sub"""
        data = snapshot.to_dict()
        now = datetime.now(timezone.utc).isoformat()

        flat: dict[str, str] = {}
        flat["overall_status"] = data["overall_status"]
        for name, info in data["modules"].items():
            flat[f"module:{name}"] = json.dumps(info)
        flat["updated_at"] = now

        await self._redis.hset(self._modules_key, flat)
        await self._redis.expire(self._modules_key, self._config.metrics_ttl)

        # Pub/Sub
        message = json.dumps({"timestamp": now, **data}, default=str)
        await self._redis.publish(self._modules_channel, message)

    async def publish_alarm_event(self, event: AlarmEvent) -> None:
        """發布告警事件至 Redis Set + Pub/Sub"""
        alarm = event.alarm

        if event.event_type == AlarmEventType.TRIGGERED:
            await self._redis.sadd(self._alarms_key, alarm.code)
        else:
            await self._redis.srem(self._alarms_key, alarm.code)

        message = json.dumps(
            {
                "type": event.event_type.value,
                "alarm": {
                    "code": alarm.code,
                    "name": alarm.name,
                    "level": alarm.level.value,
                    "description": alarm.description,
                },
                "timestamp": event.timestamp.isoformat(),
            }
        )
        await self._redis.publish(self._alarm_channel, message)

        # Distributed dual-publish
        if self._distributed_config:
            dc = self._distributed_config
            dist_alarms_key = f"{dc.metrics_prefix(dc.instance_id)}:alarms"
            if event.event_type == AlarmEventType.TRIGGERED:
                await self._redis.sadd(dist_alarms_key, alarm.code)
            else:
                await self._redis.srem(dist_alarms_key, alarm.code)


__all__ = [
    "RedisMonitorPublisher",
]
