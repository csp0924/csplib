# =============== Manager Device - Group ===============
#
# 設備群組
#
# 用於管理共用 Client 的設備順序讀取：
#   - DeviceGroup: 設備群組類別
#
# 使用場景：
#   - RTU 通訊：多設備共用 RS485 線路
#   - Shared TCP：多設備共用 TCP Client（如 Gateway）

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
    設備群組（共用 Client，順序讀取）

    用於管理共用同一 Client 的多個設備，確保順序讀取避免通訊衝突。
    適用於 RTU、Shared TCP 等場景。

    Attributes:
        devices: 群組內設備列表（必須共用同一 Client）
        interval: 完整讀取一輪的間隔時間（秒）
        step_interval: 設備間的讀取間隔時間（秒）

    使用範例：
        group = DeviceGroup(
            devices=[device_1, device_2, device_3],
            interval=1.0,
        )
        await group.connect()
        group.start()
        # ... 運行中 ...
        await group.stop()
        await group.disconnect()

    Raises:
        ValueError: 群組內設備未共用同一 Client
    """

    devices: list[AsyncModbusDevice]
    interval: float = 1.0
    step_interval: float = 0.05

    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    def __post_init__(self) -> None:
        """初始化後驗證"""
        self._validate_same_client()

    def _validate_same_client(self) -> None:
        """
        驗證群組內設備是否共用同一 Client

        Raises:
            ValueError: 發現不同 Client
        """
        if len(self.devices) < 2:
            return

        first_client = self.devices[0]._client
        for device in self.devices[1:]:
            if device._client is not first_client:
                raise ValueError(
                    f"群組內設備必須共用同一 Client: "
                    f"{self.devices[0].device_id} 與 {device.device_id} 使用不同 Client"
                )

    # ================ 生命週期 ================

    async def connect(self) -> None:
        """
        連線群組

        僅連接一次 Client（因為共用），並為每個設備啟動事件處理器。
        """
        if not self.devices:
            return

        # 連接共用 Client
        await self.devices[0]._client.connect()

        # 啟動各設備的事件處理器
        for device in self.devices:
            await device._emitter.start()
            device._client_connected = True
            device._device_responsive = True
            device._consecutive_failures = 0

        logger.info(f"設備群組已連線，包含 {len(self.devices)} 個設備")

    async def disconnect(self) -> None:
        """
        斷線群組

        停止各設備的事件處理器，並斷開共用 Client。
        """
        if not self.devices:
            return

        # 停止各設備的事件處理器
        for device in self.devices:
            device._client_connected = False
            device._device_responsive = False
            await device._emitter.stop()

        # 斷開共用 Client
        await self.devices[0]._client.disconnect()

        logger.info(f"設備群組已斷線，包含 {len(self.devices)} 個設備")

    def start(self) -> None:
        """
        啟動順序讀取循環

        建立背景任務，依序讀取群組內所有設備。
        """
        if self._task is not None and not self._task.done():
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._sequential_loop(),
            name=f"device_group_loop_{id(self)}",
        )
        logger.info(f"設備群組讀取循環已啟動，間隔 {self.interval}s")

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

        依序呼叫每個設備的 read_once()，確保不會同時使用共用 Client。
        單一設備的讀取錯誤不會影響其他設備。
        """
        while not self._stop_event.is_set():
            start = time.monotonic()

            for device in self.devices:
                if self._stop_event.is_set():
                    break
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
