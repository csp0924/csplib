# =============== Redis - Client ===============
#
# 異步 Redis 客戶端封裝
#
# 基於 redis.asyncio 提供連線管理與基本操作。

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from csp_lib.core import get_logger

logger = get_logger(__name__)


class RedisClient:
    """
    異步 Redis 客戶端封裝

    提供連線管理與常用操作的封裝，簡化 Redis 互動。

    Attributes:
        _url: Redis 連線 URL
        _client: redis.asyncio.Redis 實例

    Example:
        ```python
        client = RedisClient("redis://localhost:6379")
        await client.connect()

        # Hash 操作
        await client.hset("device:001:state", {"temperature": "25.5"})
        state = await client.hgetall("device:001:state")

        # Pub/Sub
        await client.publish("channel:device:001:data", '{"temp": 25.5}')

        await client.disconnect()
        ```
    """

    def __init__(self, url: str = "redis://localhost:6379") -> None:
        """
        初始化 Redis 客戶端

        Args:
            url: Redis 連線 URL（支援 redis:// 或 rediss://）
        """
        self._url = url
        self._client: Redis | None = None

    @property
    def is_connected(self) -> bool:
        """是否已連線"""
        return self._client is not None

    async def connect(self) -> None:
        """
        建立 Redis 連線

        Raises:
            ConnectionError: 連線失敗
        """
        if self._client is not None:
            return

        self._client = Redis.from_url(self._url, decode_responses=True)
        # 測試連線
        await self._client.ping()
        logger.info(f"Redis 已連線: {self._url}")

    async def disconnect(self) -> None:
        """關閉 Redis 連線"""
        if self._client is None:
            return

        await self._client.aclose()
        self._client = None
        logger.info("Redis 已斷線")

    # ================ Hash 操作 ================

    async def hset(self, name: str, mapping: dict[str, Any]) -> int:
        """
        設定 Hash 欄位

        Args:
            name: Hash key 名稱
            mapping: 欄位與值的字典

        Returns:
            新增的欄位數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")

        # 將所有值轉為字串（Redis Hash 值必須是字串）
        str_mapping = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in mapping.items()}
        return await self._client.hset(name, mapping=str_mapping)

    async def hgetall(self, name: str) -> dict[str, Any]:
        """
        取得 Hash 所有欄位

        Args:
            name: Hash key 名稱

        Returns:
            欄位與值的字典
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")

        result = await self._client.hgetall(name)
        # 嘗試解析 JSON
        parsed = {}
        for k, v in result.items():
            try:
                parsed[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                parsed[k] = v
        return parsed

    async def hdel(self, name: str, *keys: str) -> int:
        """
        刪除 Hash 欄位

        Args:
            name: Hash key 名稱
            keys: 要刪除的欄位名稱

        Returns:
            刪除的欄位數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.hdel(name, *keys)

    # ================ String 操作 ================

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        """
        設定字串值

        Args:
            name: Key 名稱
            value: 值
            ex: 過期時間（秒）

        Returns:
            是否成功
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        result = await self._client.set(name, value, ex=ex)
        return result is True

    async def get(self, name: str) -> str | None:
        """
        取得字串值

        Args:
            name: Key 名稱

        Returns:
            值，不存在時返回 None
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.get(name)

    # ================ Set 操作 ================

    async def sadd(self, name: str, *values: str) -> int:
        """
        新增 Set 成員

        Args:
            name: Set key 名稱
            values: 要新增的值

        Returns:
            新增的成員數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.sadd(name, *values)

    async def srem(self, name: str, *values: str) -> int:
        """
        移除 Set 成員

        Args:
            name: Set key 名稱
            values: 要移除的值

        Returns:
            移除的成員數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.srem(name, *values)

    async def smembers(self, name: str) -> set[str]:
        """
        取得 Set 所有成員

        Args:
            name: Set key 名稱

        Returns:
            成員集合
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.smembers(name)

    # ================ Pub/Sub ================

    async def publish(self, channel: str, message: str) -> int:
        """
        發布訊息到 channel

        Args:
            channel: Channel 名稱
            message: 訊息內容（字串）

        Returns:
            接收到訊息的訂閱者數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.publish(channel, message)

    # ================ Key 操作 ================

    async def delete(self, *names: str) -> int:
        """
        刪除 Key

        Args:
            names: 要刪除的 Key 名稱

        Returns:
            刪除的 Key 數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.delete(*names)

    async def exists(self, *names: str) -> int:
        """
        檢查 Key 是否存在

        Args:
            names: 要檢查的 Key 名稱

        Returns:
            存在的 Key 數量
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.exists(*names)

    async def expire(self, name: str, seconds: int) -> bool:
        """
        設定 Key 過期時間

        Args:
            name: Key 名稱
            seconds: 過期時間（秒）

        Returns:
            是否成功設定（Key 存在時返回 True）
        """
        if not self._client:
            raise ConnectionError("Redis 尚未連線")
        return await self._client.expire(name, seconds)

    # ================ Context Manager ================

    async def __aenter__(self) -> "RedisClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()


__all__ = [
    "RedisClient",
]
