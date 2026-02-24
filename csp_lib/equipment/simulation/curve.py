# =============== Equipment Simulation - Curve ===============
#
# 測試曲線模組
#
# 提供模組化的測試曲線支援：
#   - CurveType: 曲線類型枚舉
#   - CurvePoint: 曲線點位定義
#   - CurveProvider: 曲線提供者協定
#   - CurveRegistry: 曲線註冊表

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Iterator, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass

__all__ = [
    "CurveType",
    "CurvePoint",
    "CurveProvider",
    "CurveRegistry",
    # Built-in curves
    "curve_fp_step",
    "curve_qv_step",
    "DEFAULT_REGISTRY",
]


# ================ Enums ================


class CurveType(Enum):
    """曲線類型"""

    FREQUENCY = "frequency"
    VOLTAGE = "voltage"


# ================ Data Classes ================


@dataclass(frozen=True)
class CurvePoint:
    """
    曲線點位 - 不可變

    Attributes:
        value: 目標值（頻率 Hz 或電壓 V）
        duration: 持續時間（秒）
        curve_type: 曲線類型
    """

    value: float
    duration: float
    curve_type: CurveType


# ================ Protocols ================


@runtime_checkable
class CurveProvider(Protocol):
    """
    測試曲線提供者協定

    定義取得測試曲線的介面，用於 Controller 整合測試。

    Example:
        ```python
        def my_test(provider: CurveProvider):
            curve = provider.get_curve("fp_step")
            if curve:
                for point in curve:
                    print(f"Target: {point.value}, Duration: {point.duration}s")
        ```
    """

    def get_curve(self, name: str) -> Iterator[CurvePoint] | None:
        """
        取得指定名稱的曲線

        Args:
            name: 曲線名稱

        Returns:
            曲線點位迭代器，若不存在則回傳 None
        """
        ...

    def list_curves(self) -> list[str]:
        """
        列出所有可用曲線名稱

        Returns:
            曲線名稱列表
        """
        ...


# ================ Registry ================


class CurveRegistry:
    """
    曲線註冊表

    實作 CurveProvider 協定，提供曲線的註冊與取得功能。

    Example:
        ```python
        registry = CurveRegistry()
        registry.register("custom", my_curve_factory)

        meter = VirtualMeter(curve_provider=registry)
        meter.start_test_curve("custom")
        ```
    """

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Iterator[CurvePoint]]] = {}

    def register(
        self,
        name: str,
        factory: Callable[[], Iterator[CurvePoint]],
    ) -> None:
        """
        註冊曲線工廠

        Args:
            name: 曲線名稱
            factory: 曲線工廠函式，呼叫時產生新的曲線迭代器
        """
        self._factories[name] = factory

    def unregister(self, name: str) -> bool:
        """
        取消註冊曲線

        Args:
            name: 曲線名稱

        Returns:
            是否成功移除
        """
        if name in self._factories:
            del self._factories[name]
            return True
        return False

    def get_curve(self, name: str) -> Iterator[CurvePoint] | None:
        """
        取得指定名稱的曲線

        Args:
            name: 曲線名稱

        Returns:
            曲線點位迭代器，若不存在則回傳 None
        """
        factory = self._factories.get(name)
        if factory is None:
            return None
        return factory()

    def list_curves(self) -> list[str]:
        """
        列出所有可用曲線名稱

        Returns:
            曲線名稱列表
        """
        return list(self._factories.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._factories

    def __len__(self) -> int:
        return len(self._factories)


# ================ Built-in Curves ================


def curve_fp_step() -> Iterator[CurvePoint]:
    """
    FP 階梯測試曲線

    用於測試頻率-功率響應，涵蓋正常與異常頻率範圍。
    每個頻率點持續 3 秒。

    Yields:
        CurvePoint: 頻率測試點
    """
    frequency_steps = [
        60.01,
        59.99,
        60.03,
        59.97,
        60.05,
        59.95,
        60.07,
        59.92,
        60.12,
        59.88,
        60.16,
        59.84,
        60.20,
        59.80,
        60.25,
        59.75,
        60.5,
        59.5,
    ]
    for freq in frequency_steps:
        yield CurvePoint(value=freq, duration=3.0, curve_type=CurveType.FREQUENCY)


def curve_qv_step() -> Iterator[CurvePoint]:
    """
    QV 階梯測試曲線

    用於測試電壓-無功響應。
    每個電壓點持續 3 秒。

    Yields:
        CurvePoint: 電壓測試點
    """
    voltage_steps = [380, 385, 375, 390, 370, 395, 365, 400, 360]
    for volt in voltage_steps:
        yield CurvePoint(value=float(volt), duration=3.0, curve_type=CurveType.VOLTAGE)


# ================ Default Registry ================


def _create_default_registry() -> CurveRegistry:
    """建立預設曲線註冊表"""
    registry = CurveRegistry()
    registry.register("fp_step", curve_fp_step)
    registry.register("qv_step", curve_qv_step)
    return registry


DEFAULT_REGISTRY: CurveRegistry = _create_default_registry()
