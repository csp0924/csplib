# =============== Integration - Power Distributor ===============
#
# 功率分配器
#
# 將系統級 Command 分配到多台設備：
#   - DeviceSnapshot: 設備狀態快照，供分配決策用
#   - PowerDistributor: 分配器 Protocol
#   - EqualDistributor: 均分
#   - ProportionalDistributor: 按額定容量比例分配
#   - SOCBalancingDistributor: SOC 平衡分配
#
# 架構位置：ProtectionGuard → [PowerDistributor] → CommandRouter
# 無 Distributor 時行為完全不變（同值廣播）

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from csp_lib.controller.core import Command
from csp_lib.core import get_logger

logger = get_logger("csp_lib.integration.distributor")


@dataclass(frozen=True)
class DeviceSnapshot:
    """
    設備狀態快照

    供 PowerDistributor 進行分配決策，包含：
    - 靜態 metadata（額定容量等，註冊時提供）
    - 動態 latest_values（當前讀取值）
    - 結構化 capabilities（依 capability slot 解析後的值）

    Attributes:
        device_id: 設備唯一識別碼
        metadata: 註冊時提供的靜態資訊（rated_p, rated_s 等）
        latest_values: 設備最新讀取值（完整 dict）
        capabilities: capability_name → {slot: value} 的解析結果
    """

    device_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    latest_values: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_capability_value(self, capability: Any, slot: str) -> Any:
        """
        取得 capability slot 的值

        Args:
            capability: Capability 物件或 capability 名稱字串
            slot: slot 名稱

        Returns:
            slot 值，不存在時回傳 None
        """
        name = getattr(capability, "name", capability)
        return self.capabilities.get(name, {}).get(slot)


@runtime_checkable
class PowerDistributor(Protocol):
    """
    功率分配器 Protocol

    將系統級 Command 分配到多台設備。

    實作者只需實現 distribute() 方法。
    回傳的 dict 中，key 為 device_id，value 為該設備應執行的 Command。
    未包含在回傳 dict 中的設備不會被寫入。
    """

    def distribute(self, command: Command, devices: list[DeviceSnapshot]) -> dict[str, Command]:
        """
        分配功率

        Args:
            command: 系統級命令（已經過 ProtectionGuard 保護）
            devices: 可用設備的狀態快照（已過濾 responsive + non-protected）

        Returns:
            device_id → Command 的映射
        """
        ...


class EqualDistributor:
    """
    均分分配器

    將系統功率均等分配到所有設備，不考慮額定容量差異。
    適用於所有設備規格相同的場景。
    """

    def distribute(self, command: Command, devices: list[DeviceSnapshot]) -> dict[str, Command]:
        n = len(devices)
        if n == 0:
            return {}
        p_each = command.p_target / n
        q_each = command.q_target / n
        return {d.device_id: Command(p_target=p_each, q_target=q_each) for d in devices}


class ProportionalDistributor:
    """
    按額定容量比例分配

    依據各設備的額定功率（metadata 中的 key）按比例分配。
    若所有設備額定值為 0 或缺失，fallback 為均分。

    Usage::

        distributor = ProportionalDistributor(rated_key="rated_p")
        # 設備 A rated_p=500, 設備 B rated_p=1000
        # → A 分得 1/3, B 分得 2/3
    """

    def __init__(self, rated_key: str = "rated_p") -> None:
        self._rated_key = rated_key

    def distribute(self, command: Command, devices: list[DeviceSnapshot]) -> dict[str, Command]:
        n = len(devices)
        if n == 0:
            return {}

        total_rated = sum(d.metadata.get(self._rated_key, 0.0) for d in devices)
        if total_rated <= 0:
            logger.warning(f"Total rated '{self._rated_key}' is 0, falling back to equal distribution.")
            return EqualDistributor().distribute(command, devices)

        result: dict[str, Command] = {}
        for d in devices:
            ratio = d.metadata.get(self._rated_key, 0.0) / total_rated
            result[d.device_id] = Command(
                p_target=command.p_target * ratio,
                q_target=command.q_target * ratio,
            )
        return result


