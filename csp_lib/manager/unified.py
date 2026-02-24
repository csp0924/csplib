# =============== Manager - Unified ===============
#
# 統一設備管理器
#
# 整合所有子管理器，提供單一入口點：
#   - UnifiedConfig: 統一管理器配置
#   - UnifiedDeviceManager: 統一設備管理器

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .alarm import AlarmPersistenceManager, AlarmRepository
from .command import CommandRepository, WriteCommandManager
from .data import DataUploadManager
from .device import DeviceManager
from .state import StateSyncManager

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice
    from csp_lib.integration.registry import DeviceRegistry
    from csp_lib.mongo import MongoBatchUploader
    from csp_lib.notification import NotificationDispatcher
    from csp_lib.redis import RedisClient
    from csp_lib.statistics import StatisticsConfig, StatisticsManager

logger = get_logger(__name__)


# ================ 配置 ================


@dataclass
class UnifiedConfig:
    """
    統一管理器配置

    所有子管理器皆為可選，未配置的功能將自動跳過。

    Attributes:
        alarm_repository: 告警持久化 Repository（可選）
        command_repository: 寫入指令 Repository（可選）
        mongo_uploader: MongoDB 批次上傳器（可選）
        redis_client: Redis 客戶端（可選）
        notification_dispatcher: 通知分發器（可選）

    Example:
        ```python
        config = UnifiedConfig(
            alarm_repository=mongo_alarm_repo,
            command_repository=mongo_cmd_repo,
            mongo_uploader=uploader,
            redis_client=redis,
        )
        ```
    """

    alarm_repository: AlarmRepository | None = None
    command_repository: CommandRepository | None = None
    mongo_uploader: MongoBatchUploader | None = None
    redis_client: RedisClient | None = None
    notification_dispatcher: NotificationDispatcher | None = None
    statistics_config: StatisticsConfig | None = None
    device_registry: DeviceRegistry | None = None


# ================ 統一管理器 ================


