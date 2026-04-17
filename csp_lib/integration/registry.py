# =============== Integration - Registry ===============
#
# Trait-based 設備查詢索引
#
# 維護 device_id ↔ trait 的雙向索引：
#   - 依 device_id 查詢設備
#   - 依 trait 查詢所有匹配設備（支援 responsive 過濾）
#   - 依 capability 查詢具備指定能力的設備
#   - validate_capabilities: 驗證能力需求是否滿足（preflight check）
#   - 不管理設備生命週期，僅做查詢索引

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable, Sequence

from csp_lib.core import get_logger

from .schema import CapabilityRequirement, capability_display_name

if TYPE_CHECKING:
    from csp_lib.equipment.device import AsyncModbusDevice
    from csp_lib.equipment.device.capability import Capability

logger = get_logger(__name__)

# Status-change callback 簽名: (device_id, responsive) -> None
# responsive=True 代表設備從無回應轉為有回應；False 則為反向。
StatusChangeCallback = Callable[[str, bool], None]


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
        self._lock = threading.Lock()
        self._devices: dict[str, AsyncModbusDevice] = {}  # device_id → 設備實例
        self._device_traits: dict[str, set[str]] = {}  # device_id → 該設備的 traits
        self._trait_devices: dict[str, set[str]] = {}  # trait → 擁有該 trait 的 device_ids
        self._metadata: dict[str, dict[str, Any]] = {}  # device_id → 靜態 metadata
        # Status-change 觀察者與最近一次觀測狀態（用於變更偵測）
        self._status_observers: list[StatusChangeCallback] = []
        self._last_responsive: dict[str, bool] = {}  # device_id → 上次 notify 時的 responsive

    # ---- 註冊 / 移除 ----

    def register(
        self,
        device: AsyncModbusDevice,
        traits: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        註冊設備與可選的 traits 和 metadata

        Args:
            device: 要註冊的 Modbus 設備
            traits: 設備的 trait 標籤列表（可選）
            metadata: 設備靜態資訊（可選），如 rated_p、rated_s 等

        Raises:
            ValueError: device_id 已存在時拋出，防止靜默覆蓋
        """
        did = device.device_id
        with self._lock:
            if did in self._devices:
                raise ValueError(f"Device '{did}' is already registered.")
            self._devices[did] = device
            self._device_traits[did] = set()
            self._metadata[did] = dict(metadata) if metadata else {}
            for trait in traits or []:
                self._add_trait_index(did, trait)

    def register_with_capabilities(
        self,
        device: AsyncModbusDevice,
        extra_traits: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Register device with auto-discovered traits from capabilities.

        Auto-generates traits like "cap:active_power_control" from device capabilities,
        then merges with extra_traits provided by user.

        Args:
            device: 要註冊的 Modbus 設備
            extra_traits: 額外的 trait 標籤（可選），會排在自動發現的 traits 前面
            metadata: 設備靜態資訊（可選）

        Raises:
            ValueError: device_id 已存在時拋出
        """
        auto_traits = [f"cap:{cap_name}" for cap_name in device.capabilities]
        all_traits = list(extra_traits or []) + auto_traits
        self.register(device, traits=all_traits, metadata=metadata or {})

    def unregister(self, device_id: str) -> None:
        """
        移除設備及其所有 trait 關聯

        Args:
            device_id: 要移除的設備 ID（不存在時靜默忽略）
        """
        with self._lock:
            if device_id not in self._devices:
                return
            for trait in list(self._device_traits.get(device_id, [])):
                self._remove_trait_index(device_id, trait)
            del self._devices[device_id]
            del self._device_traits[device_id]
            self._metadata.pop(device_id, None)
            # 移除設備時同步清除狀態基準，避免下次以同名 id 重註冊後
            # 首次 notify 誤判為「狀態變化」
            self._last_responsive.pop(device_id, None)

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
        with self._lock:
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
        with self._lock:
            if device_id not in self._devices:
                raise KeyError(f"Device '{device_id}' is not registered.")
            self._remove_trait_index(device_id, trait)

    # ---- 查詢 ----

    def get_device(self, device_id: str) -> AsyncModbusDevice | None:
        """依 ID 查詢設備，不存在回傳 None"""
        with self._lock:
            return self._devices.get(device_id)

    def get_devices_by_trait(self, trait: str) -> list[AsyncModbusDevice]:
        """依 trait 查詢所有設備（按 device_id 排序，確保確定性）"""
        with self._lock:
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
        with self._lock:
            return set(self._device_traits.get(device_id, set()))

    def get_metadata(self, device_id: str) -> dict[str, Any]:
        """取得設備的靜態 metadata，未註冊時回傳空 dict"""
        with self._lock:
            return dict(self._metadata.get(device_id, {}))

    @property
    def all_devices(self) -> list[AsyncModbusDevice]:
        """所有已註冊設備（按 device_id 排序）"""
        with self._lock:
            return [self._devices[did] for did in sorted(self._devices)]

    @property
    def all_traits(self) -> list[str]:
        """所有已知的 trait 標籤（排序）"""
        with self._lock:
            return sorted(self._trait_devices.keys())

    # ---- Capability 查詢 ----

    def get_devices_with_capability(self, capability: Capability | str) -> list[AsyncModbusDevice]:
        """取得具備指定能力的所有設備（按 device_id 排序）"""
        with self._lock:
            return sorted(
                [d for d in self._devices.values() if d.has_capability(capability)],
                key=lambda d: d.device_id,
            )

    def get_responsive_devices_with_capability(self, capability: Capability | str) -> list[AsyncModbusDevice]:
        """取得具備指定能力且 responsive 的設備（按 device_id 排序）"""
        return [d for d in self.get_devices_with_capability(capability) if d.is_responsive]

    def validate_capabilities(self, requirements: list[CapabilityRequirement]) -> list[str]:
        """驗證設備能力是否滿足需求

        Args:
            requirements: 能力需求列表

        Returns:
            不滿足的需求描述列表（空 = 全部通過）
        """
        failures: list[str] = []
        for req in requirements:
            if req.trait_filter:
                devices = [d for d in self.get_devices_by_trait(req.trait_filter) if d.has_capability(req.capability)]
            else:
                devices = self.get_devices_with_capability(req.capability)

            if len(devices) < req.min_count:
                cap_name = capability_display_name(req.capability)
                trait_suffix = f" with trait {req.trait_filter!r}" if req.trait_filter else ""
                failures.append(
                    f"Capability '{cap_name}' requires {req.min_count} device(s){trait_suffix}, found {len(devices)}"
                )
        return failures

    def get_capability_map(self) -> dict[str, list[str]]:
        """取得 capability_name → device_ids 映射

        Returns:
            capability 名稱對應具備該能力的設備 ID 列表（按 device_id 排序）
        """
        with self._lock:
            result: dict[str, list[str]] = {}
            for did, device in self._devices.items():
                for cap_name in device.capabilities:
                    if cap_name not in result:
                        result[cap_name] = []
                    result[cap_name].append(did)
            # 排序 device_ids 確保確定性
            for cap_name in result:
                result[cap_name].sort()
            return result

    def get_capability_map_text(self) -> str:
        """取得格式化的 capability 映射文字表格

        Returns:
            格式化文字，每行一個 capability 及其設備列表
        """
        cap_map = self.get_capability_map()
        if not cap_map:
            return ""
        lines: list[str] = []
        for cap_name in sorted(cap_map):
            device_ids = cap_map[cap_name]
            count = len(device_ids)
            devices_str = ", ".join(device_ids)
            lines.append(f"{cap_name} ({count} devices): {devices_str}")
        return "\n".join(lines)

    def capability_health(self, capability: Capability | str) -> dict[str, Any]:
        """取得指定 capability 的健康狀態

        Args:
            capability: 能力定義或名稱

        Returns:
            包含 capability、total_devices、responsive_devices、
            responsive_ratio、devices 的字典
        """
        cap_name = capability.name if hasattr(capability, "name") else str(capability)
        devices = self.get_devices_with_capability(capability)
        total = len(devices)
        device_details: list[dict[str, Any]] = []
        responsive_count = 0
        for d in devices:
            is_resp = d.is_responsive
            if is_resp:
                responsive_count += 1
            device_details.append({"device_id": d.device_id, "is_responsive": is_resp})
        return {
            "capability": cap_name,
            "total_devices": total,
            "responsive_devices": responsive_count,
            "responsive_ratio": responsive_count / total if total > 0 else 0.0,
            "devices": device_details,
        }

    def refresh_capability_traits(self, device_id: str) -> None:
        """重新同步設備的 capability traits（cap:xxx）

        根據設備目前的 capabilities 重新建立 cap: 前綴的 traits，
        移除不再存在的、新增新出現的。

        Args:
            device_id: 目標設備 ID

        Raises:
            KeyError: device_id 未註冊時拋出
        """
        with self._lock:
            device = self._devices[device_id]  # KeyError if not found
            current_cap_traits = {t for t in self._device_traits.get(device_id, set()) if t.startswith("cap:")}
            desired_cap_traits = {f"cap:{name}" for name in device.capabilities}
            for trait in current_cap_traits - desired_cap_traits:
                self._remove_trait_index(device_id, trait)
            for trait in desired_cap_traits - current_cap_traits:
                self._add_trait_index(device_id, trait)

    def __len__(self) -> int:
        with self._lock:
            return len(self._devices)

    def __contains__(self, device_id: str) -> bool:
        with self._lock:
            return device_id in self._devices

    # ---- 狀態變化通知 ----

    def on_status_change(self, callback: StatusChangeCallback) -> None:
        """
        註冊「設備回應狀態變化」觀察者。

        回呼簽名: ``callback(device_id: str, responsive: bool) -> None``，
        其中 ``responsive`` 為變化後的新狀態。僅當實際變化（baseline 已建立
        且新舊狀態不同）時才會觸發；首次 ``notify_status`` 僅建立 baseline。

        Args:
            callback: 狀態變化回呼。例外會被捕獲並記錄，不會影響其他觀察者。
        """
        self._status_observers.append(callback)

    def remove_status_observer(self, callback: StatusChangeCallback) -> None:
        """
        移除已註冊的狀態變化觀察者。

        Args:
            callback: 欲移除的回呼。未註冊時靜默忽略。
        """
        try:
            self._status_observers.remove(callback)
        except ValueError:
            pass

    def notify_status(self, device_id: str) -> None:
        """
        由呼叫方（DeviceManager / 輪詢迴圈）在讀取設備 ``is_responsive``
        後呼叫，Registry 會判斷是否為狀態變化並通知觀察者。

        行為：
            * 首次呼叫：僅建立 baseline，不觸發 observers（避免啟動期噪訊）。
            * 後續呼叫：若 ``is_responsive`` 與上次相比發生變化，鎖外
              同步呼叫所有觀察者。
            * 未註冊的 ``device_id`` 靜默忽略。

        Deadlock 預防：
            在鎖內讀取 device 與 ``_last_responsive``、判定 changed、更新
            baseline；離開鎖後才呼叫 observers。若 observer 反向存取
            Registry，不會發生重入死鎖。

        Args:
            device_id: 設備 ID。
        """
        changed_to: bool | None = None
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                return
            current = bool(device.is_responsive)
            prev = self._last_responsive.get(device_id)
            # 更新 baseline；前後差異才觸發
            self._last_responsive[device_id] = current
            if prev is not None and prev != current:
                changed_to = current
        # 鎖外呼叫 observers
        if changed_to is not None:
            self._notify_status_change(device_id, changed_to)

    def _notify_status_change(self, device_id: str, responsive: bool) -> None:
        """
        同步呼叫所有 status observers（鎖外執行）。

        單一 observer 例外不影響其他 observer，統一以
        ``logger.opt(exception=True).warning(...)`` 記錄，避免中斷呼叫鏈。

        Args:
            device_id: 狀態變化的設備 ID。
            responsive: 變化後的 responsive 狀態。
        """
        for cb in self._status_observers:
            try:
                cb(device_id, responsive)
            except Exception:
                logger.opt(exception=True).warning(
                    f"DeviceRegistry status observer 執行失敗: device_id={device_id}, responsive={responsive}"
                )

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
