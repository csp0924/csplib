# =============== FP (Frequency-Power) Strategy ===============
#
# 頻率-功率控制策略 (AFC 核心)
# 根據系統頻率偏差計算功率輸出
#
# v0.8.2: 支援透過 RuntimeParameters + param_keys 動態覆蓋所有 FPConfig 欄位
# (f_base / f1..f6 / p1..p6)，以及 enabled_key 即時啟停。

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from csp_lib.controller.core import (
    Command,
    ConfigMixin,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)
from csp_lib.core import get_logger
from csp_lib.core.runtime_params import RuntimeParameters

from ._param_resolver import ParamResolver

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FPConfig(ConfigMixin):
    """
    FP 模式配置

    使用基準頻率 + 偏移量定義頻率-功率曲線。
    曲線共 6 個控制點，偏移量必須按升序排列。

    Attributes:
        f_base: 基準頻率 (Hz)，預設 60.0
        f1~f6: 頻率偏移量 (Hz)，絕對頻率 = f_base + f_offset
        p1~p6: 對應的功率百分比 (%)，-100 ~ 100
    """

    f_base: float = 60.0

    # 頻率偏移量 (Hz)，需按升序排列
    f1: float = -0.5  # 最低頻率偏移
    f2: float = -0.25
    f3: float = -0.02  # 死區下限
    f4: float = 0.02  # 死區上限
    f5: float = 0.25
    f6: float = 0.5  # 最高頻率偏移

    # 功率百分比 (%)，需按降序排列
    p1: float = 100.0  # f1 時的功率 (最大放電)
    p2: float = 52.0
    p3: float = 9.0  # 死區內功率
    p4: float = -9.0
    p5: float = -52.0
    p6: float = -100.0  # f6 時的功率 (最大充電)

    def get_absolute_frequencies(self) -> tuple[float, float, float, float, float, float]:
        """計算絕對頻率值 (f_base + 偏移)"""
        return (
            self.f_base + self.f1,
            self.f_base + self.f2,
            self.f_base + self.f3,
            self.f_base + self.f4,
            self.f_base + self.f5,
            self.f_base + self.f6,
        )

    def validate(self) -> None:
        """驗證配置有效性"""
        # 檢查頻率偏移升序
        offsets = [self.f1, self.f2, self.f3, self.f4, self.f5, self.f6]
        if not all(x < y for x, y in zip(offsets, offsets[1:], strict=False)):
            raise ValueError("頻率偏移量必須按升序排列")

        # 檢查功率降序
        powers = [self.p1, self.p2, self.p3, self.p4, self.p5, self.p6]
        if not all(x >= y for x, y in zip(powers, powers[1:], strict=False)):
            raise ValueError("功率百分比必須按降序排列")


