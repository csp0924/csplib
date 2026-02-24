# =============== Manager Device - Manager ===============
#
# 設備讀取管理器
#
# 統一管理獨立設備與群組設備的生命週期：
#   - DeviceManager: 設備管理器類別
#
# 支援模式：
#   - 獨立模式：每個設備自己跑 read_loop（適用獨立 TCP）
#   - 群組模式：Manager 順序呼叫 read_once（適用 RTU/Shared TCP）

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.core.errors import DeviceConnectionError

from .group import DeviceGroup

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger(__name__)


class DeviceManager(AsyncLifecycleMixin):
    """
    設備讀取管理器

    統一管理獨立設備與群組設備的生命週期，提供一致的 start/stop 介面。

    支援兩種模式：
        1. 獨立模式 (register): 設備自己跑 read_loop，適用獨立 TCP 連線
        2. 群組模式 (register_group): Manager 順序呼叫 read_once，適用 RTU/Shared TCP

    Attributes:
        standalone_count: 獨立設備數量
        group_count: 設備群組數量

    使用範例：
        manager = DeviceManager()

        # 獨立 TCP 設備
        manager.register(tcp_device_1)
        manager.register(tcp_device_2)

        # RTU 群組（共用 Client）
        manager.register_group([rtu_1, rtu_2], interval=1.0)
        manager.register_group([rtu_3, rtu_4, rtu_5], interval=2.0)

        # 使用 context manager
        async with manager:
            await asyncio.sleep(60)  # 運行 60 秒

        # 或手動管理
        await manager.start()
        try:
            await asyncio.sleep(60)
        finally:
            await manager.stop()
    """

    def __init__(self) -> None:
        """初始化設備管理器"""
        self._standalone: list[AsyncModbusDevice] = []
        self._groups: list[DeviceGroup] = []
        self._running = False

    # ================ 註冊 ================

    def register(self, device: AsyncModbusDevice) -> None:
        """
        註冊獨立設備

        獨立設備將使用自己的 read_loop 進行讀取。

        Args:
            device: 要註冊的設備
        """
        self._standalone.append(device)
        logger.debug(f"已註冊獨立設備: {device.device_id}")

    def register_group(
        self,
        devices: Sequence[AsyncModbusDevice],
        interval: float = 1.0,
    ) -> None:
        """
        註冊設備群組

        群組內設備將由 Manager 順序呼叫 read_once() 進行讀取。

        Args:
            devices: 設備列表
            interval: 完整讀取一輪的間隔時間（秒）
        """
        group = DeviceGroup(devices=list(devices), interval=interval)
        self._groups.append(group)
        logger.debug(f"已註冊設備群組: {group.device_ids}")

    # ================ 生命週期 ================

    async def _on_start(self) -> None:
        """
        啟動所有設備

        獨立設備將各自啟動 read_loop，群組設備將啟動順序讀取循環。
        連線失敗不會阻止啟動，會在背景自動重試。
        """
        if self._running:
            return

        self._running = True

        # 啟動獨立設備（單一設備連線失敗不影響其他設備）
        for device in self._standalone:
            try:
                await device.connect()
            except DeviceConnectionError as e:
                logger.warning(f"設備 {device.device_id} 連線失敗，將在背景重試: {e}")
            # 無論連線成功與否都啟動 read_loop（會在背景自動重連）
            await device.start()

        # 啟動群組設備：先連線各設備，再啟動順序讀取
        for group in self._groups:
            for device in group.devices:
                try:
                    await device.connect()
                except DeviceConnectionError as e:
                    logger.warning(f"設備 {device.device_id} 連線失敗，將在背景重試: {e}")
                await device._emitter.start()
            group.start()

        logger.info(f"DeviceManager 已啟動: {len(self._standalone)} 個獨立設備, {len(self._groups)} 個群組")

    async def _on_stop(self) -> None:
        """
        停止所有設備

        停止所有讀取循環並斷開連線。
        """
        if not self._running:
            return

        self._running = False

        # 停止獨立設備
        for device in self._standalone:
            await device.stop()
            await device.disconnect()

        # 停止群組設備：先停止順序讀取，再斷線各設備
        for group in self._groups:
            await group.stop()
            for device in group.devices:
                await device._emitter.stop()
                try:
                    await device.disconnect()
                except DeviceConnectionError as e:
                    logger.debug(f"設備 {device.device_id} 斷線失敗（已忽略）: {e}")

        logger.info("DeviceManager 已停止")

    # ================ 屬性 ================

    @property
    def is_running(self) -> bool:
        """管理器是否運行中"""
        return self._running

    @property
    def standalone_count(self) -> int:
        """獨立設備數量"""
        return len(self._standalone)

    @property
    def group_count(self) -> int:
        """設備群組數量"""
        return len(self._groups)

    @property
    def all_devices(self) -> list[AsyncModbusDevice]:
        """
        取得所有設備

        返回獨立設備與群組設備的合併列表。

        Returns:
            所有設備的列表
        """
        devices = list(self._standalone)
        for group in self._groups:
            devices.extend(group.devices)
        return devices

    @property
    def groups(self) -> list[DeviceGroup]:
        """取得所有設備群組"""
        return list(self._groups)

    def __repr__(self) -> str:
        return f"<DeviceManager standalone={self.standalone_count} groups={self.group_count} running={self.is_running}>"
