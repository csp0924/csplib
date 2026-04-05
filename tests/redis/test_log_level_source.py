# =============== Redis Tests - RedisLogLevelSource ===============
#
# RedisLogLevelSource 遠端等級來源測試（Redis 全 mock）

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from csp_lib.core.logging.remote import RemoteLevelSource
from csp_lib.redis.log_level_source import RedisLogLevelSource


class TestRedisLogLevelSourceProtocol:
    """Protocol 符合性測試"""

    def test_implements_remote_level_source(self):
        """RedisLogLevelSource 符合 RemoteLevelSource Protocol"""
        mock_client = MagicMock()
        source = RedisLogLevelSource(mock_client)
        assert isinstance(source, RemoteLevelSource)


class TestRedisLogLevelSourceFetch:
    """fetch_levels 測試"""

    async def test_fetch_levels(self):
        """從 Redis Hash 讀取等級設定"""
        mock_client = MagicMock()
        # hgetall 回傳 dict（模擬 RedisClient.hgetall）
        mock_client.hgetall = AsyncMock(
            return_value={
                "csp_lib.mongo": "debug",
                "csp_lib.redis": "warning",
                "": "info",
            }
        )

        source = RedisLogLevelSource(mock_client, key_prefix="test")
        levels = await source.fetch_levels()

        assert levels["csp_lib.mongo"] == "DEBUG"
        assert levels["csp_lib.redis"] == "WARNING"
        assert levels[""] == "INFO"
        mock_client.hgetall.assert_awaited_once_with("test:log_levels")

    async def test_fetch_levels_bytes(self):
        """Redis 回傳 bytes 時正確解碼"""
        mock_client = MagicMock()
        mock_client.hgetall = AsyncMock(
            return_value={
                b"csp_lib.mongo": b"debug",
            }
        )

        source = RedisLogLevelSource(mock_client)
        levels = await source.fetch_levels()

        assert levels["csp_lib.mongo"] == "DEBUG"

    async def test_fetch_levels_empty(self):
        """Redis 無資料時回傳空 dict"""
        mock_client = MagicMock()
        mock_client.hgetall = AsyncMock(return_value={})

        source = RedisLogLevelSource(mock_client)
        levels = await source.fetch_levels()
        assert levels == {}


class TestRedisLogLevelSourceSubscribe:
    """subscribe 測試"""

    async def test_subscribe(self):
        """訂閱 Redis Pub/Sub channel"""
        mock_client = MagicMock()
        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_client.pubsub = MagicMock(return_value=mock_pubsub)

        # 模擬一個訊息後結束
        async def _listen():
            yield {"type": "subscribe", "data": 1}
            yield {"type": "message", "data": b"csp_lib.mongo:DEBUG"}

        mock_pubsub.listen = _listen

        callback = MagicMock()
        source = RedisLogLevelSource(mock_client, key_prefix="myapp")
        await source.subscribe(callback)

        # 等待背景 task 執行
        await asyncio.sleep(0.1)

        # 驗證 subscribe 呼叫正確的 channel
        mock_pubsub.subscribe.assert_awaited_once_with("myapp:log_levels:changed")

        # callback 應被呼叫（type=message 的那筆）
        callback.assert_called_once_with("csp_lib.mongo", "DEBUG")
