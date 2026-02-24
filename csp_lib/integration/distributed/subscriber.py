# =============== Integration Distributed - Subscriber ===============
#
# 設備狀態訂閱器
#
# 從 Redis 輪詢遠端設備的狀態、連線狀態與告警：
#   - DeviceStateSubscriber: 分散式設備狀態輪詢器

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from csp_lib.core import AsyncLifecycleMixin, get_logger

if TYPE_CHECKING:
    from csp_lib.redis import RedisClient

    from .config import DistributedConfig

logger = get_logger("csp_lib.integration.distributed.subscriber")


class DeviceStateSubscriber(AsyncLifecycleMixin):
    """
    設備狀態訂閱器

    從 Redis 輪詢遠端站台設備的狀態，提供與 ClusterStateSubscriber
    相同的 device_states 介面，供 VirtualContextBuilder 使用。

    Redis Key 結構（由遠端 StateSyncManager 發佈）：
        - device:{device_id}:state - Hash，所有點位最新值
        - device:{device_id}:online - String，"1" 或 "0"
        - device:{device_id}:alarms - Set，活躍告警 codes

    Usage::

        subscriber = DeviceStateSubscriber(config, redis_client)
        async with subscriber:
            states = subscriber.device_states
            online = subscriber.device_online
    """

    def __init__(
        self,
        config: DistributedConfig,
        redis_client: RedisClient,
    ) -> None:
        self._config = config
        self._redis = redis_client
        self._device_states: dict[str, dict[str, Any]] = {}
        self._device_online: dict[str, bool] = {}
        self._device_alarms: dict[str, set[str]] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def device_states(self) -> dict[str, dict[str, Any]]:
        """設備狀態快取（device_id -> latest_values dict）"""
        return self._device_states

    @property
    def device_online(self) -> dict[str, bool]:
        """設備連線狀態（device_id -> is_online）"""
        return self._device_online

    @property
    def device_alarms(self) -> dict[str, set[str]]:
        """設備活躍告警（device_id -> alarm codes）"""
        return self._device_alarms

    async def _on_start(self) -> None:
        """啟動輪詢迴圈"""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("DeviceStateSubscriber started.")

    async def _on_stop(self) -> None:
        """停止輪詢"""
        self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("DeviceStateSubscriber stopped.")

    async def _poll_loop(self) -> None:
        """輪詢主迴圈"""
        interval = self._config.poll_interval
        while not self._stop_event.is_set():
            try:
                await self._poll_all()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Failed to poll device states")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                pass

    async def _poll_all(self) -> None:
        """讀取所有設備狀態"""
        for device_id in self._config.all_device_ids:
            # State (HGETALL)
            try:
                state = await self._redis.hgetall(f"device:{device_id}:state")
                if state:
                    self._device_states[device_id] = state
                else:
                    self._device_states.pop(device_id, None)
            except Exception:
                logger.debug(f"Failed to read state for device {device_id}")

            # Online (GET)
            try:
                online_raw = await self._redis.get(f"device:{device_id}:online")
                self._device_online[device_id] = online_raw == "1"
            except Exception:
                logger.debug(f"Failed to read online status for device {device_id}")
                self._device_online[device_id] = False

            # Alarms (SMEMBERS)
            try:
                alarms = await self._redis.smembers(f"device:{device_id}:alarms")
                self._device_alarms[device_id] = alarms
            except Exception:
                logger.debug(f"Failed to read alarms for device {device_id}")
                self._device_alarms[device_id] = set()


__all__ = [
    "DeviceStateSubscriber",
]
