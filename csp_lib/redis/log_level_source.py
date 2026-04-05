# =============== Redis - Log Level Source ===============
#
# Redis 遠端 log 等級來源
#
# 透過 Redis Hash + Pub/Sub 提供即時等級同步：
#   - RedisLogLevelSource: 實作 RemoteLevelSource 協定

from __future__ import annotations

import asyncio
from typing import Any, Callable

from csp_lib.core import get_logger

from .client import RedisClient

logger = get_logger(__name__)


class RedisLogLevelSource:
    """Redis 遠端 log 等級來源。

    使用 Redis Hash 儲存模組等級設定，並透過 Pub/Sub
    提供即時變更通知。

    Redis 結構：
    - Hash key: ``{key_prefix}:log_levels``
      - field = 模組名稱（空字串代表預設等級）
      - value = 等級字串
    - Channel: ``{key_prefix}:log_levels:changed``
      - 訊息格式: ``"module:level"``

    Attributes:
        _client: Redis 客戶端。
        _key_prefix: Redis key 前綴。
        _hash_key: 完整 Hash key。
        _channel: 完整 Pub/Sub channel 名稱。

    Example:
        ```python
        source = RedisLogLevelSource(redis_client, key_prefix="myapp")
        levels = await source.fetch_levels()
        # {"csp_lib.mongo": "DEBUG", "": "INFO"}
        ```
    """

    def __init__(self, client: RedisClient, key_prefix: str = "csp") -> None:
        self._client = client
        self._key_prefix = key_prefix
        self._hash_key = f"{key_prefix}:log_levels"
        self._channel = f"{key_prefix}:log_levels:changed"
        self._listen_task: asyncio.Task[None] | None = None
        self._pubsub: Any | None = None

    async def fetch_levels(self) -> dict[str, str]:
        """從 Redis Hash 拉取所有模組等級設定。

        使用 ``RedisClient.hgetall()`` 取得所有欄位。
        注意：``hgetall`` 會嘗試 JSON 解析，但等級值為純字串，
        解析後仍為字串。

        Returns:
            模組 → 等級對應表。

        Raises:
            ConnectionError: Redis 尚未連線。
        """
        raw: dict[str, Any] = await self._client.hgetall(self._hash_key)
        result: dict[str, str] = {}
        for k, v in raw.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            val = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            result[key] = val.upper()
        logger.debug("從 Redis 拉取 {} 筆 log 等級設定", len(result))
        return result

    async def subscribe(self, callback: Callable[[str, str], None]) -> None:
        """訂閱等級變更事件。

        透過 Redis Pub/Sub 監聽 ``{key_prefix}:log_levels:changed`` channel。
        訊息格式為 ``"module:level"``。

        Args:
            callback: 等級變更回呼函式 (module, level)。
        """
        self._pubsub = self._client.pubsub()
        await self._pubsub.subscribe(self._channel)
        logger.info("已訂閱 Redis log 等級變更 channel: {}", self._channel)

        async def _listen() -> None:
            pubsub = self._pubsub
            assert pubsub is not None
            try:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    # 格式: "module:level"
                    parts = data.split(":", 1)
                    if len(parts) == 2:
                        module, level = parts[0], parts[1].upper()
                        logger.debug("遠端等級變更: {} -> {}", module, level)
                        callback(module, level)
            except asyncio.CancelledError:
                return

        self._listen_task = asyncio.create_task(_listen())

    async def close(self) -> None:
        """停止訂閱並釋放 Pub/Sub 資源。"""
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self._pubsub is not None:
            await self._pubsub.unsubscribe(self._channel)
            self._pubsub = None


__all__ = [
    "RedisLogLevelSource",
]
