# =============== Equipment Device - Capability ===============
#
# 設備能力宣告系統
#
# 核心概念：
#   - Capability: 定義語意插槽 (slot)，描述「能做什麼」
#   - CapabilityBinding: 將語意插槽映射到實際點位名稱，描述「怎麼做」
#
# 設計原則：
#   - 同一能力，不同設備可使用不同點位名稱
#     例：HEARTBEAT 的 "heartbeat" slot
#         設備 A 映射到 "watchdog"
#         設備 B 映射到 "hb_reg"
#   - 支援執行期動態新增/移除能力
#   - EquipmentTemplate 宣告時自動驗證點位是否齊全

from __future__ import annotations

from dataclasses import dataclass

from csp_lib.core.errors import ConfigurationError


@dataclass(frozen=True)
class Capability:
    """
    設備能力定義

    使用語意插槽 (slot) 描述能力需要的讀/寫操作，
    而非指定具體的點位名稱。不同設備透過 CapabilityBinding 將
    slot 映射到各自的實際點位。

    Attributes:
        name: 能力名稱（全域唯一識別）
        write_slots: 需要的寫入插槽名稱
        read_slots: 需要的讀取插槽名稱
        description: 能力描述
    """

    name: str
    write_slots: tuple[str, ...] = ()
    read_slots: tuple[str, ...] = ()
    description: str = ""

    @property
    def all_slots(self) -> frozenset[str]:
        return frozenset(self.write_slots) | frozenset(self.read_slots)


@dataclass(frozen=True)
class CapabilityBinding:
    """
    設備對能力的具體綁定

    將 Capability 的語意插槽映射到設備的實際點位名稱。

    Usage::

        # Sungrow PCS: heartbeat 點位叫 "watchdog"
        CapabilityBinding(HEARTBEAT, {"heartbeat": "watchdog"})

        # Huawei PCS: heartbeat 點位叫 "hb_reg"
        CapabilityBinding(HEARTBEAT, {"heartbeat": "hb_reg"})

        # Controller 統一使用：
        point = device.resolve_point(HEARTBEAT, "heartbeat")
        # → "watchdog" or "hb_reg" 取決於設備

    Attributes:
        capability: 綁定的能力定義
        point_map: slot 名稱 → 實際點位名稱的映射
    """

    capability: Capability
    point_map: dict[str, str]

    def __post_init__(self) -> None:
        required = self.capability.all_slots
        provided = set(self.point_map.keys())
        missing = required - provided
        if missing:
            raise ConfigurationError(
                f"Capability '{self.capability.name}' binding missing slots: {sorted(missing)}"
            )
        extra = provided - required
        if extra:
            raise ConfigurationError(
                f"Capability '{self.capability.name}' binding has unknown slots: {sorted(extra)}"
            )

    def resolve(self, slot: str) -> str:
        """將語意插槽解析為實際點位名稱"""
        point_name = self.point_map.get(slot)
        if point_name is None:
            raise KeyError(f"Slot '{slot}' not found in capability '{self.capability.name}' binding")
        return point_name


# =============== Standard Capabilities ===============
#
# 預定義的標準能力。使用者也可自定義 Capability。

HEARTBEAT = Capability(
    name="heartbeat",
    write_slots=("heartbeat",),
    description="Controller watchdog heartbeat write",
)

ACTIVE_POWER_CONTROL = Capability(
    name="active_power_control",
    write_slots=("p_setpoint",),
    read_slots=("p_measurement",),
    description="Active power setpoint control (kW)",
)

REACTIVE_POWER_CONTROL = Capability(
    name="reactive_power_control",
    write_slots=("q_setpoint",),
    description="Reactive power setpoint control (kVar)",
)

SWITCHABLE = Capability(
    name="switchable",
    write_slots=("switch_cmd",),
    read_slots=("switch_status",),
    description="On/off switching (breaker, contactor, load)",
)

LOAD_SHEDDABLE = Capability(
    name="load_sheddable",
    write_slots=("switch_cmd",),
    read_slots=("active_power", "switch_status"),
    description="Load shedding (switchable + power measurement)",
)

MEASURABLE = Capability(
    name="measurable",
    read_slots=("active_power",),
    description="Has active power measurement",
)

FREQUENCY_MEASURABLE = Capability(
    name="frequency_measurable",
    read_slots=("frequency",),
    description="Has frequency measurement",
)

VOLTAGE_MEASURABLE = Capability(
    name="voltage_measurable",
    read_slots=("voltage",),
    description="Has voltage measurement",
)

SOC_READABLE = Capability(
    name="soc_readable",
    read_slots=("soc",),
    description="Has battery state of charge",
)


__all__ = [
    "Capability",
    "CapabilityBinding",
    # Standard capabilities
    "HEARTBEAT",
    "ACTIVE_POWER_CONTROL",
    "REACTIVE_POWER_CONTROL",
    "SWITCHABLE",
    "LOAD_SHEDDABLE",
    "MEASURABLE",
    "FREQUENCY_MEASURABLE",
    "VOLTAGE_MEASURABLE",
    "SOC_READABLE",
]
