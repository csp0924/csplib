# =============== Integration Distributed - Command Router ===============
#
# 遠端指令路由器
#
# 將 Command 透過 Redis Pub/Sub 發送到遠端站台：
#   - RemoteCommandRouter: CommandRouter 的分散式替代方案

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger
from csp_lib.integration.schema import CommandMapping

if TYPE_CHECKING:
    from csp_lib.controller.core import Command
    from csp_lib.redis import RedisClient

    from .config import DistributedConfig
    from .subscriber import DeviceStateSubscriber

logger = get_logger("csp_lib.integration.distributed.command_router")


class RemoteCommandRouter:
    """
    遠端指令路由器

    與 CommandRouter 相同的 ``async route(Command) -> None`` 簽名，
    但透過 Redis Pub/Sub 將指令發送到遠端站台，而非直接寫入設備。

    發布格式：``{"device_id": "X", "point_name": "Y", "value": Z}``
    與 RedisCommandAdapter 預期的格式相同。

    Usage::

        router = RemoteCommandRouter(
            config=distributed_config,
            redis_client=redis,
            subscriber=subscriber,
            mappings=command_mappings,
        )
        await router.route(command)
    """

    def __init__(
        self,
        config: DistributedConfig,
        redis_client: RedisClient,
        subscriber: DeviceStateSubscriber,
        mappings: list[CommandMapping],
    ) -> None:
        self._config = config
        self._redis = redis_client
        self._subscriber = subscriber
        self._mappings = mappings
        self._device_site_map = config.device_site_map

    async def route(self, command: Command) -> None:
        """
        路由 Command 到遠端站台

        遍歷所有 CommandMapping，取得 Command 對應欄位值後
        透過 Redis 發送到對應站台的指令 channel。

        Args:
            command: 策略執行輸出的命令
        """
        for mapping in self._mappings:
            value = getattr(command, mapping.command_field, None)
            if value is None:
                continue

            if mapping.transform is not None:
                try:
                    value = mapping.transform(value)
                except Exception:
                    logger.error(f"Transform failed for command field '{mapping.command_field}', skipping.")
                    continue

            if mapping.device_id is not None:
                await self._publish_single(mapping.device_id, mapping.point_name, value)
            elif mapping.trait is not None:
                await self._publish_trait_broadcast(mapping.trait, mapping.point_name, value)

    async def _publish_single(self, device_id: str, point_name: str, value: Any) -> None:
        """device_id 模式：發送指令到單一設備"""
        if not self._is_device_available(device_id):
            return

        site = self._device_site_map.get(device_id)
        if site is None:
            logger.warning(f"Device '{device_id}' not found in any site, skipping.")
            return

        await self._publish_command(site.effective_command_channel, device_id, point_name, value)

    async def _publish_trait_broadcast(self, trait: str, point_name: str, value: Any) -> None:
        """trait 模式：廣播指令到所有匹配設備"""
        device_ids = self._config.trait_device_map.get(trait, [])
        if not device_ids:
            logger.warning(f"No devices found for trait '{trait}'.")
            return

        for device_id in device_ids:
            if not self._is_device_available(device_id):
                continue

            site = self._device_site_map.get(device_id)
            if site is None:
                continue

            await self._publish_command(site.effective_command_channel, device_id, point_name, value)

    def _is_device_available(self, device_id: str) -> bool:
        """檢查設備是否可用（在線且無告警）"""
        if not self._subscriber.device_online.get(device_id, False):
            logger.warning(f"Device '{device_id}' is offline, skipping command.")
            return False

        alarms = self._subscriber.device_alarms.get(device_id, set())
        if alarms:
            logger.warning(f"Device '{device_id}' has active alarms {alarms}, skipping command.")
            return False

        return True

    async def _publish_command(self, channel: str, device_id: str, point_name: str, value: Any) -> None:
        """發布指令到 Redis channel"""
        payload = json.dumps({
            "device_id": device_id,
            "point_name": point_name,
            "value": value,
        })
        try:
            await self._redis.publish(channel, payload)
            logger.debug(f"Published command: {device_id}.{point_name} = {value} -> {channel}")
        except Exception:
            logger.exception(f"Failed to publish command to {channel}")


__all__ = [
    "RemoteCommandRouter",
]
