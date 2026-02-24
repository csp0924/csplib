# =============== Integration - Command Router ===============
#
# Command → 設備寫入路由器
#
# 將 StrategyExecutor 產出的 Command 路由到設備寫入：
#   - device_id 模式：寫入單一設備
#   - trait 模式：廣播寫入所有 responsive 設備
#   - 簽名 async (Command) -> None 完全符合 StrategyExecutor 的 on_command

from __future__ import annotations

from typing import TYPE_CHECKING

from csp_lib.core import get_logger
from csp_lib.core.errors import DeviceError

from .registry import DeviceRegistry
from .schema import CommandMapping

if TYPE_CHECKING:
    from csp_lib.controller.core import Command
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger("csp_lib.integration.command_router")


class CommandRouter:
    """
    Command → 設備寫入路由器

    將策略執行結果 (Command) 的各欄位，透過 CommandMapping 路由到設備寫入操作。

    設計為 StrategyExecutor 的 ``on_command`` 回呼。
    ``route()`` 的簽名 ``async (Command) -> None`` 完全符合該介面。

    錯誤處理：
        - transform 例外 → log error + 跳過該映射
        - 單一設備寫入失敗 → log warning + 繼續寫入其他設備
        - 設備不存在或離線 → log warning + 跳過
    """

    def __init__(self, registry: DeviceRegistry, mappings: list[CommandMapping]) -> None:
        """
        初始化路由器

        Args:
            registry: 設備查詢索引
            mappings: Command 欄位 → 設備寫入的映射列表
        """
        self._registry = registry
        self._mappings = mappings

    async def route(self, command: Command) -> None:
        """
        路由 Command 到設備寫入

        遍歷所有 CommandMapping，取得 Command 對應欄位值後寫入設備。

        Args:
            command: 策略執行輸出的命令
        """
        for mapping in self._mappings:
            value = getattr(command, mapping.command_field, None)
            if value is None:
                continue

            # 套用轉換函式（例如均分功率）
            if mapping.transform is not None:
                try:
                    value = mapping.transform(value)
                except Exception:
                    logger.error(f"Transform failed for command field '{mapping.command_field}', skipping.")
                    continue

            if mapping.device_id is not None:
                await self._write_single(mapping.device_id, mapping.point_name, value)
            else:
                await self._write_trait_broadcast(mapping.trait, mapping.point_name, value)  # type: ignore[arg-type]

    async def _write_single(self, device_id: str, point_name: str, value: object) -> None:
        """device_id 模式：寫入單一設備"""
        device = self._registry.get_device(device_id)
        if device is None:
            logger.warning(f"Device '{device_id}' not found in registry, skipping write.")
            return
        if device.is_protected:
            logger.warning(f"Device '{device_id}' is protected (alarm), skipping write.")
            return
        if not device.is_responsive:
            logger.warning(f"Device '{device_id}' is not responsive, skipping write.")
            return
        await self._safe_write(device, point_name, value)

    async def _write_trait_broadcast(self, trait: str, point_name: str, value: object) -> None:
        """trait 模式：廣播寫入所有 responsive 且非 protected 設備"""
        devices = self._registry.get_responsive_devices_by_trait(trait)
        if not devices:
            logger.warning(f"No responsive devices found for trait '{trait}'.")
            return
        for device in devices:
            if device.is_protected:
                logger.warning(f"Device '{device.device_id}' is protected (alarm), skipping broadcast write.")
                continue
            await self._safe_write(device, point_name, value)

    @staticmethod
    async def _safe_write(device: AsyncModbusDevice, point_name: str, value: object) -> None:
        """安全寫入：單一設備失敗不中斷其他設備"""
        try:
            await device.write(point_name, value)
        except DeviceError:
            logger.warning(f"Write failed for device '{device.device_id}' point '{point_name}'.", exc_info=True)
