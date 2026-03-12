# =============== Integration Distributed - Site Runner ===============
#
# 遠端站台執行器
#
# 簡化 Computer_1/Computer_2 的設備端設定：
#   - RemoteSiteRunner: 組合 UnifiedDeviceManager + RedisCommandAdapter

from __future__ import annotations

from typing import TYPE_CHECKING

from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.manager.command.adapters.config import CommandAdapterConfig
from csp_lib.manager.command.adapters.redis import RedisCommandAdapter

if TYPE_CHECKING:
    from csp_lib.manager import UnifiedDeviceManager
    from csp_lib.redis import RedisClient

    from .config import RemoteSiteConfig

logger = get_logger("csp_lib.integration.distributed.site_runner")


class RemoteSiteRunner(AsyncLifecycleMixin):
    """
    遠端站台執行器

    用於 Computer_1/Computer_2：管理本地設備並監聽 Redis 指令。

    組合：
    - UnifiedDeviceManager: 設備生命週期 + StateSyncManager -> Redis
    - RedisCommandAdapter: 監聽站台專屬指令 channel

    Usage::

        site_config = RemoteSiteConfig(
            site_id="site_bms",
            device_ids=["bms_1"],
        )
        runner = RemoteSiteRunner(
            config=site_config,
            unified_manager=unified_mgr,
            redis_client=redis,
        )
        async with runner:
            await asyncio.Event().wait()
    """

    def __init__(
        self,
        config: RemoteSiteConfig,
        unified_manager: UnifiedDeviceManager,
        redis_client: RedisClient,
    ) -> None:
        self._config = config
        self._unified_manager = unified_manager
        self._redis = redis_client
        self._adapter: RedisCommandAdapter | None = None

    async def _on_start(self) -> None:
        """啟動站台：連接設備 + 開始監聽指令"""
        # 1. 啟動 UnifiedDeviceManager（連接設備、啟動讀取、啟動 Redis sync）
        await self._unified_manager.start()

        # 2. 建立並啟動 RedisCommandAdapter（站台專屬 channel）
        command_manager = self._unified_manager.command_manager
        if command_manager is None:
            logger.warning("UnifiedDeviceManager has no command_manager; RedisCommandAdapter will not start.")
        else:
            adapter_config = CommandAdapterConfig(
                command_channel=self._config.effective_command_channel,
                result_channel=self._config.effective_result_channel,
            )
            if self._redis._client is None:
                logger.warning("Redis client is not connected; RedisCommandAdapter will not start.")
            else:
                self._adapter = RedisCommandAdapter(
                    redis_client=self._redis._client,
                    manager=command_manager,
                    config=adapter_config,
                )
                await self._adapter.start()

        logger.info(f"RemoteSiteRunner started: site={self._config.site_id}")

    async def _on_stop(self) -> None:
        """停止站台"""
        # 停止 adapter
        if self._adapter is not None:
            await self._adapter.stop()
            self._adapter = None

        # 停止 UnifiedDeviceManager
        await self._unified_manager.stop()

        logger.info(f"RemoteSiteRunner stopped: site={self._config.site_id}")

    @property
    def site_id(self) -> str:
        """站台 ID"""
        return self._config.site_id

    @property
    def unified_manager(self) -> UnifiedDeviceManager:
        """統一設備管理器"""
        return self._unified_manager

    @property
    def adapter(self) -> RedisCommandAdapter | None:
        """Redis 指令適配器"""
        return self._adapter

    @property
    def is_running(self) -> bool:
        """是否正在執行"""
        return self._unified_manager.is_running


__all__ = [
    "RemoteSiteRunner",
]
