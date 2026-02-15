# =============== Integration - Registry ===============
#
# Trait-based 設備查詢索引
#
# 維護 device_id ↔ trait 的雙向索引：
#   - 依 device_id 查詢設備
#   - 依 trait 查詢所有匹配設備（支援 responsive 過濾）
#   - 不管理設備生命週期，僅做查詢索引

from __future__ import annotations

from typing import TYPE_CHECKING

from csp_lib.core import get_logger

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice

logger = get_logger("csp_lib.integration.registry")


class DeviceRegistry:
    """
    Trait-based 設備查詢索引

    維護雙向索引：
      - device_id → AsyncModbusDevice
      - device_id → set[trait]
      - trait → set[device_id]

    不管理設備生命週期，僅負責查詢。
    所有依 trait 查詢的結果皆按 device_id 排序，確保確定性。
    """

    def __init__(self) -> None:
        self._devices: dict[str, AsyncModbusDevice] = {}  # device_id → 設備實例
        self._device_traits: dict[str, set[str]] = {}  # device_id → 該設備的 traits
        self._trait_devices: dict[str, set[str]] = {}  # trait → 擁有該 trait 的 device_ids

    # ---- 註冊 / 移除 ----

    def register(self, device: AsyncModbusDevice, traits: list[str] | None = None) -> None:
        """
        註冊設備與可選的 traits

        Args:
            device: 要註冊的 Modbus 設備
            traits: 設備的 trait 標籤列表（可選）

        Raises:
            ValueError: device_id 已存在時拋出，防止靜默覆蓋
        """
        did = device.device_id
        if did in self._devices:
            raise ValueError(f"Device '{did}' is already registered.")
        self._devices[did] = device
        self._device_traits[did] = set()
        for trait in traits or []:
            self._add_trait_index(did, trait)

    def unregister(self, device_id: str) -> None:
        """
        移除設備及其所有 trait 關聯

        Args:
            device_id: 要移除的設備 ID（不存在時靜默忽略）
        """
        if device_id not in self._devices:
            return
        for trait in list(self._device_traits.get(device_id, [])):
            self._remove_trait_index(device_id, trait)
        del self._devices[device_id]
        del self._device_traits[device_id]

    # ---- Trait 管理 ----

    def add_trait(self, device_id: str, trait: str) -> None:
        """
        為已註冊設備新增 trait

        Args:
            device_id: 目標設備 ID
            trait: 要新增的 trait 標籤

        Raises:
            KeyError: device_id 未註冊時拋出
        """
        if device_id not in self._devices:
            raise KeyError(f"Device '{device_id}' is not registered.")
        self._add_trait_index(device_id, trait)

    def remove_trait(self, device_id: str, trait: str) -> None:
        """
        移除設備的 trait

        Args:
            device_id: 目標設備 ID
            trait: 要移除的 trait 標籤

        Raises:
            KeyError: device_id 未註冊時拋出
        """
        if device_id not in self._devices:
            raise KeyError(f"Device '{device_id}' is not registered.")
        self._remove_trait_index(device_id, trait)

    # ---- 查詢 ----

    def get_device(self, device_id: str) -> AsyncModbusDevice | None:
        """依 ID 查詢設備，不存在回傳 None"""
        return self._devices.get(device_id)

    def get_devices_by_trait(self, trait: str) -> list[AsyncModbusDevice]:
        """依 trait 查詢所有設備（按 device_id 排序，確保確定性）"""
        ids = self._trait_devices.get(trait, set())
        return [self._devices[did] for did in sorted(ids)]

    def get_responsive_devices_by_trait(self, trait: str) -> list[AsyncModbusDevice]:
        """依 trait 查詢所有 is_responsive=True 的設備（按 device_id 排序）"""
        return [d for d in self.get_devices_by_trait(trait) if d.is_responsive]

    def get_first_responsive_device_by_trait(self, trait: str) -> AsyncModbusDevice | None:
        """依 trait 取得第一台 responsive 設備，無則回傳 None"""
        devices = self.get_responsive_devices_by_trait(trait)
        return devices[0] if devices else None

    def get_traits(self, device_id: str) -> set[str]:
        """取得設備的所有 traits，未註冊時回傳空集合"""
        return set(self._device_traits.get(device_id, set()))

    @property
    def all_devices(self) -> list[AsyncModbusDevice]:
        """所有已註冊設備（按 device_id 排序）"""
        return [self._devices[did] for did in sorted(self._devices)]

    @property
    def all_traits(self) -> list[str]:
        """所有已知的 trait 標籤（排序）"""
        return sorted(self._trait_devices.keys())

    def __len__(self) -> int:
        return len(self._devices)

    def __contains__(self, device_id: str) -> bool:
        return device_id in self._devices

    # ---- 內部輔助 ----

    def _add_trait_index(self, device_id: str, trait: str) -> None:
        """建立 device_id ↔ trait 的雙向索引"""
        self._device_traits[device_id].add(trait)
        if trait not in self._trait_devices:
            self._trait_devices[trait] = set()
        self._trait_devices[trait].add(device_id)

    def _remove_trait_index(self, device_id: str, trait: str) -> None:
        """移除 device_id ↔ trait 的雙向索引"""
        self._device_traits[device_id].discard(trait)
        if trait in self._trait_devices:
            self._trait_devices[trait].discard(device_id)
            # trait 已無設備時，清除該 trait 索引
            if not self._trait_devices[trait]:
                del self._trait_devices[trait]
