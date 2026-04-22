# =============== Manager - Unified ===============
#
# 統一設備管理器
#
# 整合所有子管理器，提供單一入口點：
#   - UnifiedConfig: 統一管理器配置
#   - UnifiedDeviceManager: 統一設備管理器

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .alarm import AlarmPersistenceManager, AlarmRepository
from .command import CommandRepository, WriteCommandManager
from .data import DataUploadManager, UploadTarget
from .device import DeviceManager
from .state import StateSyncManager

if TYPE_CHECKING:
    from csp_lib.equipment.device.protocol import DeviceProtocol
    from csp_lib.integration.registry import DeviceRegistry
    from csp_lib.manager.base import BatchUploader
    from csp_lib.notification import NotificationDispatcher
    from csp_lib.redis import RedisClient
    from csp_lib.statistics import StatisticsConfig, StatisticsManager

logger = get_logger(__name__)


# ================ 配置 ================


@dataclass(frozen=True, slots=True)
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
    batch_uploader: BatchUploader | None = None
    mongo_uploader: BatchUploader | None = None
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
        self._config = config
        self._device_manager = DeviceManager()

        # 解析 uploader（支援 deprecated mongo_uploader 過渡）
        resolved_uploader = self._resolve_uploader()

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
            DataUploadManager(resolved_uploader) if resolved_uploader else None
        )
        self._state_manager: StateSyncManager | None = (
            StateSyncManager(config.redis_client) if config.redis_client else None
        )

        # Statistics manager（需要 uploader + statistics_config + csp_lib.statistics）
        self._statistics_manager: StatisticsManager | None = None
        if config.statistics_config and resolved_uploader:
            try:
                from csp_lib.statistics import StatisticsManager

                self._statistics_manager = StatisticsManager(
                    config.statistics_config, resolved_uploader, config.device_registry
                )
            except ImportError:
                logger.warning("Statistics module not available, skipping StatisticsManager initialization")

        self._register_lock = threading.Lock()

        logger.info(
            f"UnifiedDeviceManager 初始化: "
            f"alarm={self._alarm_manager is not None}, "
            f"command={self._command_manager is not None}, "
            f"data={self._data_manager is not None}, "
            f"state={self._state_manager is not None}, "
            f"statistics={self._statistics_manager is not None}"
        )

    def _resolve_uploader(self) -> BatchUploader | None:
        """解析 uploader，優先使用 batch_uploader，降級到 deprecated mongo_uploader。"""
        if self._config.batch_uploader is not None:
            return self._config.batch_uploader
        if self._config.mongo_uploader is not None:
            import warnings

            warnings.warn(
                "UnifiedConfig.mongo_uploader is deprecated, use batch_uploader instead. "
                "mongo_uploader will be removed in v1.0.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            return self._config.mongo_uploader
        return None

    # ================ 註冊 ================

    def register(
        self,
        device: DeviceProtocol,
        collection_name: str | None = None,
        traits: Sequence[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        *,
        outputs: Sequence[UploadTarget] | None = None,
    ) -> None:
        """
        註冊獨立設備

        設備將使用自己的 read_loop 進行讀取，並自動訂閱所有已啟用的子管理器。
        若配置了 DeviceRegistry，會同時將設備註冊到 Registry。

        Args:
            device: 實作 DeviceProtocol 的設備
            collection_name: Legacy 單一 collection 名稱（Data Upload 用，與 ``outputs`` 互斥）
            traits: 設備 trait 標籤列表（選填，用於 DeviceRegistry）
            metadata: 設備靜態資訊（選填，用於 DeviceRegistry）
            outputs: Fan-out 模式的 ``UploadTarget`` 列表（keyword-only，與 ``collection_name`` 互斥）

        Raises:
            ValueError: 同時提供 ``collection_name`` 與 ``outputs``
        """
        if collection_name is not None and outputs is not None:
            raise ValueError(
                f"UnifiedDeviceManager.register(device_id={device.device_id!r}): "
                "collection_name 與 outputs 不可同時提供"
            )
        with self._register_lock:
            self._device_manager.register(device)
            self._subscribe_all(device, collection_name, outputs)
            self._register_to_registry(device, traits, metadata)
        logger.info(f"UnifiedDeviceManager: 已註冊設備 {device.device_id}")

    def register_group(
        self,
        devices: Sequence[DeviceProtocol],
        interval: float = 1.0,
        collection_name: str | None = None,
        traits: Sequence[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        *,
        outputs: Sequence[UploadTarget] | None = None,
    ) -> None:
        """
        註冊設備群組

        群組內設備將順序讀取，並自動訂閱所有已啟用的子管理器。
        群組內設備共用同一 collection_name 或同一份 outputs。
        若配置了 DeviceRegistry，所有設備會同時註冊（共用相同 traits/metadata）。

        Args:
            devices: 設備列表（必須共用同一 Client）
            interval: 完整讀取一輪的間隔時間（秒）
            collection_name: Legacy 單一 collection 名稱（群組共用，與 ``outputs`` 互斥）
            traits: 設備 trait 標籤列表（選填，套用到群組所有設備）
            metadata: 設備靜態資訊（選填，套用到群組所有設備）
            outputs: Fan-out 模式的 ``UploadTarget`` 列表（群組共用，與 ``collection_name`` 互斥）

        Raises:
            ValueError: 同時提供 ``collection_name`` 與 ``outputs``
        """
        if collection_name is not None and outputs is not None:
            device_ids = [d.device_id for d in devices]
            raise ValueError(
                f"UnifiedDeviceManager.register_group(devices={device_ids!r}): collection_name 與 outputs 不可同時提供"
            )
        with self._register_lock:
            self._device_manager.register_group(devices, interval)
            for device in devices:
                self._subscribe_all(device, collection_name, outputs)
                self._register_to_registry(device, traits, metadata)
        device_ids = [d.device_id for d in devices]
        logger.info(f"UnifiedDeviceManager: 已註冊設備群組 {device_ids}")

    def _register_to_registry(
        self,
        device: DeviceProtocol,
        traits: Sequence[str] | None,
        metadata: Mapping[str, Any] | None,
    ) -> None:
        """
        若配置了 DeviceRegistry，將設備註冊到 Registry。

        自動從 ``device`` 探測可注入的 metadata（如 ``used_unit_ids``），
        使用者提供的 metadata 一律覆蓋 auto 值。

        Args:
            device: 實作 DeviceProtocol 的設備
            traits: trait 標籤列表（可選）
            metadata: 靜態資訊（可選）
        """
        if self._config.device_registry is not None:
            self._config.device_registry.register(
                device,
                traits=list(traits) if traits else [],
                metadata=self._build_metadata(device, metadata),
            )

    def _build_metadata(
        self,
        device: DeviceProtocol,
        user_metadata: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """建構 DeviceRegistry metadata，自動注入 device 可探測的屬性。

        注入規則（低優先，使用者提供的 metadata 永遠覆蓋 auto 值）：
            - ``used_unit_ids``: 若 device 有此屬性且型別為集合類，轉 sorted list
              後注入（sorted 確保 JSON 序列化穩定）。

        Args:
            device: 實作 DeviceProtocol 的設備
            user_metadata: 使用者提供的 metadata（可為 ``None``）

        Returns:
            合併後的 metadata dict
        """
        auto: dict[str, Any] = {}
        used = getattr(device, "used_unit_ids", None)
        # 用 isinstance 檢查避開 MagicMock 物件（它有 used_unit_ids 但不是真的集合）
        if isinstance(used, (frozenset, set, list, tuple)):
            auto["used_unit_ids"] = sorted(used)
        return {**auto, **(dict(user_metadata) if user_metadata else {})}

    def _subscribe_all(
        self,
        device: DeviceProtocol,
        collection_name: str | None,
        outputs: Sequence[UploadTarget] | None,
    ) -> None:
        """
        訂閱所有已啟用的子管理器

        Args:
            device: 實作 DeviceProtocol 的設備
            collection_name: Legacy 單一 collection 名稱（可選）
            outputs: Fan-out 模式的 ``UploadTarget`` 列表（可選）
        """
        if self._alarm_manager:
            self._alarm_manager.subscribe(device)

        if self._command_manager:
            # 統一走 subscribe()（v0.8 新 API）；內部仍委派至 register_device 保持向後相容。
            self._command_manager.subscribe(device)

        if self._data_manager:
            # 優先走 fan-out 路徑；其次 legacy collection_name；兩者皆無則跳過 data_manager。
            if outputs is not None:
                self._data_manager.configure(device.device_id, outputs=list(outputs))
                self._data_manager.subscribe(device)
            elif collection_name is not None:
                self._data_manager.configure(device.device_id, collection_name)
                self._data_manager.subscribe(device)

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
