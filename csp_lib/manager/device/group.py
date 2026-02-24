# =============== Manager Device - Group ===============
#
# 設備群組（純順序讀取器）
#
# 用於管理需要順序讀取的設備：
#   - DeviceGroup: 設備群組類別
#
# 使用場景：
#   - RTU 通訊：多設備共用 RS485 線路
#   - Shared TCP：多設備共用 TCP Client（如 Gateway）
#   - 任何需要順序讀取的場景
#
# 設計理念：
#   - DeviceGroup 只負責「順序讀取」
#   - 連線/斷線/重連由各 Device 自己管理
#   - 不限制設備是否共用 Client

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger(__name__)


@dataclass
class DeviceGroup:
    """
    設備群組（純順序讀取器）

    依序讀取群組內設備，確保不會同時讀取造成衝突。
    連線/斷線/重連由各 Device 自己管理，DeviceGroup 不介入。

    Attributes:
        devices: 群組內設備列表
        interval: 完整讀取一輪的間隔時間（秒）
        step_interval: 設備間的讀取間隔時間（秒）

    使用範例：
        group = DeviceGroup(
            devices=[device_1, device_2, device_3],
            interval=1.0,
        )
        group.start()
        # ... 運行中 ...
        await group.stop()
    """

    devices: list[AsyncModbusDevice]
    interval: float = 1.0
    step_interval: float = 0.05

    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    # ================ 生命週期 ================

    def start(self) -> None:
        """
        啟動順序讀取循環

        建立背景任務，依序讀取群組內所有設備。
        各設備的連線由 Device 自己管理。
        """
        if self._task is not None and not self._task.done():
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._sequential_loop(),
            name=f"device_group_loop_{id(self)}",
        )
        logger.info(f"設備群組讀取循環已啟動，間隔 {self.interval}s，包含 {len(self.devices)} 個設備")

    async def stop(self) -> None:
        """
        停止順序讀取循環

        取消背景任務並等待其結束。
        """
        self._stop_event.set()

        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("設備群組讀取循環已停止")

    # ================ 私有方法 ================

    async def _sequential_loop(self) -> None:
        """
        順序讀取循環

        依序呼叫每個設備的 read_once()，確保不會同時讀取。
        單一設備的讀取錯誤不會影響其他設備。
        """
        while not self._stop_event.is_set():
            start = time.monotonic()

            for device in self.devices:
                if self._stop_event.is_set():
                    break
                if not device.should_attempt_read:
                    logger.debug(f"跳過無回應設備 {device.device_id}，等待重試間隔")
                    continue
                try:
                    await device.read_once()
                except Exception:
                    # read_once 內部已處理錯誤並發射事件
                    # 這裡捕獲避免影響其他設備
                    pass
                finally:
                    await asyncio.sleep(self.step_interval)

            elapsed = time.monotonic() - start
            sleep_time = max(0, self.interval - elapsed)

            if sleep_time > 0:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=sleep_time,
                    )
                except asyncio.TimeoutError:
                    pass  # 正常超時，繼續下一輪

    # ================ 屬性 ================

    @property
    def is_running(self) -> bool:
        """讀取循環是否運行中"""
        return self._task is not None and not self._task.done()

    @property
    def device_ids(self) -> list[str]:
        """群組內所有設備的 ID"""
        return [d.device_id for d in self.devices]

    def __len__(self) -> int:
        return len(self.devices)

    def __repr__(self) -> str:
        return f"<DeviceGroup devices={self.device_ids} interval={self.interval}s running={self.is_running}>"
