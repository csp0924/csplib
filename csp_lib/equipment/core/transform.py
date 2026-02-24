# =============== Equipment Core - Transform ===============
#
# 資料轉換步驟
#
# 提供可組合的資料轉換功能：
#   - ScaleTransform: 縮放轉換 (value * magnitude + offset)
#   - RoundTransform: 四捨五入
#   - EnumMapTransform: 數值 → 枚舉映射
#   - ClampTransform: 值域限制
#   - BitExtractTransform: 位元欄位提取轉換
#   - MultiFieldExtractTransform: 多位元欄位提取轉換

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class TransformStep(Protocol):
    """轉換步驟介面"""

    def apply(self, value: Any) -> Any:
        """套用轉換"""
        ...


@dataclass(frozen=True)
class ScaleTransform:
    """
    縮放轉換

    計算: result = value * magnitude + offset

    Attributes:
        magnitude: 倍率 (預設 1.0)
        offset: 偏移量 (預設 0.0)

    使用範例：
        # 溫度轉換: raw_value * 0.1 - 40
        ScaleTransform(magnitude=0.1, offset=-40)
    """

    magnitude: float = 1.0
    offset: float = 0.0

    def apply(self, value: Any) -> float:
        if not isinstance(value, (int, float)):
            raise TypeError(f"ScaleTransform 需要數值，收到: {type(value).__name__}")
        return float(value) * self.magnitude + self.offset


@dataclass(frozen=True)
class RoundTransform:
    """
    四捨五入轉換

    Attributes:
        decimals: 小數位數 (預設 2)
    """

    decimals: int = 2

    def apply(self, value: Any) -> float:
        if not isinstance(value, (int, float)):
            raise TypeError(f"RoundTransform 需要數值，收到: {type(value).__name__}")
        return round(float(value), self.decimals)


@dataclass(frozen=True)
class EnumMapTransform:
    """
    數值 → 枚舉映射轉換

    Attributes:
        mapping: 數值到字串的映射字典
        default: 找不到映射時的預設值

    使用範例：
        EnumMapTransform(
            mapping={0: "STOP", 1: "RUN", 2: "FAULT"},
            default="UNKNOWN",
        )
    """

    mapping: dict[int, str]
    default: str = "UNKNOWN"

    def __hash__(self) -> int:
        return hash((tuple(self.mapping.items()), self.default))

    def apply(self, value: Any) -> str:
        if not isinstance(value, int):
            # 嘗試轉換
            try:
                value = int(value)
            except (TypeError, ValueError):
                return self.default + " (" + str(value) + ")"
        return self.mapping.get(value, self.default)


@dataclass(frozen=True)
class ClampTransform:
    """
    值域限制轉換

    將值限制在指定範圍內。

    Attributes:
        min_value: 最小值 (可選)
        max_value: 最大值 (可選)
    """

    min_value: float | None = None
    max_value: float | None = None

    def apply(self, value: Any) -> float:
        if not isinstance(value, (int, float)):
            raise TypeError(f"ClampTransform 需要數值，收到: {type(value).__name__}")
        result = float(value)
        if self.min_value is not None:
            result = max(result, self.min_value)
        if self.max_value is not None:
            result = min(result, self.max_value)
        return result


