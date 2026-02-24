# =============== Integration - Heartbeat Service ===============
#
# 控制器心跳（看門狗）寫入服務
#
# 定期對設備寫入心跳值，讓設備端確認控制器仍在線。
# 若設備端超時未收到心跳，應進入安全模式（由設備韌體處理）。
#
# 兩種使用模式：
#   1. 明確映射模式：透過 HeartbeatMapping 指定 trait/device_id + point_name
#   2. 能力發現模式：自動找出所有具備 HEARTBEAT 能力的設備，
#      透過 CapabilityBinding 解析各設備的實際心跳點位名稱
#
# 支援 pause / resume，供旁路模式等需要停止控制器輸出的場景使用。

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from csp_lib.core import get_logger
from csp_lib.core.errors import DeviceError
from csp_lib.equipment.device.capability import HEARTBEAT

from .schema import HeartbeatMapping, HeartbeatMode

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice

    from .registry import DeviceRegistry

logger = get_logger("csp_lib.integration.heartbeat")


class HeartbeatService:
    """
    控制器心跳寫入服務

    兩種使用方式：

    **明確映射模式** — 適合所有設備心跳點位名稱相同的場景::

        service = HeartbeatService(registry, mappings=[
            HeartbeatMapping(point_name="heartbeat", trait="pcs"),
        ])

    **能力發現模式** — 適合不同設備使用不同點位名稱的場景::

        service = HeartbeatService(registry, use_capability=True)
        # 自動找出所有具備 HEARTBEAT 能力的設備
        # 各設備透過 CapabilityBinding 解析實際點位名稱

    兩種模式可同時使用（先處理明確映射，再處理能力發現）。
    """

    def __init__(
        self,
        registry: DeviceRegistry,
        mappings: list[HeartbeatMapping] | None = None,
        interval: float = 1.0,
        use_capability: bool = False,
        mode: HeartbeatMode = HeartbeatMode.TOGGLE,
        constant_value: int = 1,
        increment_max: int = 65535,
    ) -> None:
        """
        初始化心跳服務

        Args:
            registry: 設備查詢索引
            mappings: 明確映射列表（可選）
            interval: 心跳寫入間隔（秒）
            use_capability: 是否啟用能力發現模式
            mode: 能力發現模式使用的心跳值模式
            constant_value: CONSTANT 模式的固定值
            increment_max: INCREMENT 模式的最大計數值
        """
        self._registry = registry
        self._mappings = mappings or []
        self._interval = interval
        self._use_capability = use_capability
        self._cap_mode = mode
        self._cap_constant_value = constant_value
        self._cap_increment_max = increment_max

        self._counters: dict[str, int] = {}
        self._paused = False
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def start(self) -> None:
        """啟動心跳寫入迴圈"""
        if self.is_running:
            return
        self._stop_event.clear()
        self._paused = False
        self._task = asyncio.create_task(self._run())
        logger.info("HeartbeatService started.")

    async def stop(self) -> None:
        """停止心跳寫入迴圈"""
        self._stop_event.set()
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HeartbeatService stopped.")

    def pause(self) -> None:
        """暫停心跳寫入（設備端將因超時進入安全模式）"""
        if not self._paused:
            self._paused = True
            logger.info("HeartbeatService paused.")

    def resume(self) -> None:
        """恢復心跳寫入"""
        if self._paused:
            self._paused = False
            logger.info("HeartbeatService resumed.")

    def reset_counters(self) -> None:
        """重置所有心跳計數器"""
        self._counters.clear()

    async def _run(self) -> None:
        """心跳主迴圈"""
        while not self._stop_event.is_set():
            if not self._paused:
                await self._send_heartbeats()

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
                break  # stop_event was set
            except asyncio.TimeoutError:
                pass  # normal interval elapsed

    async def _send_heartbeats(self) -> None:
        """對所有設備寫入心跳值"""
        # 1. 明確映射
        for mapping in self._mappings:
            value = self._next_value_for_mapping(mapping)

            if mapping.device_id is not None:
                device = self._registry.get_device(mapping.device_id)
                if device is not None and device.is_responsive:
                    await self._safe_write(device, mapping.point_name, value)
            elif mapping.trait is not None:
                devices = self._registry.get_responsive_devices_by_trait(mapping.trait)
                for device in devices:
                    await self._safe_write(device, mapping.point_name, value)

        # 2. 能力發現
        if self._use_capability:
            devices = self._registry.get_responsive_devices_with_capability(HEARTBEAT)
            for device in devices:
                point_name = device.resolve_point(HEARTBEAT, "heartbeat")
                value = self._next_value_for_device(device.device_id)
                await self._safe_write(device, point_name, value)

    def _next_value_for_mapping(self, mapping: HeartbeatMapping) -> int:
        """依據 mapping 模式計算下一個心跳值"""
        key = f"mapping:{mapping.device_id or mapping.trait}:{mapping.point_name}"
        return self._compute_next(key, mapping.mode, mapping.constant_value, mapping.increment_max)

    def _next_value_for_device(self, device_id: str) -> int:
        """依據能力發現模式計算下一個心跳值"""
        key = f"cap:{device_id}"
        return self._compute_next(key, self._cap_mode, self._cap_constant_value, self._cap_increment_max)

    def _compute_next(self, key: str, mode: HeartbeatMode, constant_value: int, increment_max: int) -> int:
        """依據模式計算下一個值"""
        if mode == HeartbeatMode.TOGGLE:
            current = self._counters.get(key, 0)
            next_val = 1 - current
            self._counters[key] = next_val
            return next_val

        if mode == HeartbeatMode.INCREMENT:
            current = self._counters.get(key, 0)
            next_val = (current + 1) % (increment_max + 1)
            self._counters[key] = next_val
            return next_val

        # CONSTANT
        return constant_value

    @staticmethod
    async def _safe_write(device: AsyncModbusDevice, point_name: str, value: int) -> None:
        """安全寫入：單一設備失敗不中斷其他設備"""
        try:
            await device.write(point_name, value)
        except DeviceError:
            logger.warning(f"Heartbeat write failed: device='{device.device_id}' point='{point_name}'", exc_info=True)


__all__ = [
    "HeartbeatService",
]
