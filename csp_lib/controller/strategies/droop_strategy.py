# =============== Droop (Primary Frequency Response) Strategy ===============
#
# 標準下垂控制一次頻率響應策略
# 根據系統頻率偏差，透過下垂公式計算功率輸出
#
# v0.8.2: 支援透過 RuntimeParameters + param_keys 動態覆蓋 f_base / droop /
# deadband / rated_power / max_droop_power，並可透過 enabled_key / schedule_p_key
# 實現 EMS 即時啟停與排程 P 注入。

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
class DroopConfig(ConfigMixin):
    """
    Droop 模式配置

    標準下垂控制參數，用於一次頻率響應 (Primary Frequency Response)。

    Attributes:
        f_base: 基準頻率 (Hz)，預設 60.0
        droop: 下垂係數，5% = 0.05，預設 0.05
        deadband: 死區寬度 (Hz)，頻率偏差在此範圍內不響應，預設 0.0
        rated_power: 額定功率 (kW)，0 表示使用 system_base.p_base，預設 0.0
        max_droop_power: 最大調頻功率 (kW)，0 表示不限制，預設 0.0
        interval: 執行週期 (秒)，預設 0.3
    """

    f_base: float = 60.0
    droop: float = 0.05
    deadband: float = 0.0
    rated_power: float = 0.0
    max_droop_power: float = 0.0
    interval: float = 0.3

    def validate(self) -> None:
        """驗證配置有效性

        Raises:
            ValueError: 當 droop 或 f_base 不合法時
        """
        if self.droop <= 0:
            raise ValueError("droop must be positive (e.g. 0.05 for 5%)")
        if self.f_base <= 0:
            raise ValueError("f_base must be positive")
        if self.deadband < 0:
            raise ValueError("deadband must be non-negative")
        if self.rated_power < 0:
            raise ValueError("rated_power must be non-negative")
        if self.max_droop_power < 0:
            raise ValueError("max_droop_power must be non-negative")
        if self.interval <= 0:
            raise ValueError("interval must be positive")


def _clamp(value: float, low: float, high: float) -> float:
    """將數值限制於 [low, high] 區間。"""
    if value < low:
        return low
    if value > high:
        return high
    return value


