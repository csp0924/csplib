# =============== Manager Command - Redis Adapter ===============
#
# Redis Pub/Sub 指令適配器
#
# 監聽 Redis channel 接收寫入指令並轉發至 WriteCommandManager

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from csp_lib.core import get_logger

from ..schema import CommandSource

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from ..manager import WriteCommandManager

logger = get_logger(__name__)


class RedisCommandAdapter:
    """
    Redis Pub/Sub 指令適配器

    監聯指定 channel，解析 JSON 指令並轉發至 WriteCommandManager。
    執行完成後將結果發布到結果 channel。

    Attributes:
        _redis: Redis 客戶端
        _manager: 寫入指令管理器
        _command_channel: 接收指令的 channel
        _result_channel: 發布結果的 channel

    Example:
        ```python
        from csp_lib.manager.command import WriteCommandManager, RedisCommandAdapter

        adapter = RedisCommandAdapter(
            redis_client=redis_client._client,  # 底層 redis.asyncio.Redis
            manager=command_manager,
            command_channel="channel:commands:write",
            result_channel="channel:commands:result",
        )
        await adapter.start()

        # 外部可透過 Redis 發送指令：
        # PUBLISH channel:commands:write '{"device_id":"d1","point_name":"sp","value":100}'
        ```

    Message Format:
        指令（發送至 command_channel）:
        ```json
        {
            "device_id": "device_001",
            "point_name": "setpoint",
            "value": 25.5,
            "verify": false,
            "source_info": {"user_id": "admin", "client_ip": "192.168.1.1"}
        }
        ```

        結果（發布至 result_channel）:
        ```json
        {
            "command_id": "uuid",
            "device_id": "device_001",
            "point_name": "setpoint",
            "status": "success",
            "value": 25.5,
            "error_message": ""
        }
        ```
    """

    DEFAULT_COMMAND_CHANNEL = "channel:commands:write"
    DEFAULT_RESULT_CHANNEL = "channel:commands:result"

    def __init__(
        self,
        redis_client: Redis,
        manager: WriteCommandManager,
        command_channel: str | None = None,
        result_channel: str | None = None,
    ) -> None:
        """
        初始化 Redis 指令適配器

        Args:
            redis_client: redis.asyncio.Redis 客戶端實例
            manager: 寫入指令管理器
            command_channel: 接收指令的 channel
            result_channel: 發布結果的 channel
        """
        self._redis = redis_client
        self._manager = manager
        self._command_channel = command_channel or self.DEFAULT_COMMAND_CHANNEL
        self._result_channel = result_channel or self.DEFAULT_RESULT_CHANNEL
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        """是否正在運行"""
        return self._running

    async def start(self) -> None:
        """
        啟動監聽

        開始訂閱 command_channel 並處理指令。
        """
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info(f"Redis 指令適配器已啟動: {self._command_channel}")

    async def stop(self) -> None:
        """
        停止監聽

        取消訂閱並停止處理。
        """
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Redis 指令適配器已停止")

    async def _listen_loop(self) -> None:
        """監聽循環"""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._command_channel)

        try:
            while self._running:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    await self._handle_message(message["data"])
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(self._command_channel)
            await pubsub.aclose()

    async def _handle_message(self, data: str | bytes) -> None:
        """處理訊息"""
        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")

            command_data = json.loads(data)
            logger.debug(f"收到寫入指令: {command_data}")

            # 執行指令
            result = await self._manager.execute_from_dict(
                command_data,
                source=CommandSource.REDIS_PUBSUB,
            )

            # 發布結果
            result_message = json.dumps(
                {
                    "command_id": command_data.get("command_id", ""),
                    "device_id": command_data.get("device_id", ""),
                    "point_name": result.point_name,
                    "status": result.status.value,
                    "value": result.value,
                    "error_message": result.error_message,
                }
            )
            await self._redis.publish(self._result_channel, result_message)

        except json.JSONDecodeError as e:
            logger.error(f"指令 JSON 解析失敗: {e}")
        except KeyError as e:
            logger.error(f"指令缺少必要欄位: {e}")
        except Exception as e:
            logger.error(f"指令處理失敗: {e}")


__all__ = [
    "RedisCommandAdapter",
]
