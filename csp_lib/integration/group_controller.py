# =============== Integration - Group Controller ===============
#
# 多群組控制器管理
#
# 將多台設備分成獨立群組，每組擁有獨立的 SystemController：
#   - GroupDefinition: 群組定義（ID、設備、配置）
#   - GroupControllerManager: 管理多個 SystemController 實例
#
# 架構：
#   Master DeviceRegistry
#       ↓ (per group)
#   Sub-DeviceRegistry → SystemController
#       ↓
#   獨立的 ModeManager / ProtectionGuard / Executor

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from csp_lib.core import AsyncLifecycleMixin, get_logger
from csp_lib.core.health import HealthReport, HealthStatus

from .registry import DeviceRegistry
from .system_controller import SystemController, SystemControllerConfig

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy

logger = get_logger("csp_lib.integration.group_controller")


@dataclass(frozen=True)
class GroupDefinition:
    """
    群組定義

    Attributes:
        group_id: 群組唯一識別碼
        device_ids: 群組內的設備 ID 列表
        config: 該群組的 SystemController 配置
    """

    group_id: str
    device_ids: list[str]
    config: SystemControllerConfig


class GroupControllerManager(AsyncLifecycleMixin):
    """
    多群組控制器管理器

    為每個群組建立獨立的 SystemController，各群組擁有獨立的：
    - Sub-DeviceRegistry（僅包含該群組設備）
    - ModeManager（獨立模式管理）
    - ProtectionGuard（獨立保護鏈）
    - StrategyExecutor（獨立策略執行）

    使用範例::

        manager = GroupControllerManager(
            registry=master_registry,
            groups=[
                GroupDefinition("group1", ["pcs_1", "bess_1"], config1),
                GroupDefinition("group2", ["pcs_2", "bess_2"], config2),
            ],
        )
        manager.register_mode("group1", "pq", pq_strategy, ModePriority.MANUAL)
        await manager.set_base_mode("group1", "pq")
        async with manager:
            await asyncio.Event().wait()
    """

    def __init__(self, registry: DeviceRegistry, groups: list[GroupDefinition]) -> None:
        self._registry = registry
        self._controllers: dict[str, SystemController] = {}

        # Validation
        if not groups:
            raise ValueError("At least one group must be provided.")

        group_ids = [g.group_id for g in groups]
        if len(group_ids) != len(set(group_ids)):
            seen: set[str] = set()
            for gid in group_ids:
                if gid in seen:
                    raise ValueError(f"Duplicate group_id: '{gid}'.")
                seen.add(gid)

        all_device_ids: dict[str, str] = {}  # device_id → group_id
        for group in groups:
            if not group.device_ids:
                raise ValueError(f"Group '{group.group_id}' has no devices.")
            for did in group.device_ids:
                if did not in registry:
                    raise ValueError(f"Device '{did}' in group '{group.group_id}' is not registered in the registry.")
                if did in all_device_ids:
                    raise ValueError(
                        f"Device '{did}' is assigned to both "
                        f"group '{all_device_ids[did]}' and group '{group.group_id}'."
                    )
                all_device_ids[did] = group.group_id

        # Build per-group sub-registries and controllers
        for group in groups:
            sub_registry = self._build_sub_registry(registry, group.device_ids)
            controller = SystemController(sub_registry, group.config)
            self._controllers[group.group_id] = controller

    @staticmethod
    def _build_sub_registry(registry: DeviceRegistry, device_ids: list[str]) -> DeviceRegistry:
        """建立僅包含指定設備的子 Registry，保留 traits"""
        sub = DeviceRegistry()
        for did in device_ids:
            device = registry.get_device(did)
            if device is None:
                raise ValueError(f"Device '{did}' not found in registry.")
            traits = registry.get_traits(did)
            sub.register(device, list(traits))
        return sub

    # ---- 模式管理（委派至各群組 SystemController）----

    def _get_controller(self, group_id: str) -> SystemController:
        """取得群組控制器，未知群組拋出 KeyError"""
        if group_id not in self._controllers:
            raise KeyError(f"Unknown group_id: '{group_id}'.")
        return self._controllers[group_id]

    def register_mode(self, group_id: str, name: str, strategy: Strategy, priority: int, description: str = "") -> None:
        """為指定群組註冊模式"""
        self._get_controller(group_id).register_mode(name, strategy, priority, description)

    async def set_base_mode(self, group_id: str, name: str | None) -> None:
        """設定指定群組的基礎模式"""
        await self._get_controller(group_id).set_base_mode(name)

    async def add_base_mode(self, group_id: str, name: str) -> None:
        """為指定群組新增基礎模式"""
        await self._get_controller(group_id).add_base_mode(name)

    async def remove_base_mode(self, group_id: str, name: str) -> None:
        """移除指定群組的基礎模式"""
        await self._get_controller(group_id).remove_base_mode(name)

    async def push_override(self, group_id: str, name: str) -> None:
        """為指定群組推入 override 模式"""
        await self._get_controller(group_id).push_override(name)

    async def pop_override(self, group_id: str, name: str) -> None:
        """移除指定群組的 override 模式"""
        await self._get_controller(group_id).pop_override(name)

    def trigger(self, group_id: str) -> None:
        """觸發指定群組的策略執行"""
        self._get_controller(group_id).trigger()

    def trigger_all(self) -> None:
        """觸發所有群組的策略執行"""
        for controller in self._controllers.values():
            controller.trigger()

    # ---- 生命週期 ----

    async def _on_start(self) -> None:
        """啟動所有群組控制器"""
        await asyncio.gather(*(ctrl.start() for ctrl in self._controllers.values()))
        logger.info(f"GroupControllerManager started with {len(self._controllers)} groups.")

    async def _on_stop(self) -> None:
        """停止所有群組控制器"""
        await asyncio.gather(*(ctrl.stop() for ctrl in self._controllers.values()))
        logger.info("GroupControllerManager stopped.")

    # ---- 查詢屬性 ----

    def get_controller(self, group_id: str) -> SystemController:
        """取得指定群組的 SystemController"""
        return self._get_controller(group_id)

    @property
    def group_ids(self) -> list[str]:
        """所有群組 ID（排序）"""
        return sorted(self._controllers.keys())

    @property
    def controllers(self) -> dict[str, SystemController]:
        """所有群組控制器（副本）"""
        return dict(self._controllers)

    @property
    def is_running(self) -> bool:
        """是否有任何控制器正在執行"""
        return any(ctrl.is_running for ctrl in self._controllers.values())

    def effective_mode_name(self, group_id: str) -> str | None:
        """取得指定群組當前生效的模式名稱"""
        return self._get_controller(group_id).effective_mode_name

    def health(self) -> HealthReport:
        """取得聚合健康報告（含各群組子報告）"""
        children = [ctrl.health() for ctrl in self._controllers.values()]
        if not children:
            status = HealthStatus.HEALTHY
        elif all(c.status == HealthStatus.HEALTHY for c in children):
            status = HealthStatus.HEALTHY
        elif any(c.status == HealthStatus.UNHEALTHY for c in children):
            status = HealthStatus.UNHEALTHY
        else:
            status = HealthStatus.DEGRADED
        return HealthReport(
            status=status,
            component="group_controller_manager",
            details={"groups": self.group_ids},
            children=children,
        )

    # ---- 容器協定 ----

    def __len__(self) -> int:
        return len(self._controllers)

    def __contains__(self, group_id: str) -> bool:
        return group_id in self._controllers

    def __iter__(self) -> Iterator[tuple[str, SystemController]]:
        return iter(sorted(self._controllers.items()))