class FPStrategy(Strategy):
    """
    頻率-功率控制策略 (Frequency-Power)

    根據系統頻率偏差，透過分段線性插值計算功率輸出。
    適用於 AFC (自動頻率控制) 應用。

    頻率曲線:
        f < f1: P = p1 (最大放電)
        f1 <= f < f2: 線性插值 p1 -> p2
        f2 <= f < f3: 線性插值 p2 -> 死區邊界
        f3 <= f < f4: P = 死區功率 (p3+p4)/2
        f4 <= f < f5: 線性插值 死區邊界 -> p5
        f5 <= f < f6: 線性插值 p5 -> p6
        f >= f6: P = p6 (最大充電)

    Runtime 動態化 (v0.8.2):
        ``param_keys`` 可涵蓋 FPConfig 所有 public 欄位：
        ``f_base`` / ``f1..f6`` / ``p1..p6``。
        ``enabled_key`` falsy → 回 ``Command(0, 0)``（立即停止 P 輸出）。

    Usage:
        config = FPConfig(f_base=60.0, f1=-0.5, f2=-0.2, ...)
        strategy = FPStrategy(config)
    """

    def __init__(
        self,
        config: FPConfig | None = None,
        *,
        params: RuntimeParameters | None = None,
        param_keys: Mapping[str, str] | None = None,
        enabled_key: str | None = None,
    ) -> None:
        self._config = config or FPConfig()
        self._resolver = ParamResolver(
            params=params,
            param_keys=param_keys,
            config=self._config,
        )
        self._enabled_key = enabled_key

    @property
    def config(self) -> FPConfig:
        """當前配置"""
        return self._config

    @property
    def execution_config(self) -> ExecutionConfig:
        """執行配置: 每秒執行"""
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        """
        執行策略邏輯

        從 context.extra["frequency"] 取得系統頻率，計算功率輸出。

        Args:
            context: 策略上下文，需包含 extra["frequency"]

        Returns:
            Command: 計算出的功率命令 (百分比需由 GridController 轉換)
        """
        # Runtime enabled 旗標：falsy → 立即輸出 0
        if self._enabled_key is not None:
            enabled = self._resolver.resolve_optional(self._enabled_key, True)
            if not enabled:
                logger.debug("FP: runtime disabled via '%s', output zero", self._enabled_key)
                return Command(p_target=0.0, q_target=0.0)

        frequency = context.extra.get("frequency")
        if frequency is None:
            # 無頻率資料，維持上一次命令
            return context.last_command

        p_percent = self._calculate_power(frequency)

        # 轉換為 kW (使用 system_base)
        if context.system_base is not None:
            p_kw = context.percent_to_kw(p_percent)
        else:
            p_kw = p_percent  # 無 system_base 時直接輸出百分比

        return Command(p_target=p_kw, q_target=0.0)

    def _calculate_power(self, frequency: float) -> float:
        """根據頻率計算功率百分比"""
        # 讀取動態配置欄位（f_base / f1..f6 / p1..p6）
        f_base = float(self._resolver.resolve("f_base"))
        f1_off = float(self._resolver.resolve("f1"))
        f2_off = float(self._resolver.resolve("f2"))
        f3_off = float(self._resolver.resolve("f3"))
        f4_off = float(self._resolver.resolve("f4"))
        f5_off = float(self._resolver.resolve("f5"))
        f6_off = float(self._resolver.resolve("f6"))
        p1 = float(self._resolver.resolve("p1"))
        p2 = float(self._resolver.resolve("p2"))
        p3 = float(self._resolver.resolve("p3"))
        p4 = float(self._resolver.resolve("p4"))
        p5 = float(self._resolver.resolve("p5"))
        p6 = float(self._resolver.resolve("p6"))

        f1 = f_base + f1_off
        f2 = f_base + f2_off
        f3 = f_base + f3_off
        f4 = f_base + f4_off
        f5 = f_base + f5_off
        f6 = f_base + f6_off

        # 低於 f1: 最大放電
        if frequency < f1:
            return p1

        # f1 ~ f2: 線性插值
        if f1 <= frequency < f2:
            return self._interpolate(frequency, f1, f2, p1, p2)

        # f2 ~ f3: 線性插值到死區
        if f2 <= frequency < f3:
            deadband_power = 0.5 * (p3 + p4)
            return self._interpolate(frequency, f2, f3, p2, deadband_power)

        # f3 ~ f4: 死區
        if f3 <= frequency < f4:
            return 0.5 * (p3 + p4)

        # f4 ~ f5: 死區到線性插值
        if f4 <= frequency < f5:
            deadband_power = 0.5 * (p3 + p4)
            return self._interpolate(frequency, f4, f5, deadband_power, p5)

        # f5 ~ f6: 線性插值
        if f5 <= frequency < f6:
            return self._interpolate(frequency, f5, f6, p5, p6)

        # 高於 f6: 最大充電
        return p6

    @staticmethod
    def _interpolate(x: float, x1: float, x2: float, y1: float, y2: float) -> float:
        """線性插值"""
        if x2 == x1:
            return y1
        return y1 + (y2 - y1) * (x - x1) / (x2 - x1)

    def update_config(self, config: FPConfig) -> None:
        """更新配置並重建 resolver（保留既有 runtime 設定）。"""
        self._config = config
        self._resolver = self._resolver.with_config(self._config)

    def __str__(self) -> str:
        return f"FPStrategy(f_base={self._config.f_base}Hz)"
