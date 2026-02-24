# =============== Equipment Simulation - Virtual Meter ===============
#
# 虛擬電表模擬器
#
# 用於測試 Grid Forming 控制策略，支援：
#   - RANDOM: 在基準值附近隨機波動
#   - TEST_CURVE: 執行預定義的測試曲線

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Iterator

from csp_lib.core import get_logger

from .curve import DEFAULT_REGISTRY, CurvePoint, CurveProvider, CurveType

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

__all__ = [
    "MeterMode",
    "MeterReading",
    "VirtualMeter",
]


# ================ Enums ================


class MeterMode(Enum):
    """電表運行模式"""

    RANDOM = "random"
    TEST_CURVE = "test_curve"


# ================ Data Classes ================


@dataclass(frozen=True)
class MeterReading:
    """
    電表讀值 - 不可變

    Attributes:
        v: 電壓 (V)
        f: 頻率 (Hz)
        p: 有功功率 (kW)
        q: 無功功率 (kVar)
        s: 視在功率 (kVA)
        pf: 功率因數
    """

    v: float = 380.0
    f: float = 60.0
    p: float = 0.0
    q: float = 0.0
    s: float = 0.0
    pf: float = 1.0

    @classmethod
    def with_power(cls, v: float, f: float, p: float, q: float) -> MeterReading:
        """
        建立包含功率計算的讀值

        Args:
            v: 電壓 (V)
            f: 頻率 (Hz)
            p: 有功功率 (kW)
            q: 無功功率 (kVar)

        Returns:
            計算完成的 MeterReading
        """
        s = math.sqrt(p**2 + q**2)
        pf = p / s if s > 1e-6 else 1.0
        return cls(v=v, f=f, p=p, q=q, s=s, pf=pf)


# ================ VirtualMeter ================


class VirtualMeter:
    """
    虛擬電表模擬器

    支援兩種模式：
    1. RANDOM - 在基準值附近隨機波動
    2. TEST_CURVE - 執行預定義的測試曲線

    Example:
        ```python
        # 使用預設曲線
        meter = VirtualMeter(base_frequency=60.0)

        # 隨機模式
        await meter.update()
        print(meter.get_frequency())

        # 測試曲線模式
        meter.start_test_curve("fp_step")
        while meter.mode == MeterMode.TEST_CURVE:
            await meter.update()
            print(f"f={meter.get_frequency():.3f}Hz")
            await asyncio.sleep(1)
        ```

        ```python
        # 自定義曲線提供者
        from csp_lib.equipment.simulation import CurveRegistry

        registry = CurveRegistry()
        registry.register("custom", my_curve_factory)

        meter = VirtualMeter(curve_provider=registry)
        meter.start_test_curve("custom")
        ```
    """

    def __init__(
        self,
        base_voltage: float = 380.0,
        base_frequency: float = 60.0,
        voltage_noise: float = 5.0,
        frequency_noise: float = 0.05,
        curve_provider: CurveProvider | None = None,
    ) -> None:
        """
        初始化虛擬電表

        Args:
            base_voltage: 基準電壓 (V)
            base_frequency: 基準頻率 (Hz)
            voltage_noise: 電壓隨機波動範圍 (+/- V)
            frequency_noise: 頻率隨機波動範圍 (+/- Hz)
            curve_provider: 測試曲線提供者（預設使用 DEFAULT_REGISTRY）
        """
        self._base_voltage = base_voltage
        self._base_frequency = base_frequency
        self._voltage_noise = voltage_noise
        self._frequency_noise = frequency_noise
        self._curve_provider = curve_provider or DEFAULT_REGISTRY

        self._mode = MeterMode.RANDOM
        self._reading = MeterReading(v=base_voltage, f=base_frequency)

        # Test curve state
        self._curve_iterator: Iterator[CurvePoint] | None = None
        self._curve_name: str | None = None
        self._current_point: CurvePoint | None = None
        self._curve_end_time: float | None = None

    # ================ Properties ================

    @property
    def mode(self) -> MeterMode:
        """取得當前模式"""
        return self._mode

    @property
    def reading(self) -> MeterReading:
        """取得當前電表讀值"""
        return self._reading

    @property
    def curve_provider(self) -> CurveProvider:
        """取得曲線提供者"""
        return self._curve_provider

    # ================ Getters ================

    def get_frequency(self) -> float:
        """取得當前頻率"""
        return self._reading.f

    def get_voltage(self) -> float:
        """取得當前電壓"""
        return self._reading.v

    def list_available_curves(self) -> list[str]:
        """列出可用的測試曲線"""
        return self._curve_provider.list_curves()

    # ================ Curve Control ================

    def start_test_curve(self, curve_name: str) -> bool:
        """
        啟動測試曲線

        Args:
            curve_name: 曲線名稱

        Returns:
            是否成功啟動
        """
        curve = self._curve_provider.get_curve(curve_name)
        if curve is None:
            logger.error(f"Unknown curve: {curve_name}")
            return False

        self._curve_iterator = curve
        self._curve_name = curve_name
        self._mode = MeterMode.TEST_CURVE

        # 取得第一個點
        self._advance_curve()
        logger.info(f"VirtualMeter: 啟動測試曲線 {curve_name}")
        return True

    def stop_test_curve(self) -> None:
        """停止測試曲線"""
        self._mode = MeterMode.RANDOM
        self._curve_iterator = None
        self._curve_name = None
        self._current_point = None
        self._curve_end_time = None
        logger.info("VirtualMeter: 測試曲線結束")

    def _advance_curve(self) -> bool:
        """前進到下一個曲線點"""
        if self._curve_iterator is None:
            return False
        try:
            point = next(self._curve_iterator)
            self._current_point = point
            self._curve_end_time = time.monotonic() + point.duration
            return True
        except StopIteration:
            self.stop_test_curve()
            return False

    # ================ Update ================

    async def update(self) -> None:
        """更新電表讀值"""
        if self._mode == MeterMode.RANDOM:
            self._update_random()
        elif self._mode == MeterMode.TEST_CURVE:
            await self._update_test_curve()

    def _update_random(self) -> None:
        """隨機模式更新"""
        v = self._base_voltage + random.uniform(-self._voltage_noise, self._voltage_noise)
        f = self._base_frequency + random.uniform(-self._frequency_noise, self._frequency_noise)
        self._reading = MeterReading(
            v=v, f=f, p=self._reading.p, q=self._reading.q, s=self._reading.s, pf=self._reading.pf
        )

    async def _update_test_curve(self) -> None:
        """測試曲線模式更新"""
        if self._current_point is None or self._curve_end_time is None:
            self.stop_test_curve()
            return

        current_time = time.monotonic()

        if current_time >= self._curve_end_time:
            if not self._advance_curve():
                return

        if self._current_point is None:
            return

        if self._current_point.curve_type == CurveType.FREQUENCY:
            v = self._base_voltage + random.uniform(-self._voltage_noise, self._voltage_noise)
            f = self._current_point.value
        else:
            v = self._current_point.value
            f = self._base_frequency + random.uniform(-self._frequency_noise, self._frequency_noise)

        self._reading = MeterReading(
            v=v, f=f, p=self._reading.p, q=self._reading.q, s=self._reading.s, pf=self._reading.pf
        )

    # ================ Magic Methods ================

    def __str__(self) -> str:
        return f"<VirtualMeter mode={self._mode.value} v={self._reading.v:.1f}V f={self._reading.f:.3f}Hz>"

    def __repr__(self) -> str:
        return self.__str__()
