# =============== Droop (Primary Frequency Response) Strategy ===============
#
# 標準下垂控制一次頻率響應策略
# 根據系統頻率偏差，透過下垂公式計算功率輸出

from __future__ import annotations

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

    Usage:
        config = DroopConfig(f_base=60.0, droop=0.05, rated_power=500)
        strategy = DroopStrategy(config)  # noqa: F841
    """

    def __init__(self, config: DroopConfig | None = None) -> None:
        self._config = config or DroopConfig()
        self._active = False

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
        frequency = context.extra.get("frequency")
        if frequency is None:
            if self._active:
                logger.info("Droop: frequency data lost, holding last command")
                self._active = False
            return context.last_command

        if not self._active:
            logger.info("Droop: frequency data available, strategy active")
            self._active = True

        schedule_p: float = context.extra.get("schedule_p", 0.0)

        # Resolve rated power: config > system_base > fallback 0
        rated = self._resolve_rated_power(context)
        if rated <= 0:
            logger.debug("Droop: rated_power is 0, returning schedule_p only")
            return Command(p_target=schedule_p, q_target=0.0)

        cfg = self._config
        freq_error = frequency - cfg.f_base

        # Deadband check
        if abs(freq_error) <= cfg.deadband:
            pct = 0.0
            logger.debug(
                "Droop: freq=%.4f Hz, error=%.4f Hz within deadband=%.4f Hz, pct=0",
                frequency,
                freq_error,
                cfg.deadband,
            )
        else:
            gain = 100.0 / (cfg.f_base * cfg.droop)
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
        if cfg.max_droop_power > 0:
            droop_power = _clamp(droop_power, -cfg.max_droop_power, cfg.max_droop_power)

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
        """Resolve rated power from config or system_base.

        Priority: config.rated_power > system_base.p_base > 0.0

        Args:
            context: Strategy context with optional system_base.

        Returns:
            Rated power in kW.
        """
        if self._config.rated_power > 0:
            return self._config.rated_power
        if context.system_base is not None and context.system_base.p_base > 0:
            return context.system_base.p_base
        return 0.0

    def update_config(self, config: DroopConfig) -> None:
        """更新配置

        Args:
            config: 新的 DReg 配置
        """
        self._config = config

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
