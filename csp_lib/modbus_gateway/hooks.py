"""
Built-in WriteHook implementations.

WriteHook 在寫入成功後觸發，用於 Redis 發布、狀態持久化、自訂回呼等。
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.modbus_gateway.register_map import GatewayRegisterMap

logger = get_logger(__name__)


class RedisPublishHook:
    """
    Publishes register write events to a Redis channel.

    Published message format (JSON)::

        {"register": "<name>", "old": <old_value>, "new": <new_value>, "ts": <unix_timestamp>}

    Satisfies WriteHook protocol.

    Args:
        redis_client: redis.asyncio.Redis 或 csp_lib.redis.RedisClient 實例
        channel: Redis channel 名稱
    """

    def __init__(self, redis_client: Any, channel: str = "gateway:writes") -> None:
        self._redis = redis_client
        self._channel = channel

    async def on_write(self, register_name: str, old_value: Any, new_value: Any) -> None:
        payload = json.dumps({
            "register": register_name,
            "old": old_value,
            "new": new_value,
            "ts": time.time(),
        })
        try:
            await self._redis.publish(self._channel, payload)
        except Exception:
            logger.opt(exception=True).warning(f"RedisPublishHook: failed to publish to {self._channel}")


class CallbackHook:
    """
    Invokes a user-provided async callback on write.

    Satisfies WriteHook protocol.

    Args:
        callback: async function(register_name, old_value, new_value) -> None
    """

    def __init__(self, callback: Callable[[str, Any, Any], Awaitable[None]]) -> None:
        self._callback = callback

    async def on_write(self, register_name: str, old_value: Any, new_value: Any) -> None:
        await self._callback(register_name, old_value, new_value)


class StatePersistHook:
    """
    Persists written holding register values to Redis Hash.

    On startup, ModbusGatewayServer can call restore_all() to recover state.

    Redis key: ``gateway:{server_name}:state``
    Hash field: register name, value: JSON-encoded physical value

    Satisfies WriteHook protocol.

    Args:
        redis_client: redis.asyncio.Redis 或 csp_lib.redis.RedisClient 實例
        server_name: 伺服器名稱（用於 Redis key 區隔）
    """

    def __init__(self, redis_client: Any, server_name: str = "default") -> None:
        self._redis = redis_client
        self._key = f"gateway:{server_name}:state"

    @property
    def redis_key(self) -> str:
        """Redis Hash key used for persistence."""
        return self._key

    async def on_write(self, register_name: str, old_value: Any, new_value: Any) -> None:
        try:
            if hasattr(self._redis, "hset"):
                await self._redis.hset(self._key, mapping={register_name: json.dumps(new_value)})
            else:
                await self._redis._client.hset(self._key, register_name, json.dumps(new_value))
        except Exception:
            logger.opt(exception=True).warning(f"StatePersistHook: failed to persist {register_name}")

    async def restore_all(self, register_map: GatewayRegisterMap) -> int:
        """
        Restore all persisted register values into the register map.

        Args:
            register_map: Gateway register map to restore into

        Returns:
            Number of registers restored
        """
        try:
            if hasattr(self._redis, "hgetall"):
                stored = await self._redis.hgetall(self._key)
            else:
                stored = await self._redis._client.hgetall(self._key)
            if not stored:
                return 0
            count = 0
            for name, raw_value in stored.items():
                if isinstance(name, bytes):
                    name = name.decode()
                try:
                    value = json.loads(raw_value) if isinstance(raw_value, str) else json.loads(raw_value.decode())
                    register_map.set_value(name, value)
                    count += 1
                except (KeyError, json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"StatePersistHook: skip restoring '{name}': {e}")
            logger.info(f"StatePersistHook: restored {count} registers from {self._key}")
            return count
        except Exception:
            logger.opt(exception=True).warning(f"StatePersistHook: failed to restore from {self._key}")
            return 0


__all__ = [
    "RedisPublishHook",
    "CallbackHook",
    "StatePersistHook",
]
