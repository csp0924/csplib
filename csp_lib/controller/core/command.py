# =============== Command Module ===============
#
# 策略輸出命令與系統基準值
# - Command: 策略輸出命令 (不可變)
# - SystemBase: 系統基準值，用於百分比與絕對值轉換
# - NoChange / NO_CHANGE: 「此軸不變更」的 sentinel

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import TypeIs, TypeVar

# =============== Config Mixin ===============

T = TypeVar("T", bound="ConfigMixin")


class ConfigMixin:
    """
    Config 類別的 Mixin，提供統一的 from_dict 方法

    搭配 @dataclass 使用：

    Usage:
        @dataclass
        class MyConfig(ConfigMixin):
            p: float = 0.0
            q: float = 0.0

        config = MyConfig.from_dict({"p": 100, "q": 50, "extra": "ignored"})
    """

    @classmethod
    def from_dict(cls: type[T], data: dict) -> T:
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


# =============== NoChange Sentinel ===============


class NoChange:
    """``Command.p_target`` / ``Command.q_target`` 的 sentinel 類別：代表「此軸不變更」。

    v0.8.0 新增。策略可回傳 ``Command(p_target=NO_CHANGE, q_target=50.0)``
    要求 CommandRouter 僅寫入 Q 軸、保留設備當前 P 值。

    設計決策：
    - 單例（``NO_CHANGE`` 常數）— 所有比較應使用 ``is NO_CHANGE`` 而非 ``==``。
    - ``__bool__`` 明確拋 TypeError，避免在 ``if command.p_target:`` 式樣中被誤用為
      falsy（0.0 是合法 setpoint，NO_CHANGE 是「跳過」，語義完全不同）。
    - ``__eq__`` 僅對自身單例成立；供 mypy / dataclass 使用但不鼓勵依賴。
    - ``__repr__`` 回傳 ``"NO_CHANGE"``，方便日誌閱讀。
    """

    __slots__ = ()
    _instance: NoChange | None = None

    def __new__(cls) -> NoChange:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NO_CHANGE"

    def __bool__(self) -> bool:
        raise TypeError("NoChange is not a boolean; use `value is NO_CHANGE` instead.")

    def __eq__(self, other: object) -> bool:
        return other is self

    def __hash__(self) -> int:
        return id(self.__class__)


NO_CHANGE: NoChange = NoChange()
"""全域 NoChange sentinel 單例，代表「此軸不變更」。"""


def is_no_change(value: float | NoChange) -> TypeIs[NoChange]:
    """TypeIs（PEP 742）：判斷值是否為 NO_CHANGE sentinel。

    使用 TypeIs 而非 TypeGuard 以同時取得 True/False 兩分支的型別收斂：
    True 分支為 ``NoChange``，False 分支為 ``float``。避免散落各處的
    ``isinstance`` 或 ``value is NO_CHANGE`` 重覆檢查。

    Args:
        value: 可能是 float 或 NO_CHANGE 的值。

    Returns:
        True 代表值為 NO_CHANGE sentinel。
    """
    return value is NO_CHANGE


# =============== Command ===============


@dataclass(frozen=True, slots=True)
class Command:
    """
    策略輸出命令 (不可變)

    Attributes:
        p_target: 有功功率目標值 (kW)。v0.8.0 起型別為 ``float | NoChange``：
            傳 ``NO_CHANGE`` 代表「此軸不變更」，CommandRouter 會跳過 P 軸寫入，
            設備保留當前值。
        q_target: 無功功率目標值 (kVar)。同 p_target，v0.8.0 起支援 ``NO_CHANGE``。
        is_fallback: 是否為 fallback 命令。
            StrategyExecutor 在策略執行失敗時回傳 ``Command(0, 0, is_fallback=True)``，
            供上層（如監控、叢集狀態發佈）辨識是否為異常情境下的保守輸出。
            預設 False；``with_p`` / ``with_q`` 透過 ``dataclasses.replace``
            會自動保留此旗標。

            註：StrategyExecutor 的 fallback 路徑**刻意**使用 float ``0.0``
            而非 ``NO_CHANGE`` — fallback 是「安全停機」語義，必須明確下達 P=0、Q=0，
            不應保留可能造成危險的舊值。
    """

    p_target: float | NoChange = 0.0
    q_target: float | NoChange = 0.0
    is_fallback: bool = False

    def with_p(self, p: float | NoChange) -> Command:
        """建立新 Command，替換 P 值（支援 ``NO_CHANGE``）。"""
        return dataclasses.replace(self, p_target=p)

    def with_q(self, q: float | NoChange) -> Command:
        """建立新 Command，替換 Q 值（支援 ``NO_CHANGE``）。"""
        return dataclasses.replace(self, q_target=q)

    def effective_p(self, fallback: float = 0.0) -> float:
        """取得有效 P 值：若為 ``NO_CHANGE`` 則回傳 ``fallback``，否則回傳 ``p_target``。

        供需要「把 NO_CHANGE 轉成具體浮點數」的消費點（如級聯累加、積分補償器
        的狀態更新）使用，避免散落各處的 ``is NO_CHANGE`` 守衛。

        Args:
            fallback: 當 ``p_target`` 為 NO_CHANGE 時的替代值（預設 0.0）。

        Returns:
            有效的浮點 P 值。
        """
        value = self.p_target
        if is_no_change(value):
            return fallback
        return value

    def effective_q(self, fallback: float = 0.0) -> float:
        """取得有效 Q 值：若為 ``NO_CHANGE`` 則回傳 ``fallback``，否則回傳 ``q_target``。

        語義同 :meth:`effective_p`。
        """
        value = self.q_target
        if is_no_change(value):
            return fallback
        return value

    def __str__(self) -> str:
        p_repr = "NO_CHANGE" if is_no_change(self.p_target) else f"{self.p_target:.1f}kW"
        q_repr = "NO_CHANGE" if is_no_change(self.q_target) else f"{self.q_target:.1f}kVar"
        return f"Command(P={p_repr}, Q={q_repr})"


# =============== System Base ===============


@dataclass(frozen=True, slots=True)
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


__all__ = [
    "NO_CHANGE",
    "Command",
    "ConfigMixin",
    "NoChange",
    "SystemBase",
    "is_no_change",
]