class UnifiedDeviceManager(AsyncLifecycleMixin):
    """
    統一設備管理器

    整合 DeviceManager、AlarmPersistenceManager、WriteCommandManager、
    DataUploadManager、StateSyncManager、StatisticsManager，提供單一入口點。

    註冊設備後自動串接所有已啟用的功能，使用者無需手動 subscribe 各子管理器。

    Attributes:
        device_manager: 設備讀取管理器
        alarm_manager: 告警持久化管理器（可能為 None）
        command_manager: 寫入指令管理器（可能為 None）
        data_manager: 資料上傳管理器（可能為 None）
        state_manager: 狀態同步管理器（可能為 None）
        statistics_manager: 統計管理器（可能為 None）

    Example:
        ```python
        config = UnifiedConfig(
            alarm_repository=mongo_alarm_repo,
            command_repository=mongo_cmd_repo,
            mongo_uploader=uploader,
            redis_client=redis,
        )

        manager = UnifiedDeviceManager(config)

        # 註冊時指定 collection_name
        manager.register(meter_device, collection_name="meter")
        manager.register(io_device, collection_name="io")

        # 群組註冊
        manager.register_group([rtu1, rtu2], collection_name="rtu_data")

        async with manager:
            await asyncio.sleep(3600)
        ```
    """

    def __init__(self, config: UnifiedConfig) -> None:
        """
        初始化統一設備管理器

        Args:
            config: 統一管理器配置
        """
        self._device_manager = DeviceManager()

        # 根據配置初始化子管理器（可選）
        self._alarm_manager: AlarmPersistenceManager | None = (
            AlarmPersistenceManager(config.alarm_repository, config.notification_dispatcher)
            if config.alarm_repository
            else None
        )
        self._command_manager: WriteCommandManager | None = (
            WriteCommandManager(config.command_repository) if config.command_repository else None
        )
        self._data_manager: DataUploadManager | None = (
            DataUploadManager(config.mongo_uploader) if config.mongo_uploader else None
        )
        self._state_manager: StateSyncManager | None = (
            StateSyncManager(config.redis_client) if config.redis_client else None
        )

        # Statistics manager（需要 mongo_uploader + statistics_config）
        from csp_lib.statistics import StatisticsManager

        self._statistics_manager: StatisticsManager | None = (
            StatisticsManager(config.statistics_config, config.mongo_uploader, config.device_registry)
            if config.statistics_config and config.mongo_uploader
            else None
        )

        logger.info(
            f"UnifiedDeviceManager 初始化: "
            f"alarm={self._alarm_manager is not None}, "
            f"command={self._command_manager is not None}, "
            f"data={self._data_manager is not None}, "
            f"state={self._state_manager is not None}, "
            f"statistics={self._statistics_manager is not None}"
        )

    # ================ 註冊 ================

    def register(
        self,
        device: AsyncModbusDevice,
        collection_name: str | None = None,
    ) -> None:
        """
        註冊獨立設備

        設備將使用自己的 read_loop 進行讀取，並自動訂閱所有已啟用的子管理器。

        Args:
            device: Modbus 設備
            collection_name: MongoDB collection 名稱（Data Upload 用，選填）
        """
        self._device_manager.register(device)
        self._subscribe_all(device, collection_name)
        logger.info(f"UnifiedDeviceManager: 已註冊設備 {device.device_id}")

    def register_group(
        self,
        devices: Sequence[AsyncModbusDevice],
        interval: float = 1.0,
        collection_name: str | None = None,
    ) -> None:
        """
        註冊設備群組

        群組內設備將順序讀取，並自動訂閱所有已啟用的子管理器。
        群組內設備共用同一 collection_name。

        Args:
            devices: 設備列表（必須共用同一 Client）
            interval: 完整讀取一輪的間隔時間（秒）
            collection_name: MongoDB collection 名稱（群組共用，選填）
        """
        self._device_manager.register_group(devices, interval)
        for device in devices:
            self._subscribe_all(device, collection_name)
        device_ids = [d.device_id for d in devices]
        logger.info(f"UnifiedDeviceManager: 已註冊設備群組 {device_ids}")

    def _subscribe_all(
        self,
        device: AsyncModbusDevice,
        collection_name: str | None,
    ) -> None:
        """
        訂閱所有已啟用的子管理器

        Args:
            device: Modbus 設備
            collection_name: MongoDB collection 名稱（可選）
        """
        if self._alarm_manager:
            self._alarm_manager.subscribe(device)

        if self._command_manager:
            self._command_manager.register_device(device)

        if self._data_manager and collection_name:
            self._data_manager.subscribe(device, collection_name)

        if self._state_manager:
            self._state_manager.subscribe(device)

        if self._statistics_manager:
            self._statistics_manager.subscribe(device)

    # ================ 生命週期 ================

    async def _on_start(self) -> None:
        """
        啟動管理器

        啟動所有已註冊設備的讀取循環。
        """
        await self._device_manager.start()
        logger.info("UnifiedDeviceManager 已啟動")

    async def _on_stop(self) -> None:
        """
        停止管理器

        停止所有讀取循環並斷開連線。
        """
        await self._device_manager.stop()
        logger.info("UnifiedDeviceManager 已停止")

    # ================ 屬性 ================

    @property
    def device_manager(self) -> DeviceManager:
        """設備讀取管理器"""
        return self._device_manager

    @property
    def alarm_manager(self) -> AlarmPersistenceManager | None:
        """告警持久化管理器（可能為 None）"""
        return self._alarm_manager

    @property
    def command_manager(self) -> WriteCommandManager | None:
        """寫入指令管理器（可能為 None）"""
        return self._command_manager

    @property
    def data_manager(self) -> DataUploadManager | None:
        """資料上傳管理器（可能為 None）"""
        return self._data_manager

    @property
    def state_manager(self) -> StateSyncManager | None:
        """狀態同步管理器（可能為 None）"""
        return self._state_manager

    @property
    def statistics_manager(self) -> StatisticsManager | None:
        """統計管理器（可能為 None）"""
        return self._statistics_manager

    @property
    def is_running(self) -> bool:
        """管理器是否運行中"""
        return self._device_manager.is_running

    def __repr__(self) -> str:
        return (
            f"<UnifiedDeviceManager "
            f"devices={self._device_manager.standalone_count + sum(len(g.devices) for g in self._device_manager.groups)} "
            f"running={self.is_running}>"
        )


__all__ = [
    "UnifiedConfig",
    "UnifiedDeviceManager",
]
