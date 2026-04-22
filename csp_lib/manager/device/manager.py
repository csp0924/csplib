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

from typing import TYPE_CHECKING, Sequence, cast

from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.core.errors import DeviceConnectionError

from .group import DeviceGroup

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice
    from csp_lib.equipment.device.protocol import DeviceProtocol

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
        # 型別使用 DeviceProtocol 以接受任何實作該介面的設備（AsyncModbusDevice / AsyncCANDevice 等）。
        # 內部 start/stop 仍呼叫 connect/disconnect/read_loop 等 AsyncModbusDevice 具體方法，
        # 藉由 cast 壓 mypy；未來 DeviceProtocol 補齊 lifecycle 後即可移除 cast（追蹤 B-P2）。
        self._standalone: list[DeviceProtocol] = []
        self._groups: list[DeviceGroup] = []
        self._registered_ids: set[str] = set()
        self._running = False

    # ================ 註冊 ================

    def register(self, device: DeviceProtocol) -> None:
        """
        註冊獨立設備

        獨立設備將使用自己的 read_loop 進行讀取。

        Args:
            device: 要註冊的設備（任何實作 DeviceProtocol 的裝置）

        Raises:
            ValueError: 設備 ID 已被註冊
        """
        if device.device_id in self._registered_ids:
            raise ValueError(f"Device '{device.device_id}' already registered")
        self._standalone.append(device)
        self._registered_ids.add(device.device_id)
        logger.debug(f"已註冊獨立設備: {device.device_id}")

    def register_group(
        self,
        devices: Sequence[DeviceProtocol],
        interval: float = 1.0,
    ) -> None:
        """
        註冊設備群組

        群組內設備將由 Manager 順序呼叫 read_once() 進行讀取。

        Args:
            devices: 設備列表
            interval: 完整讀取一輪的間隔時間（秒）

        Raises:
            ValueError: 設備 ID 已被註冊
        """
        new_ids: set[str] = set()
        for device in devices:
            if device.device_id in self._registered_ids or device.device_id in new_ids:
                raise ValueError(f"Device '{device.device_id}' already registered")
            new_ids.add(device.device_id)
        # DeviceGroup.devices 目前仍以 AsyncModbusDevice 具體型別保存（需呼叫 read_once / _emitter）。
        # 這裡透過 cast 串接；未來 DeviceProtocol 補齊相關欄位後可一起鬆綁（B-P2）。
        group = DeviceGroup(devices=[cast("AsyncModbusDevice", d) for d in devices], interval=interval)
        self._groups.append(group)
        self._registered_ids.update(new_ids)
        logger.debug(f"已註冊設備群組: {group.device_ids}")

    # ================ 解除註冊 ================

    async def unregister(self, device_id: str) -> bool:
        """
        解除單一獨立設備註冊

        若設備正在執行，會先 stop + disconnect（best-effort，失敗僅 warn）。
        若 device_id 屬於群組設備，不處理（請用 ``unregister_group``）。

        Args:
            device_id: 要解除註冊的設備 ID

        Returns:
            True 若成功解除，False 若設備不存在於 standalone 列表
        """
        target: DeviceProtocol | None = None
        for dev in self._standalone:
            if dev.device_id == device_id:
                target = dev
                break
        if target is None:
            logger.debug("DeviceManager.unregister: 設備 {} 不在 standalone 列表", device_id)
            return False

        if self._running:
            concrete = cast("AsyncModbusDevice", target)
            # stop/disconnect best-effort：抓 Exception 不抓 BaseException（避免吃掉 CancelledError）
            try:
                await concrete.stop()
            except Exception as e:
                logger.warning("DeviceManager.unregister: stop 失敗 device={} err={}", device_id, e)
            try:
                await concrete.disconnect()
            except Exception as e:
                logger.warning("DeviceManager.unregister: disconnect 失敗 device={} err={}", device_id, e)

        self._standalone.remove(target)
        self._registered_ids.discard(device_id)
        logger.info("DeviceManager: 已解除註冊設備 {}", device_id)
        return True

    async def unregister_group(self, device_ids: Sequence[str]) -> bool:
        """
        解除整個群組註冊

        以群組方式尋找完全匹配 ``device_ids`` 的 DeviceGroup（順序無關）。
        若正在執行，會先 group.stop()，再對每個設備 disconnect（best-effort）。
        中途 disconnect 失敗以 warn 記錄不中斷。

        Args:
            device_ids: 群組內所有設備 ID（必須與註冊時提供的完全相同）

        Returns:
            True 若成功解除，False 若找不到符合的群組
        """
        import asyncio

        target_ids = set(device_ids)
        target_group: DeviceGroup | None = None
        for group in self._groups:
            if set(group.device_ids) == target_ids:
                target_group = group
                break
        if target_group is None:
            logger.debug("DeviceManager.unregister_group: 找不到符合的群組 {}", list(device_ids))
            return False

        if self._running:
            try:
                await target_group.stop()
            except Exception as e:
                logger.warning("DeviceManager.unregister_group: group.stop 失敗 err={}", e)

            # 逐台 disconnect，以 gather + return_exceptions 收斂所有錯誤（CancelledError 向上拋）
            async def _disconnect_one(dev: "AsyncModbusDevice") -> None:
                try:
                    await dev.disconnect()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(
                        "DeviceManager.unregister_group: disconnect 失敗 device={} err={}",
                        dev.device_id,
                        e,
                    )

            await asyncio.gather(
                *(_disconnect_one(d) for d in target_group.devices),
                return_exceptions=False,
            )

        self._groups.remove(target_group)
        for did in target_group.device_ids:
            self._registered_ids.discard(did)
        logger.info("DeviceManager: 已解除註冊設備群組 {}", target_group.device_ids)
        return True

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
            # 目前 lifecycle 方法（connect / start / _emitter）尚未納入 DeviceProtocol，
            # 暫以 cast 壓 mypy；後續補齊 Protocol 後移除（追蹤 B-P2）。
            concrete = cast("AsyncModbusDevice", device)
            try:
                await concrete.connect()
            except DeviceConnectionError as e:
                logger.warning(f"設備 {device.device_id} 連線失敗，將在背景重試: {e}")
            # 無論連線成功與否都啟動 read_loop（會在背景自動重連）
            await concrete.start()

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
            concrete = cast("AsyncModbusDevice", device)
            await concrete.stop()
            await concrete.disconnect()

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
    def all_devices(self) -> list[DeviceProtocol]:
        """
        取得所有設備

        返回獨立設備與群組設備的合併列表。

        Returns:
            所有設備的列表（DeviceProtocol 視角）
        """
        devices: list[DeviceProtocol] = list(self._standalone)
        for group in self._groups:
            devices.extend(group.devices)
        return devices

    @property
    def groups(self) -> list[DeviceGroup]:
        """取得所有設備群組"""
        return list(self._groups)

    def __repr__(self) -> str:
        return f"<DeviceManager standalone={self.standalone_count} groups={self.group_count} running={self.is_running}>"
