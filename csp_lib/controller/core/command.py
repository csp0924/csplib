# =============== Command Module ===============
#
# 策略輸出命令與系統基準值
# - Command: 策略輸出命令 (不可變)
# - SystemBase: 系統基準值，用於百分比與絕對值轉換

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Type, TypeVar

# =============== Config Mixin ===============

T = TypeVar("T", bound="ConfigMixin")


class ConfigMixin:
    """
    Config 類別的 Mixin，提供統一的 from_dict 方法

    搭配 @dataclass 使用：

    Usage:
        @dataclass
        class PQModeConfig(ConfigMixin):
            p: float = 0.0
            q: float = 0.0

        config = PQModeConfig.from_dict({"p": 100, "q": 50, "extra": "ignored"})
    """

    @classmethod
    def from_dict(cls: Type[T], data: dict) -> T:
        """
        從字典建立 Config 實例

        自動過濾不存在於 dataclass 欄位的 key。
        支援 camelCase 到 snake_case 的轉換 (如 rampRate -> ramp_rate)。

        Args:
            data: 來源字典

        Returns:
            Config 實例
        """
        if not dataclasses.is_dataclass(cls):
            raise TypeError(f"{cls.__name__} must be a dataclass")

        field_names = {f.name for f in dataclasses.fields(cls)}

        # 建立 key 映射 (支援 camelCase -> snake_case)
        filtered_data = {}
        for key, value in data.items():
            # 嘗試原始 key
            if key in field_names:
                filtered_data[key] = value
            else:
                # 嘗試轉換 camelCase -> snake_case
                snake_key = _camel_to_snake(key)
                if snake_key in field_names:
                    filtered_data[snake_key] = value

        return cls(**filtered_data)

    def to_dict(self) -> dict:
        """轉換為字典"""
        if not dataclasses.is_dataclass(self):
            raise TypeError(f"{self.__class__.__name__} must be a dataclass")
        return dataclasses.asdict(self)


def _camel_to_snake(name: str) -> str:
    """將 camelCase 轉換為 snake_case"""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# =============== Command ===============


@dataclass(frozen=True)
class Command:
    """
    策略輸出命令 (不可變)

    Attributes:
        p_target: 有功功率目標值 (kW)
        q_target: 無功功率目標值 (kVar)
    """

    p_target: float = 0.0
    q_target: float = 0.0

    def with_p(self, p: float) -> Command:
        """建立新 Command，替換 P 值"""
        return dataclasses.replace(self, p_target=p)

    def with_q(self, q: float) -> Command:
        """建立新 Command，替換 Q 值"""
        return dataclasses.replace(self, q_target=q)

    def __str__(self) -> str:
        return f"Command(P={self.p_target:.1f}kW, Q={self.q_target:.1f}kVar)"


# =============== System Base ===============


@dataclass(frozen=True)
class SystemBase(ConfigMixin):
    """
    系統基準值，用於百分比與絕對值轉換

    AFC 等策略計算出的是百分比，需透過 system_base 轉換為 kW/kVar。

    Usage:
        p_kw = p_percent * system_base.p_base / 100
        q_kvar = q_percent * system_base.q_base / 100

    Attributes:
        p_base: 有功功率基準值 (kW)
        q_base: 無功功率基準值 (kVar)
    """

    p_base: float = 0.0
    q_base: float = 0.0
