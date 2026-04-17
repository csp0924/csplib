# =============== Equipment Core - Point ===============
#
# 點位定義類別
#
# 提供 Modbus 點位的基礎定義：
#   - PointDefinition: 基礎點位
#   - ReadPoint: 讀取點位
#   - WritePoint: 寫入點位

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from csp_lib.modbus import ByteOrder, FunctionCode, ModbusDataType, RegisterOrder

if TYPE_CHECKING:
    from .pipeline import ProcessingPipeline


class ValueValidator(Protocol):
    """值驗證器介面"""

    def validate(self, value: Any) -> bool:
        """驗證值是否合法"""
        ...

    def get_error_message(self, value: Any) -> str:
        """取得錯誤訊息"""
        ...


@dataclass(frozen=True)
class PointDefinition:
    """
    點位定義 - 不可變

    Attributes:
        name: 點位名稱（唯一識別）
        address: Modbus 位址
        data_type: 資料類型（來自 csp_lib.modbus）
        function_code: Modbus 功能碼
        byte_order: 位元組順序
        register_order: 暫存器順序
    """

    name: str
    address: int
    data_type: ModbusDataType
    function_code: FunctionCode | None = None
    byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    register_order: RegisterOrder = RegisterOrder.HIGH_FIRST


@dataclass(frozen=True, slots=True)
class PointMetadata:
    """
    點位元資料（補充資訊）

    Attributes:
        unit: 單位（如 kW, V, A）
        description: 描述
        value_map: 數值對應名稱（如 {0: "Stop", 1: "Run", 2: "Fault"}）
    """

    unit: str | None = None
    description: str | None = None
    value_map: dict[int, str] | None = None

    def __hash__(self) -> int:
        return hash((self.unit, self.description, tuple(self.value_map.items()) if self.value_map else None))


@dataclass(frozen=True)
class ReadPoint(PointDefinition):
    """
    讀取點位

    Attributes:
        pipeline: 資料處理管線（可選）
        read_group: 讀取分組名稱（可選）
            - "": 參與自動合併邏輯
            - str: 只與相同 read_group 名稱的點位合併
        metadata: 點位元資料（可選）
        reject_non_finite: v0.8.0+ 新增。當為 ``True`` 時，若本次讀取值為
            非有限 float（NaN / +Inf / -Inf），設備會：
              - 保留 ``_latest_values`` 中的舊值（不覆寫）
              - log WARNING
              - **不**發 ``value_change`` 事件
              - **不**將該非有限值餵給 ``_evaluate_alarm`` 或 ``EVENT_READ_COMPLETE``
            用於防禦通訊瞬態讓上層保護/策略看到 NaN 造成比較恆 False 被無聲繞過。
            預設 ``False``（維持 v0.7.x 既有行為 — 非有限值直接寫入 latest）。
    """

    pipeline: ProcessingPipeline | None = None
    read_group: str = ""
    metadata: PointMetadata | None = None
    reject_non_finite: bool = False

    def __post_init__(self) -> None:
        if self.function_code is None:
            object.__setattr__(self, "function_code", FunctionCode.READ_HOLDING_REGISTERS)


@dataclass(frozen=True)
class WritePoint(PointDefinition):
    """
    寫入點位

    Attributes:
        validator: 值驗證器（可選）
        pipeline: 寫入前資料處理管線（可選），將使用者值轉換為暫存器值
        metadata: 點位元資料（可選）
    """

    validator: ValueValidator | None = None
    pipeline: ProcessingPipeline | None = None
    metadata: PointMetadata | None = None

    def __post_init__(self) -> None:
        if self.function_code is None:
            object.__setattr__(self, "function_code", FunctionCode.WRITE_MULTIPLE_REGISTERS)


# ========== 內建驗證器 ==========


@dataclass(frozen=True, slots=True)
class RangeValidator:
    """範圍驗證器"""

    min_value: float | None = None
    max_value: float | None = None

    def validate(self, value: Any) -> bool:
        if not isinstance(value, (int, float)):
            return False
        if self.min_value is not None and value < self.min_value:
            return False
        if self.max_value is not None and value > self.max_value:
            return False
        return True

    def get_error_message(self, value: Any) -> str:
        return f"值 {value} 超出範圍 [{self.min_value}, {self.max_value}]"


@dataclass(frozen=True, slots=True)
class EnumValidator:
    """枚舉驗證器"""

    allowed_values: tuple[Any, ...]

    def validate(self, value: Any) -> bool:
        return value in self.allowed_values

    def get_error_message(self, value: Any) -> str:
        return f"值 {value} 不在允許列表 {self.allowed_values} 中"


@dataclass(frozen=True, slots=True)
class CompositeValidator:
    """組合驗證器 - 所有驗證器都通過才算通過"""

    validators: tuple[ValueValidator, ...]

    def validate(self, value: Any) -> bool:
        return all(v.validate(value) for v in self.validators)

    def get_error_message(self, value: Any) -> str:
        error_messages = []
        for validator in self.validators:
            if not validator.validate(value):
                error_messages.append(validator.get_error_message(value))
        return ",".join(error_messages)


__all__ = [
    "ValueValidator",
    "PointDefinition",
    "PointMetadata",
    "ReadPoint",
    "WritePoint",
    "RangeValidator",
    "EnumValidator",
    "CompositeValidator",
]