class SOCBalancingDistributor:
    """
    SOC 平衡分配器

    在按額定容量比例分配的基礎上，根據各設備 SOC 偏差調整 P 分配：
    - 放電 (P > 0)：SOC 較高的設備多放
    - 充電 (P < 0)：SOC 較低的設備多充
    - Q 仍按額定容量比例分配

    演算法：
        avg_soc = mean(device SOCs)
        對每台設備：
            soc_deviation = (device_soc - avg_soc) / 100
            若放電: weight = rated * (1 + gain * soc_deviation)
            若充電: weight = rated * (1 - gain * soc_deviation)
        最終 P 按 weight 比例分配。

    Attributes:
        rated_key: metadata 中額定功率的 key
        soc_capability: SOC capability 名稱
        soc_slot: SOC slot 名稱
        gain: SOC 偏差增益（預設 2.0）
        per_device_max_p: 單台設備最大有功功率限制 (kW)，None 表示不限制
        per_device_max_q: 單台設備最大無功功率限制 (kVar)，None 表示不限制
    """

    def __init__(
        self,
        rated_key: str = "rated_p",
        soc_capability: str = "soc_readable",
        soc_slot: str = "soc",
        gain: float = 2.0,
        per_device_max_p: float | None = None,
        per_device_max_q: float | None = None,
    ) -> None:
        self._rated_key = rated_key
        self._soc_capability = soc_capability
        self._soc_slot = soc_slot
        self._gain = gain
        self._per_device_max_p = per_device_max_p
        self._per_device_max_q = per_device_max_q

    def distribute(self, command: Command, devices: list[DeviceSnapshot]) -> dict[str, Command]:
        n = len(devices)
        if n == 0:
            return {}

        # 收集 SOC 和額定值
        socs: list[float | None] = []
        rateds: list[float] = []
        for d in devices:
            soc = d.get_capability_value(self._soc_capability, self._soc_slot)
            socs.append(float(soc) if soc is not None else None)
            rateds.append(float(d.metadata.get(self._rated_key, 0.0)))

        total_rated = sum(rateds)
        if total_rated <= 0:
            logger.warning(f"Total rated '{self._rated_key}' is 0, falling back to equal distribution.")
            return EqualDistributor().distribute(command, devices)

        # 計算平均 SOC（忽略 None）
        valid_socs = [s for s in socs if s is not None]
        if not valid_socs:
            logger.warning("No SOC data available, falling back to proportional distribution.")
            return ProportionalDistributor(self._rated_key).distribute(command, devices)
        avg_soc = sum(valid_socs) / len(valid_socs)

        # 計算 P 分配權重
        is_discharging = command.p_target > 0
        p_weights: list[float] = []
        for i, _d in enumerate(devices):
            rated = rateds[i]
            soc = socs[i]
            if soc is None:
                soc = avg_soc  # 無 SOC 資料的設備按平均值處理

            soc_deviation = (soc - avg_soc) / 100.0
            if is_discharging:
                # 放電：高 SOC 多放
                factor = 1.0 + self._gain * soc_deviation
            else:
                # 充電：低 SOC 多充
                factor = 1.0 - self._gain * soc_deviation

            p_weights.append(rated * max(factor, 0.0))

        total_p_weight = sum(p_weights)
        if total_p_weight <= 0:
            return ProportionalDistributor(self._rated_key).distribute(command, devices)

        # P 按 SOC 平衡權重分配，Q 按額定比例分配
        result: dict[str, Command] = {}
        for i, d in enumerate(devices):
            p_ratio = p_weights[i] / total_p_weight
            q_ratio = rateds[i] / total_rated
            result[d.device_id] = Command(
                p_target=command.p_target * p_ratio,
                q_target=command.q_target * q_ratio,
            )

        # 硬體限幅 + 溢出轉移
        if self._per_device_max_p is not None:
            result = self._apply_clamp_and_overflow(result, "p_target", self._per_device_max_p)
        if self._per_device_max_q is not None:
            result = self._apply_clamp_and_overflow(result, "q_target", self._per_device_max_q)

        return result

    def _apply_clamp_and_overflow(
        self,
        result: dict[str, Command],
        field: str,
        max_val: float,
    ) -> dict[str, Command]:
        """
        對已分配結果執行硬體限幅與溢出轉移。

        演算法：
            1. 遍歷每台設備，若 |assigned| > max_val，限幅至 max_val（保留符號），
               累計溢出量。
            2. 將溢出量依未飽和設備的當前分配值按比例重新分配。
            3. 再執行一次限幅，處理重分配後超限的邊界情況。

        Args:
            result: device_id → Command 的映射（初始分配結果）
            field: 要限幅的 Command 欄位名稱 ("p_target" | "q_target")
            max_val: 單台設備的絕對值上限

        Returns:
            限幅並重分配後的 device_id → Command 映射
        """
        # Pass 1: clamp and collect overflow
        overflow = 0.0
        saturated: set[str] = set()
        values: dict[str, float] = {}

        for dev_id, cmd in result.items():
            val: float = getattr(cmd, field)
            if abs(val) > max_val:
                clamped = max_val if val > 0 else -max_val
                overflow += val - clamped
                values[dev_id] = clamped
                saturated.add(dev_id)
            else:
                values[dev_id] = val

        # Pass 2: redistribute overflow to non-saturated devices
        if abs(overflow) > 1e-9:
            unsaturated = {did: values[did] for did in values if did not in saturated}
            total_unsaturated = sum(abs(v) for v in unsaturated.values())

            for did in unsaturated:
                if total_unsaturated > 1e-9:
                    share = abs(unsaturated[did]) / total_unsaturated
                else:
                    # All unsaturated have zero assignment — split equally
                    share = 1.0 / len(unsaturated) if unsaturated else 0.0
                values[did] += overflow * share

        # Pass 3: re-clamp after redistribution, collect second overflow
        overflow2 = 0.0
        saturated2: set[str] = set(saturated)
        for dev_id in values:
            val = values[dev_id]
            if abs(val) > max_val:
                clamped = max_val if val > 0 else -max_val
                overflow2 += val - clamped
                values[dev_id] = clamped
                saturated2.add(dev_id)

        # Pass 4: distribute remaining overflow to devices with headroom
        if abs(overflow2) > 1e-9:
            headroom = {did: max_val - abs(values[did]) for did in values if did not in saturated2}
            total_headroom = sum(headroom.values())
            if total_headroom > 1e-9:
                sign = 1.0 if overflow2 > 0 else -1.0
                remaining = abs(overflow2)
                for did, hr in headroom.items():
                    share = min(hr, remaining * (hr / total_headroom))
                    values[did] += sign * share
                    remaining -= share
                    if remaining < 1e-9:
                        break

        # Build updated result
        updated: dict[str, Command] = {}
        for dev_id, cmd in result.items():
            if field == "p_target":
                updated[dev_id] = Command(p_target=values[dev_id], q_target=cmd.q_target)
            else:
                updated[dev_id] = Command(p_target=cmd.p_target, q_target=values[dev_id])
        return updated


__all__ = [
    "DeviceSnapshot",
    "PowerDistributor",
    "EqualDistributor",
    "ProportionalDistributor",
    "SOCBalancingDistributor",
]