class DroopStrategy(Strategy):
    """
    標準下垂控制一次頻率響應策略 (Droop / Primary Frequency Response)

    根據系統頻率偏差，透過下垂公式計算功率輸出並疊加排程功率。
    適用於併網型儲能系統的一次頻率調節 (AFC/Droop) 應用。

    計算公式:
        gain = 100 / (f_base * droop)
        pct = -gain * (frequency - f_base)    (死區外)
        pct = 0                                (死區內)

        droop_power = rated_power * pct / 100
        total = schedule_p + droop_power
        total = clamp(total, -rated_power, rated_power)

    context.extra 需求:
        - frequency: 當前電網頻率 (Hz)
        - schedule_p: 排程功率設定點 (kW)，可選，預設 0

    行為:
        - 頻率低於基準 -> 正功率 (放電)
        - 頻率高於基準 -> 負功率 (充電)
        - 頻率偏差在死區內 -> 不響應

    Runtime 動態化 (v0.8.2):
        傳入 ``params`` + ``param_keys`` 即可讓 EMS 透過 RuntimeParameters
        即時覆蓋以下欄位（key 由 ``param_keys`` 映射，欄位缺失則 fallback config）：

            - f_base / droop / deadband / rated_power / max_droop_power

        額外旗標：
            - ``enabled_key``: params[enabled_key] 為 falsy → 回 ``Command(schedule_p, 0)``
              （schedule_p 來自 schedule_p_key）
            - ``schedule_p_key``: params[schedule_p_key] 提供排程 P（kW），優先於 context.extra

        ``droop_scale`` 針對 droop 欄位：例如 EMS 傳的是百分比 (5.0) 但 config 用小數 (0.05)，
        可設 ``droop_scale=0.01`` 將 runtime 值統一到小數。

    Args:
        config: DroopConfig，None 時使用預設值。
        params: RuntimeParameters，可選。必須與 ``param_keys`` 同時提供或同時省略。
        param_keys: {config 欄位名: runtime key} 映射。
        droop_scale: 套用於 droop 欄位的倍率（不論值來自 params 或 config）。
        enabled_key: runtime 啟停旗標 key。
        schedule_p_key: runtime 排程 P（kW）key。

    Usage:
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500)
        strategy = DroopStrategy(config)  # noqa: F841
    """

    def __init__(
        self,
        config: DroopConfig | None = None,
        *,
        params: RuntimeParameters | None = None,
        param_keys: Mapping[str, str] | None = None,
        droop_scale: float = 1.0,
        enabled_key: str | None = None,
        schedule_p_key: str | None = None,
    ) -> None:
        self._config = config or DroopConfig()
        self._active = False
        self._resolver = ParamResolver(
            params=params,
            param_keys=param_keys,
            config=self._config,
            scale={"droop": droop_scale},
        )
        self._enabled_key = enabled_key
        self._schedule_p_key = schedule_p_key

    @property
    def config(self) -> DroopConfig:
        """當前配置"""
        return self._config

    @property
    def execution_config(self) -> ExecutionConfig:
        """執行配置：週期執行（支援次秒級週期）。"""
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=self._config.interval)

    def execute(self, context: StrategyContext) -> Command:
        """
        執行下垂頻率響應策略

        從 context.extra 取得 frequency 和 schedule_p，計算功率輸出。
        若無 frequency 資料，維持上一次命令。

        Args:
            context: 策略上下文，需包含 extra["frequency"]

        Returns:
            Command: 計算出的功率命令 (kW)
        """
        # Runtime enabled 旗標：falsy → 僅輸出排程 P（或 0）
        if self._enabled_key is not None:
            enabled = self._resolver.resolve_optional(self._enabled_key, True)
            if not enabled:
                schedule_p = float(self._resolver.resolve_optional(self._schedule_p_key, 0.0))
                logger.debug("Droop: runtime disabled via '%s', output schedule_p=%s", self._enabled_key, schedule_p)
                return Command(p_target=schedule_p, q_target=0.0)

        frequency = context.extra.get("frequency")
        if frequency is None:
            if self._active:
                logger.info("Droop: frequency data lost, holding last command")
                self._active = False
            return context.last_command

        if not self._active:
            logger.info("Droop: frequency data available, strategy active")
            self._active = True

        # schedule_p：runtime param 優先，否則 fallback context.extra
        runtime_schedule_p = self._resolver.resolve_optional(self._schedule_p_key, None)
        schedule_p = (
            float(runtime_schedule_p) if runtime_schedule_p is not None else context.extra.get("schedule_p", 0.0)
        )

        # 讀取動態配置欄位
        f_base = float(self._resolver.resolve("f_base"))
        droop = float(self._resolver.resolve("droop"))
        deadband = float(self._resolver.resolve("deadband"))
        max_droop_power = float(self._resolver.resolve("max_droop_power"))

        # Resolve rated power: resolver > system_base > fallback 0
        rated = self._resolve_rated_power(context)
        if rated <= 0:
            logger.debug("Droop: rated_power is 0, returning schedule_p only")
            return Command(p_target=schedule_p, q_target=0.0)

        freq_error = frequency - f_base

        # Deadband check
        if abs(freq_error) <= deadband:
            pct = 0.0
            logger.debug(
                "Droop: freq=%.4f Hz, error=%.4f Hz within deadband=%.4f Hz, pct=0",
                frequency,
                freq_error,
                deadband,
            )
        else:
            gain = 100.0 / (f_base * droop)
            pct = -gain * freq_error
            pct = _clamp(pct, -100.0, 100.0)
            logger.debug(
                "Droop: freq=%.4f Hz, error=%.4f Hz, gain=%.2f, pct=%.2f%%",
                frequency,
                freq_error,
                gain,
                pct,
            )

        droop_power = rated * pct / 100.0

        # Apply max_droop_power limit
        if max_droop_power > 0:
            droop_power = _clamp(droop_power, -max_droop_power, max_droop_power)

        total = schedule_p + droop_power
        total = _clamp(total, -rated, rated)

        logger.debug(
            "Droop: schedule_p=%.1f kW, droop_power=%.1f kW, total=%.1f kW",
            schedule_p,
            droop_power,
            total,
        )

        return Command(p_target=total, q_target=0.0)

    def _resolve_rated_power(self, context: StrategyContext) -> float:
        """Resolve rated power from runtime/config or system_base.

        Priority: resolver("rated_power") > system_base.p_base > 0.0

        Args:
            context: Strategy context with optional system_base.

        Returns:
            Rated power in kW.
        """
        rated = float(self._resolver.resolve("rated_power"))
        if rated > 0:
            return rated
        if context.system_base is not None and context.system_base.p_base > 0:
            return context.system_base.p_base
        return 0.0

    def update_config(self, config: DroopConfig) -> None:
        """更新配置並重建 resolver（保留既有 runtime/scale 設定）。

        Args:
            config: 新的 Droop 配置
        """
        self._config = config
        self._resolver = self._resolver.with_config(self._config)

    async def on_activate(self) -> None:
        """策略啟用時重置狀態"""
        self._active = False
        logger.info("DroopStrategy activated")

    async def on_deactivate(self) -> None:
        """策略停用時記錄"""
        self._active = False
        logger.info("DroopStrategy deactivated")

    def __str__(self) -> str:
        return (
            f"DroopStrategy(f_base={self._config.f_base}Hz, "
            f"droop={self._config.droop}, "
            f"deadband={self._config.deadband}Hz)"
        )
