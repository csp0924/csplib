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
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from csp_lib.core import AsyncLifecycleMixin, get_logger

from .alarm import AlarmPersistenceManager, AlarmRepository
from .command import CommandRepository, WriteCommandManager
from .data import DataUploadManager, UploadTarget
from .device import DeviceManager
from .state import StateSyncManager

if TYPE_CHECKING:
    from csp_lib.equipment.device.protocol import DeviceProtocol
    from csp_lib.integration.registry import DeviceRegistry
    from csp_lib.manager.base import BatchUploader, LeaderGate
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


# ================ 觀測狀態 ================


@dataclass(frozen=True, slots=True)
class UnifiedManagerStatus:
    """UnifiedDeviceManager 觀測快照。

    ``describe()`` 的回傳型別，供外部（GUI / Monitor / Cluster 狀態報告）
    讀取當前 manager 狀態。所有欄位皆為讀 snapshot，無 I/O。

    Attributes:
        devices_count: 目前註冊的設備總數（standalone + group 內設備）
        running: Manager 是否處於執行中（委派 ``device_manager.is_running``）
        is_leader: 當前 leader 狀態；``None`` 代表未注入 ``leader_gate``
        alarms_active_count: 活躍告警數量；``None`` 代表未配置 alarm_manager
            或 alarm_manager 不暴露 ``active_count`` 屬性
        command_queue_depth: 寫入指令佇列深度；Wave 2a 先回 ``None``
            （待子 manager 補 ``describe``）
        upload_queue_depth: 上傳佇列深度；Wave 2a 先回 ``None``（同上）
        state_sync_enabled: 是否啟用 StateSyncManager
        statistics_enabled: 是否啟用 StatisticsManager
    """

    devices_count: int
    running: bool
    is_leader: bool | None
    alarms_active_count: int | None
    command_queue_depth: int | None
    upload_queue_depth: int | None
    state_sync_enabled: bool
    statistics_enabled: bool


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

    Example (cluster / HA 部署 — 注入 leader_gate)::

        from csp_lib.manager import AlwaysLeaderGate  # or cluster-provided gate

        # 注入 leader_gate：非 leader 節點不會啟動 device I/O，
        # 且內部 WriteCommandManager 會在非 leader 時 raise NotLeaderError。
        manager = UnifiedDeviceManager(config, leader_gate=cluster_gate)

        async with manager:
            # follower 節點：_on_start 跳過 device_manager.start()
            # leader 節點：正常啟動並處理事件
            await asyncio.sleep(3600)

        # 查詢觀測狀態
        status = manager.describe()
        print(status.is_leader, status.devices_count)
    """

    def __init__(
        self,
        config: UnifiedConfig,
        *,
        leader_gate: LeaderGate | None = None,
    ) -> None:
        """
        初始化統一設備管理器

        Args:
            config: 統一管理器配置
            leader_gate: Leader 閘門（keyword-only，可選）。注入後：

                - ``_on_start`` 會檢查 ``is_leader``，非 leader 跳過
                  ``device_manager.start()``（不啟動讀取 / 不連線）
                - 若有 ``command_manager``，其 ``execute()`` 在非 leader 時
                  會 raise ``NotLeaderError``
                - 若有 ``state_manager``，其事件 handler 在非 leader 時
                  會早退不寫 Redis

                未注入時 manager 視為永遠是 leader（等同傳入
                ``AlwaysLeaderGate``）。
        """
        self._config = config
        self._leader_gate = leader_gate
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
            WriteCommandManager(config.command_repository, leader_gate=leader_gate)
            if config.command_repository
            else None
        )
        self._data_manager: DataUploadManager | None = (
            DataUploadManager(resolved_uploader) if resolved_uploader else None
        )
        self._state_manager: StateSyncManager | None = (
            StateSyncManager(config.redis_client, leader_gate=leader_gate) if config.redis_client else None
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

    @staticmethod
    def _check_output_exclusivity(
        *,
        label: str,
        collection_name: str | None,
        outputs: Sequence[UploadTarget] | None,
    ) -> None:
        if collection_name is not None and outputs is not None:
            raise ValueError(f"{label}: collection_name 與 outputs 不可同時提供")

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
        self._check_output_exclusivity(
            label=f"UnifiedDeviceManager.register(device_id={device.device_id!r})",
            collection_name=collection_name,
            outputs=outputs,
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
        self._check_output_exclusivity(
            label=f"UnifiedDeviceManager.register_group(devices={[d.device_id for d in devices]!r})",
            collection_name=collection_name,
            outputs=outputs,
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

    # ================ 解除註冊 ================

    def _cascade_unsubscribe_device(self, device: DeviceProtocol, *, log_prefix: str) -> None:
        """級聯解除 device 在所有子 manager + registry 的訂閱。

        每步獨立 ``try/except``，單步失敗僅 ``warn``，不中斷其他步驟；
        確保部分失敗（如 Redis 斷線）不會導致設備卡在 half-registered 狀態。

        呼叫順序為「倒序相依」：先拆事件訂閱再拆 registry，
        供 ``unregister`` 與 ``unregister_group`` 共用。
        """
        did = device.device_id

        def _step(name: str, action: Callable[[], None]) -> None:
            try:
                action()
            except Exception as e:
                logger.warning("{}: {} 失敗 {} err={}", log_prefix, name, did, e)

        alarm = self._alarm_manager
        if alarm is not None:
            _step("alarm_manager", lambda: alarm.unsubscribe(device))
        command = self._command_manager
        if command is not None:
            _step("command_manager", lambda: command.unregister_device(did))
        data = self._data_manager
        if data is not None:
            _step("data_manager", lambda: data.unsubscribe(device))
        state = self._state_manager
        if state is not None:
            _step("state_manager", lambda: state.unsubscribe(device))
        stats = self._statistics_manager
        if stats is not None:
            _step("statistics_manager", lambda: stats.unsubscribe(device))
        registry = self._config.device_registry
        if registry is not None:
            _step("device_registry", lambda: registry.unregister(did))

    async def unregister(self, device_id: str) -> bool:
        """
        解除單一獨立設備註冊

        級聯順序：先呼叫 ``_cascade_unsubscribe_device``（在 register_lock
        內同步拆事件訂閱與 registry），最後在鎖外以 async 呼叫
        ``device_manager.unregister``（避免 async I/O 持有 thread lock）。

        Args:
            device_id: 要解除註冊的設備 ID

        Returns:
            True 若在 standalone 或 group 中找到設備並已觸發卸載流程；
            False 若 device_id 不在任何已註冊設備中
        """
        with self._register_lock:
            device = self._find_registered_device(device_id)
            if device is None:
                logger.debug("UnifiedDeviceManager.unregister: 找不到設備 {}", device_id)
                return False
            self._cascade_unsubscribe_device(device, log_prefix="UnifiedDeviceManager.unregister")

        try:
            removed = await self._device_manager.unregister(device_id)
        except Exception as e:
            logger.warning("UnifiedDeviceManager.unregister: device_manager 失敗 {} err={}", device_id, e)
            removed = False

        logger.info("UnifiedDeviceManager: 已解除註冊設備 {} (device_manager_removed={})", device_id, removed)
        return True

    async def unregister_group(self, device_ids: Sequence[str]) -> bool:
        """
        解除整個群組註冊

        對稱 ``register_group``：對 group 內每個 device 呼叫
        ``_cascade_unsubscribe_device``，最後呼叫
        ``device_manager.unregister_group``。

        Args:
            device_ids: 群組內所有設備 ID（順序無關，但集合需完全相符）

        Returns:
            True 若找到符合的群組並已觸發卸載流程；False 若找不到符合的群組
        """
        target_set = set(device_ids)
        with self._register_lock:
            target_group = None
            for group in self._device_manager.groups:
                if set(group.device_ids) == target_set:
                    target_group = group
                    break
            if target_group is None:
                logger.debug("UnifiedDeviceManager.unregister_group: 找不到符合的群組 {}", list(device_ids))
                return False
            for device in target_group.devices:
                self._cascade_unsubscribe_device(device, log_prefix="UnifiedDeviceManager.unregister_group")

        try:
            removed = await self._device_manager.unregister_group(device_ids)
        except Exception as e:
            logger.warning("UnifiedDeviceManager.unregister_group: device_manager 失敗 err={}", e)
            removed = False

        logger.info("UnifiedDeviceManager: 已解除註冊群組 {} (device_manager_removed={})", list(device_ids), removed)
        return True

    def _find_registered_device(self, device_id: str) -> DeviceProtocol | None:
        """在 DeviceManager 中尋找指定 device_id 的 device 物件。

        走 ``DeviceManager.all_devices`` public API（standalone + group 合併），
        避免觸碰私有屬性。

        Args:
            device_id: 設備 ID

        Returns:
            DeviceProtocol 物件，若找不到則回 None
        """
        for dev in self._device_manager.all_devices:
            if dev.device_id == device_id:
                return dev
        return None

    # ================ 觀測 ================

    def describe(self) -> UnifiedManagerStatus:
        """回傳目前 manager 的觀測快照。

        此方法為 O(1)~O(n_groups) 的快照讀取，不 await、不做 I/O；
        供外部 GUI / Monitor / Cluster 狀態報告使用。

        Returns:
            ``UnifiedManagerStatus``，欄位定義見該 dataclass docstring。
        """
        devices_count = self._device_manager.standalone_count + sum(len(g.devices) for g in self._device_manager.groups)
        is_leader = self._leader_gate.is_leader if self._leader_gate is not None else None
        alarms_active = getattr(self._alarm_manager, "active_count", None) if self._alarm_manager is not None else None
        return UnifiedManagerStatus(
            devices_count=devices_count,
            running=self.is_running,
            is_leader=is_leader,
            alarms_active_count=alarms_active,
            command_queue_depth=None,
            upload_queue_depth=None,
            state_sync_enabled=self._state_manager is not None,
            statistics_enabled=self._statistics_manager is not None,
        )

    # ================ 生命週期 ================

    async def _on_start(self) -> None:
        """
        啟動管理器

        啟動所有已註冊設備的讀取循環。若注入 leader_gate 且目前非 leader，
        會跳過 ``device_manager.start()``（不連線 / 不讀取 / 不訂閱底層事件），
        避免 follower 節點重複對設備執行 I/O。
        """
        if self._leader_gate is not None and not self._leader_gate.is_leader:
            logger.info("UnifiedDeviceManager: 非 leader 節點，_on_start 跳過 device_manager.start()")
            return
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
    "UnifiedManagerStatus",
]
