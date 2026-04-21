# =============== Integration - Command Router ===============
#
# Command → 設備寫入路由器
#
# 將 StrategyExecutor 產出的 Command 路由到設備寫入：
#   - device_id 模式：寫入單一設備
#   - trait 模式：廣播寫入所有 responsive 設備
#   - 簽名 async (Command) -> None 完全符合 StrategyExecutor 的 on_command

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from csp_lib.controller.core import NO_CHANGE, is_no_change
from csp_lib.core import get_logger
from csp_lib.core.errors import DeviceError

from .registry import DeviceRegistry
from .schema import CapabilityCommandMapping, CommandMapping

if TYPE_CHECKING:
    from csp_lib.controller.core import Command
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger(__name__)


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

    def __init__(
        self,
        registry: DeviceRegistry,
        mappings: list[CommandMapping],
        capability_mappings: list[CapabilityCommandMapping] | None = None,
    ) -> None:
        """
        初始化路由器

        Args:
            registry: 設備查詢索引
            mappings: Command 欄位 → 設備寫入的映射列表
            capability_mappings: capability-driven command 映射列表（可選）
        """
        self._registry = registry
        self._mappings = mappings
        self._capability_mappings = capability_mappings or []
        # Desired-state table consumed by CommandRefreshService reconciler.
        # NO_CHANGE writes skip this table so values stay business-meaningful.
        self._last_written: dict[str, dict[str, Any]] = {}
        # 設備解除註冊時同步 prune desired-state，避免污染 get_tracked_device_ids()
        # 進而讓 reconciler / refresh service 持續對已移除設備發無效寫入。
        self._registry.on_unregister(self._on_device_unregistered)

    def _on_device_unregistered(self, device_id: str) -> None:
        """DeviceRegistry unregister observer：prune 該 device 的 desired-state。"""
        self._last_written.pop(device_id, None)

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
            # NO_CHANGE：跳過此軸寫入，保留設備當前值
            if is_no_change(value):
                logger.trace(
                    f"Command field '{mapping.command_field}' is NO_CHANGE, skipping write to "
                    f"{mapping.device_id or f'trait:{mapping.trait}'}.{mapping.point_name}"
                )
                continue

            # 套用轉換函式（例如均分功率）
            if mapping.transform is not None:
                try:
                    value = mapping.transform(value)
                except Exception:
                    logger.error(f"Transform failed for command field '{mapping.command_field}', skipping.")
                    continue

            if mapping.device_id is not None:
                await self.try_write_single(mapping.device_id, mapping.point_name, value)
            else:
                await self._write_trait_broadcast(mapping.trait, mapping.point_name, value)  # type: ignore[arg-type]

        for cap_mapping in self._capability_mappings:
            value = getattr(command, cap_mapping.command_field, None)
            if value is None:
                continue
            # NO_CHANGE：跳過此軸寫入
            if is_no_change(value):
                logger.trace(
                    f"Capability command field '{cap_mapping.command_field}' is NO_CHANGE, skipping capability write"
                )
                continue

            if cap_mapping.transform is not None:
                try:
                    value = cap_mapping.transform(value)
                except Exception:
                    logger.error(
                        f"Transform failed for capability command field '{cap_mapping.command_field}', skipping."
                    )
                    continue

            if cap_mapping.device_id is not None:
                await self._write_capability_single(cap_mapping, value)
            elif cap_mapping.trait is not None:
                await self._write_capability_trait(cap_mapping, value)
            else:
                await self._write_capability_auto(cap_mapping, value)

    async def try_write_single(self, device_id: str, point_name: str, value: object) -> bool:
        """device_id 模式：寫入單一設備，回報成功/失敗

        成功後會更新 ``self._last_written`` 的 desired-state 表，供
        ``CommandRefreshService`` 週期 reconcile 使用。

        Args:
            device_id: 目標設備 ID。
            point_name: 寫入點位名稱。
            value: 寫入值（非 NO_CHANGE）。

        Returns:
            ``True`` 若寫入成功；``False`` 若 device 不存在 / protected /
            unresponsive / 寫入拋 ``DeviceError`` / value 為 NO_CHANGE。
        """
        # 防呆：NO_CHANGE sentinel 不可被當 desired-state 寫入 / 紀錄，
        # 否則 CommandRefreshService 會週期性將 sentinel 重送給設備。
        if value is NO_CHANGE:
            return False
        device = self._registry.get_device(device_id)
        if device is None:
            logger.warning(f"Device '{device_id}' not found in registry, skipping write.")
            return False
        if device.is_protected:
            logger.warning(f"Device '{device_id}' is protected (alarm), skipping write.")
            return False
        if not device.is_responsive:
            logger.warning(f"Device '{device_id}' is not responsive, skipping write.")
            return False
        if await self._safe_write(device, point_name, value):
            self._record_written(device_id, point_name, value)
            return True
        return False

    def _record_written(self, device_id: str, point_name: str, value: object) -> None:
        """紀錄成功寫入到 ``_last_written`` 表（CommandRefreshService 的 desired state）"""
        self._last_written.setdefault(device_id, {})[point_name] = value

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
            if await self._safe_write(device, point_name, value):
                self._record_written(device.device_id, point_name, value)

    async def _write_capability_single(self, mapping: CapabilityCommandMapping, value: object) -> None:
        """capability 單一設備寫入"""
        device = self._registry.get_device(mapping.device_id)  # type: ignore[arg-type]
        if device is None:
            logger.warning(f"Device '{mapping.device_id}' not found in registry, skipping capability write.")
            return
        if device.is_protected:
            logger.warning(f"Device '{mapping.device_id}' is protected (alarm), skipping capability write.")
            return
        if not device.is_responsive:
            logger.warning(f"Device '{mapping.device_id}' is not responsive, skipping capability write.")
            return
        if not device.has_capability(mapping.capability):
            logger.warning(
                f"Device '{mapping.device_id}' lacks capability '{mapping.capability.name}', skipping write."
            )
            return
        point_name = device.resolve_point(mapping.capability, mapping.slot)
        if await self._safe_write(device, point_name, value):
            self._record_written(device.device_id, point_name, value)

    async def _write_capability_trait(self, mapping: CapabilityCommandMapping, value: object) -> None:
        """capability trait 模式：廣播寫入"""
        devices = self._registry.get_responsive_devices_by_trait(mapping.trait)  # type: ignore[arg-type]
        if not devices:
            logger.warning(f"No responsive devices found for trait '{mapping.trait}'.")
            return
        for device in devices:
            if device.is_protected:
                logger.warning(
                    f"Device '{device.device_id}' is protected (alarm), skipping capability broadcast write."
                )
                continue
            if not device.has_capability(mapping.capability):
                continue
            point_name = device.resolve_point(mapping.capability, mapping.slot)
            if await self._safe_write(device, point_name, value):
                self._record_written(device.device_id, point_name, value)

    async def _write_capability_auto(self, mapping: CapabilityCommandMapping, value: object) -> None:
        """capability 自動發現模式：寫入所有具備該 capability 的 responsive 設備"""
        devices = self._registry.get_responsive_devices_with_capability(mapping.capability)
        if not devices:
            logger.warning(f"No responsive devices with capability '{mapping.capability.name}' found.")
            return
        for device in devices:
            if device.is_protected:
                logger.warning(f"Device '{device.device_id}' is protected (alarm), skipping capability auto write.")
                continue
            point_name = device.resolve_point(mapping.capability, mapping.slot)
            if await self._safe_write(device, point_name, value):
                self._record_written(device.device_id, point_name, value)

    async def route_per_device(self, command: Command, per_device_commands: dict[str, Command]) -> None:
        """
        路由 Command 到設備寫入（per-device 分配模式）

        明確映射使用系統級 command（同 route()），
        capability 映射使用 per_device_commands 中各設備的個別 Command。

        Args:
            command: 系統級命令（用於明確映射）
            per_device_commands: device_id → Command 的映射（由 PowerDistributor 產生）
        """
        # 1. 明確映射：同 route() 邏輯
        for mapping in self._mappings:
            value = getattr(command, mapping.command_field, None)
            if value is None:
                continue
            # NO_CHANGE：跳過此軸寫入
            if is_no_change(value):
                logger.trace(
                    f"Command field '{mapping.command_field}' is NO_CHANGE, skipping write to "
                    f"{mapping.device_id or f'trait:{mapping.trait}'}.{mapping.point_name}"
                )
                continue
            if mapping.transform is not None:
                try:
                    value = mapping.transform(value)
                except Exception:
                    logger.error(f"Transform failed for command field '{mapping.command_field}', skipping.")
                    continue
            if mapping.device_id is not None:
                await self.try_write_single(mapping.device_id, mapping.point_name, value)
            else:
                await self._write_trait_broadcast(mapping.trait, mapping.point_name, value)  # type: ignore[arg-type]

        # 2. Capability 映射：per-device 分配
        for cap_mapping in self._capability_mappings:
            targets = self._resolve_capability_targets(cap_mapping)
            for device in targets:
                dev_cmd = per_device_commands.get(device.device_id)
                if dev_cmd is None:
                    continue
                value = getattr(dev_cmd, cap_mapping.command_field, None)
                if value is None:
                    continue
                # per-device command 同樣過濾 NO_CHANGE
                if is_no_change(value):
                    logger.trace(
                        f"Per-device capability field '{cap_mapping.command_field}' is NO_CHANGE "
                        f"for device '{device.device_id}', skipping"
                    )
                    continue
                await self._apply_transform_and_write(device, cap_mapping, value)

    def _resolve_capability_targets(self, mapping: CapabilityCommandMapping) -> list[AsyncModbusDevice]:
        """解析 capability mapping 的目標設備列表（已過濾 responsive + non-protected + has_capability）"""
        if mapping.device_id is not None:
            device = self._registry.get_device(mapping.device_id)  # type: ignore[arg-type]
            if (
                device is not None
                and device.is_responsive
                and not device.is_protected
                and device.has_capability(mapping.capability)
            ):
                return [device]
            return []
        if mapping.trait is not None:
            devices = self._registry.get_responsive_devices_by_trait(mapping.trait)  # type: ignore[arg-type]
            return [d for d in devices if not d.is_protected and d.has_capability(mapping.capability)]
        devices = self._registry.get_responsive_devices_with_capability(mapping.capability)
        return [d for d in devices if not d.is_protected]

    async def _apply_transform_and_write(
        self, device: AsyncModbusDevice, mapping: CapabilityCommandMapping, value: object
    ) -> None:
        """套用 transform 後寫入 capability 解析的點位"""
        if mapping.transform is not None:
            try:
                value = mapping.transform(value)  # type: ignore[arg-type]
            except Exception:
                logger.error(f"Transform failed for capability command field '{mapping.command_field}', skipping.")
                return
        point_name = device.resolve_point(mapping.capability, mapping.slot)
        if await self._safe_write(device, point_name, value):
            self._record_written(device.device_id, point_name, value)

    @staticmethod
    async def _safe_write(device: AsyncModbusDevice, point_name: str, value: object) -> bool:
        """安全寫入：單一設備失敗不中斷其他設備

        Returns:
            ``True`` 代表寫入成功；``False`` 代表 ``DeviceError`` 已吞掉（僅 log warning）。
        """
        try:
            await device.write(point_name, value)
            return True
        except DeviceError:
            logger.opt(exception=True).warning(f"Write failed for device '{device.device_id}' point '{point_name}'.")
            return False

    # ---- Desired-state 查詢介面（供 CommandRefreshService 使用） ----

    def get_last_written(self, device_id: str) -> dict[str, Any]:
        """回傳指定設備最近一次成功寫入的 ``{point_name: value}`` 快照

        回傳的是 shallow copy，調用方修改不影響 router 內部狀態。
        若設備尚未被成功寫入過任何點位，回傳空 dict。

        Args:
            device_id: 查詢對象的設備 ID。

        Returns:
            ``{point_name: value}`` 的淺拷貝。
        """
        return dict(self._last_written.get(device_id, {}))

    def get_tracked_device_ids(self) -> frozenset[str]:
        """回傳目前有 desired-state 紀錄的所有設備 ID（frozenset）"""
        return frozenset(self._last_written.keys())
