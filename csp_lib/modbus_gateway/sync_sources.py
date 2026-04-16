"""
Built-in DataSyncSource implementations.

DataSyncSource 將外部資料來源（Redis / 輪詢回呼）的數據同步到 gateway 的 Input Registers。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from csp_lib.core import get_logger

logger = get_logger(__name__)

# Type alias matching protocol.py
UpdateRegisterCallback = Callable[[str, Any], Awaitable[None]]


class RedisSubscriptionSource:
    """
    Subscribes to a Redis channel and updates registers from published messages.

    Expected message format (JSON)::

        {"register": "<name>", "value": <physical_value>}

    Or batch::

        [{"register": "<name>", "value": <physical_value>}, ...]

    Or key-value shorthand::

        {"<register_name>": <physical_value>, ...}

    Satisfies DataSyncSource protocol.

    Args:
        redis_client: redis.asyncio.Redis 或 csp_lib.redis.RedisClient 實例
        channel: Redis channel 名稱
        batch_mode: 若 True，將 payload 視為 {name: value} dict（簡潔模式）
    """

    def __init__(self, redis_client: Any, channel: str = "gateway:sync", batch_mode: bool = True) -> None:
        self._redis = redis_client
        self._channel = channel
        self._batch_mode = batch_mode
        self._update_cb: UpdateRegisterCallback | None = None
        self._task: asyncio.Task | None = None

    async def start(self, update_callback: UpdateRegisterCallback) -> None:
        self._update_cb = update_callback
        self._task = asyncio.create_task(self._listen_loop(), name=f"redis_sync_{self._channel}")
        logger.info(f"RedisSubscriptionSource started: channel={self._channel}")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"RedisSubscriptionSource stopped: channel={self._channel}")

    async def _listen_loop(self) -> None:
        # Get pubsub - support both RedisClient and raw redis.asyncio.Redis
        if hasattr(self._redis, "pubsub"):
            pubsub = self._redis.pubsub()
        else:
            pubsub = self._redis.pubsub()

        await pubsub.subscribe(self._channel)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    await self._handle_message(msg["data"])
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.opt(exception=True).error(f"RedisSubscriptionSource listen error: {self._channel}")
        finally:
            try:
                await pubsub.unsubscribe(self._channel)
                await pubsub.aclose()
            except Exception:
                pass

    async def _dispatch(self, name: str, value: Any) -> None:
        """單次 register 寫入；未知 register / HOLDING 拒絕均不中斷呼叫端 loop。"""
        assert self._update_cb is not None
        try:
            await self._update_cb(name, value)
        except KeyError:
            logger.debug(f"RedisSync: unknown register '{name}', skipping")
        except PermissionError as e:
            logger.warning(f"RedisSync: rejected write — {e}")

    async def _handle_message(self, data: Any) -> None:
        if self._update_cb is None:
            return
        try:
            if isinstance(data, bytes):
                data = data.decode()
            payload = json.loads(data)

            if isinstance(payload, dict) and "register" in payload and "value" in payload:
                # Single: {"register": "soc", "value": 75.5}
                # 優先匹配，避免被 batch_mode shorthand 吞掉
                await self._dispatch(payload["register"], payload["value"])
            elif isinstance(payload, list):
                # Batch: [{"register": "soc", "value": 75.5}, ...]
                for item in payload:
                    name = item.get("register")
                    value = item.get("value")
                    if name is not None and value is not None:
                        await self._dispatch(name, value)
            elif self._batch_mode and isinstance(payload, dict):
                # Key-value shorthand: {"soc": 75.5, "soh": 98.0}
                for name, value in payload.items():
                    await self._dispatch(name, value)

        except (json.JSONDecodeError, TypeError):
            logger.opt(exception=True).warning(f"RedisSync: invalid message on {self._channel}")


class PollingCallbackSource:
    """
    Periodically calls a user-provided async function to get register values.

    The callback returns a dict of {register_name: physical_value}.
    Only non-None values are written.

    Satisfies DataSyncSource protocol.

    Args:
        callback: async function() -> dict[str, Any]
        interval: polling interval in seconds
    """

    def __init__(
        self,
        callback: Callable[[], Awaitable[dict[str, Any]]],
        interval: float = 1.0,
    ) -> None:
        self._callback = callback
        self._interval = interval
        self._update_cb: UpdateRegisterCallback | None = None
        self._task: asyncio.Task | None = None

    async def start(self, update_callback: UpdateRegisterCallback) -> None:
        self._update_cb = update_callback
        self._task = asyncio.create_task(self._poll_loop(), name="polling_sync")
        logger.info(f"PollingCallbackSource started: interval={self._interval}s")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PollingCallbackSource stopped")

    async def _dispatch(self, name: str, value: Any) -> None:
        """單次 register 寫入；未知 register / HOLDING 拒絕均不中斷 poll loop。"""
        assert self._update_cb is not None
        try:
            await self._update_cb(name, value)
        except KeyError:
            logger.debug(f"PollingSync: unknown register '{name}', skipping")
        except PermissionError as e:
            logger.warning(f"PollingSync: rejected write — {e}")

    async def _poll_loop(self) -> None:
        try:
            while True:
                try:
                    values = await self._callback()
                    if self._update_cb and values:
                        for name, value in values.items():
                            if value is not None:
                                await self._dispatch(name, value)
                except Exception:
                    logger.opt(exception=True).warning("PollingCallbackSource: callback error")
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass


__all__ = [
    "RedisSubscriptionSource",
    "PollingCallbackSource",
]