@dataclass(frozen=True)
class BoolTransform:
    """
    布林轉換

    將數值轉換為布林值。

    Attributes:
        true_values: 視為 True 的值集合 (預設: {1})
    """

    true_values: frozenset[int] = frozenset({1})

    def apply(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value in self.true_values
        return bool(value)


@dataclass(frozen=True)
class InverseTransform:
    """
    反向縮放轉換 (用於寫入前的逆轉換)

    計算: result = (value - offset) / magnitude
    """

    magnitude: float = 1.0
    offset: float = 0.0

    def apply(self, value: Any) -> float:
        if not isinstance(value, (int, float)):
            raise TypeError(f"InverseTransform 需要數值，收到: {type(value).__name__}")
        if self.magnitude == 0:
            raise ValueError("magnitude 不可為 0")
        return (float(value) - self.offset) / self.magnitude


@dataclass(frozen=True)
class BitExtractTransform:
    """
    位元欄位提取轉換

    從整數值中提取指定範圍的位元。
    不限制位元大小，支援 16/32/64 bit 或更大的整數。

    Attributes:
        bit_offset: 起始位元位置 (0-based)
        bit_length: 位元數量 (預設 1 = 布林值)

    使用範例：
        # 提取 Bit 0 作為布林值
        BitExtractTransform(bit_offset=0)

        # 提取 Bit 8-11 作為 4-bit 數值
        BitExtractTransform(bit_offset=8, bit_length=4)
    """

    bit_offset: int
    bit_length: int = 1

    def __post_init__(self) -> None:
        if self.bit_offset < 0:
            raise ValueError(f"bit_offset 必須 >= 0，收到: {self.bit_offset}")
        if self.bit_length < 1:
            raise ValueError(f"bit_length 必須 >= 1，收到: {self.bit_length}")

    @property
    def mask(self) -> int:
        """計算位元遮罩"""
        return (1 << self.bit_length) - 1

    def apply(self, value: Any) -> int | bool:
        if not isinstance(value, int):
            raise TypeError(f"BitExtractTransform 需要整數，收到: {type(value).__name__}")
        result = (value >> self.bit_offset) & self.mask
        return bool(result) if self.bit_length == 1 else result


@dataclass(frozen=True)
class ByteExtractTransform:
    """
    位元組提取轉換

    從多暫存器值列表提取指定位元組。

    Attributes:
        byte_offset: 起始位元組位置
        byte_length: 位元組數量

    使用範例：
        # 從 [0x1234, 0x5678] 提取前 2 bytes
        ByteExtractTransform(byte_offset=0, byte_length=2)
        # -> bytes([0x12, 0x34])
    """

    byte_offset: int = 0
    byte_length: int = 1

    def __post_init__(self) -> None:
        if self.byte_offset < 0:
            raise ValueError(f"byte_offset 必須 >= 0，收到: {self.byte_offset}")
        if self.byte_length < 1:
            raise ValueError(f"byte_length 必須 >= 1，收到: {self.byte_length}")

    def apply(self, value: Any) -> bytes:
        if isinstance(value, (list, tuple)):
            # 假設是暫存器列表，每個暫存器 2 bytes
            data = bytearray()
            for reg in value:
                data.append((reg >> 8) & 0xFF)
                data.append(reg & 0xFF)
            return bytes(data[self.byte_offset : self.byte_offset + self.byte_length])
        raise TypeError(f"ByteExtractTransform 需要列表，收到: {type(value).__name__}")


@dataclass(frozen=True)
class PowerFactorTransform:
    """
    功率因數解碼轉換（Schneider PM5350 專用）

    PM5350 使用特殊編碼表示功率因數與相位：
        - Q1 (0° ~ 90°):   0 < x < 1   → PF = x, lagging
        - Q2 (90° ~ 180°): -2 < x < -1 → PF = -2 - x, leading
        - Q3 (180° ~ 270°): -1 < x < 0 → PF = x, lagging
        - Q4 (270° ~ 360°): 1 < x < 2  → PF = 2 - x, leading
        - Unity: |x| = 1 → PF = x

    Attributes:
        include_status: 是否回傳包含 pf/status 的字典（預設 False，只回傳 PF 值）

    Returns:
        如果 include_status=False: float (功率因數值)
        如果 include_status=True: dict {"pf": float, "status": "leading"|"lagging"|"unity"}
    """

    include_status: bool = False

    def apply(self, value: Any) -> float | dict[str, Any]:
        if not isinstance(value, (int, float)):
            raise TypeError(f"PowerFactorTransform 需要數值，收到: {type(value).__name__}")

        reg_val = float(value)

        # 判斷象限與解碼
        if reg_val > 1:
            # Q4: 1 < x < 2 → leading
            pf_val = 2 - reg_val
            status = "leading"
        elif reg_val < -1:
            # Q2: -2 < x < -1 → leading
            pf_val = -2 - reg_val
            status = "leading"
        elif abs(reg_val) == 1:
            # Unity
            pf_val = reg_val
            status = "unity"
        else:
            # Q1/Q3: -1 < x < 1 → lagging
            pf_val = reg_val
            status = "lagging"

        if self.include_status:
            return {"pf": pf_val, "status": status}
        return pf_val


@dataclass(frozen=True)
class MultiFieldExtractTransform:
    """
    多位元欄位提取轉換

    從單一整數值中提取多個命名的位元欄位。
    不限制位元大小，支援 16/32/64 bit 或更大的整數。

    Attributes:
        fields: 欄位定義元組，每個元素為 (name, bit_offset, bit_length)

    使用範例：
        MultiFieldExtractTransform(fields=(
            ("is_running", 0, 1),    # Bit 0, 布林
            ("has_fault", 1, 1),     # Bit 1, 布林
            ("mode", 8, 4),          # Bit 8-11, 4-bit 數值
        ))
    """

    fields: tuple[tuple[str, int, int], ...]

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("fields 不可為空")

        names = [f[0] for f in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("欄位名稱必須唯一")

        for name, offset, length in self.fields:
            if offset < 0:
                raise ValueError(f"欄位 '{name}' 的 bit_offset 必須 >= 0")
            if length < 1:
                raise ValueError(f"欄位 '{name}' 的 bit_length 必須 >= 1")

    def apply(self, value: Any) -> dict[str, int | bool]:
        if not isinstance(value, int):
            raise TypeError(f"MultiFieldExtractTransform 需要整數，收到: {type(value).__name__}")

        result: dict[str, int | bool] = {}
        for name, offset, length in self.fields:
            mask = (1 << length) - 1
            extracted = (value >> offset) & mask
            result[name] = bool(extracted) if length == 1 else extracted
        return result

    @property
    def field_names(self) -> tuple[str, ...]:
        """所有欄位名稱"""
        return tuple(f[0] for f in self.fields)


__all__ = [
    "TransformStep",
    "ScaleTransform",
    "RoundTransform",
    "EnumMapTransform",
    "ClampTransform",
    "BoolTransform",
    "ByteExtractTransform",
    "InverseTransform",
    "BitExtractTransform",
    "PowerFactorTransform",
    "MultiFieldExtractTransform",
]
