# =============== Dynamic Protection Rules ===============
#
# 從 RuntimeParameters 讀取動態參數的保護規則
#
# 解決 SOCProtectionConfig 等 frozen dataclass 無法即時更新的問題。
# 適用於從外部系統（EMS/Modbus/Redis）即時推送的參數。
#
# 規則：
#   - DynamicSOCProtection: 動態 SOC 上下限保護
#   - GridLimitProtection: 外部功率限制（電力公司/排程）
#   - RampStopProtection: 故障/告警時斜坡降功率至 0

from __future__ import annotations

from typing import TYPE_CHECKING

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.core import get_logger

from .protection import ProtectionRule

if TYPE_CHECKING:
    from csp_lib.core.runtime_params import RuntimeParameters

logger = get_logger("csp_lib.controller.system.dynamic_protection")


# =============== Dynamic SOC Protection ===============


class DynamicSOCProtection(ProtectionRule):
    """
    動態 SOC 保護

    每次 evaluate() 時從 RuntimeParameters 讀取 soc_max / soc_min，
    支援即時更新（如來自 EMS/Modbus 的寫入）。

    P > 0 = 放電；P < 0 = 充電

    RuntimeParameters keys:
        soc_max: SOC 上限（%），預設 95.0
        soc_min: SOC 下限（%），預設 5.0

    Args:
        params: RuntimeParameters 實例
        soc_max_key: soc_max 在 params 中的 key
        soc_min_key: soc_min 在 params 中的 key
        warning_band: 警戒區寬度（%），0 = 不啟用漸進限制
    """

    def __init__(
        self,
        params: RuntimeParameters,
        soc_max_key: str = "soc_max",
        soc_min_key: str = "soc_min",
        warning_band: float = 0.0,
    ) -> None:
        self._params = params
        self._soc_max_key = soc_max_key
        self._soc_min_key = soc_min_key
        self._warning_band = warning_band
        self._is_triggered = False

    @property
    def name(self) -> str:
        return "dynamic_soc_protection"

    @property
    def is_triggered(self) -> bool:
        return self._is_triggered

    def evaluate(self, command: Command, context: StrategyContext) -> Command:
        soc = context.soc
        if soc is None:
            self._is_triggered = False
            return command

        soc_max = float(self._params.get(self._soc_max_key, 95.0))
        soc_min = float(self._params.get(self._soc_min_key, 5.0))
        p = command.p_target

        # SOC 過高：禁止充電
        if soc >= soc_max:
            if p < 0:
                self._is_triggered = True
                logger.warning(
                    f"DynamicSOC: SOC={soc:.1f}% >= {soc_max}%, block charging, P: {p:.1f} → 0"
                )
                return command.with_p(0.0)
            self._is_triggered = False
            return command

        # SOC 過低：禁止放電
        if soc <= soc_min:
            if p > 0:
                self._is_triggered = True
                logger.warning(
                    f"DynamicSOC: SOC={soc:.1f}% <= {soc_min}%, block discharging, P: {p:.1f} → 0"
                )
                return command.with_p(0.0)
            self._is_triggered = False
            return command

        # 高側警戒區：漸進限制充電
        wb = self._warning_band
        if wb > 0 and soc >= soc_max - wb and p < 0:
            ratio = (soc_max - soc) / wb
            limited = p * ratio
            self._is_triggered = True
            logger.debug(f"DynamicSOC: high warning SOC={soc:.1f}%, ratio={ratio:.2f}, P: {p:.1f} → {limited:.1f}")
            return command.with_p(limited)

        # 低側警戒區：漸進限制放電
        if wb > 0 and soc <= soc_min + wb and p > 0:
            ratio = (soc - soc_min) / wb
            limited = p * ratio
            self._is_triggered = True
            logger.debug(f"DynamicSOC: low warning SOC={soc:.1f}%, ratio={ratio:.2f}, P: {p:.1f} → {limited:.1f}")
            return command.with_p(limited)

        self._is_triggered = False
        return command


# =============== Grid Limit Protection ===============


class GridLimitProtection(ProtectionRule):
    """
    外部功率限制保護

    讀取 RuntimeParameters 中的功率限制百分比，計算上限：
        max_p = total_rated_kw × limit_pct / 100

    正負 P 均受限制，clamp 至 [-max_p, +max_p]。

    RuntimeParameters keys:
        grid_limit_pct: 功率限制百分比（0~100），預設 100（無限制）

    Args:
        params: RuntimeParameters 實例
        total_rated_kw: 系統額定功率 (kW)
        limit_key: limit_pct 在 params 中的 key
    """

    def __init__(
        self,
        params: RuntimeParameters,
        total_rated_kw: float,
        limit_key: str = "grid_limit_pct",
    ) -> None:
        self._params = params
        self._rated = total_rated_kw
        self._limit_key = limit_key
        self._is_triggered = False

    @property
    def name(self) -> str:
        return "grid_limit_protection"

    @property
    def is_triggered(self) -> bool:
        return self._is_triggered

    def evaluate(self, command: Command, context: StrategyContext) -> Command:
        pct = float(self._params.get(self._limit_key, 100))
        max_p = self._rated * pct / 100.0
        p = command.p_target

        if p > max_p:
            self._is_triggered = True
            logger.warning(f"GridLimit: discharge over limit={pct:.0f}%, P: {p:.1f} → {max_p:.1f}")
            return command.with_p(max_p)

        if p < -max_p:
            self._is_triggered = True
            logger.warning(f"GridLimit: charge over limit={pct:.0f}%, P: {p:.1f} → {-max_p:.1f}")
            return command.with_p(-max_p)

        self._is_triggered = False
        return command


# =============== Ramp Stop Protection (Deprecated) ===============
# 建議改用 csp_lib.controller.strategies.RampStopStrategy + EventDrivenOverride
# RampStop 本質上是「接管控制」而非「修改數值」，更適合作為 Strategy。


class RampStopProtection(ProtectionRule):
    """
    斜坡停機保護

    當 RuntimeParameters 中的觸發旗標為 True 時，
    從上次保護後的實際功率出發，按斜率逐步降至 0。

    ramp_step = ramp_rate(%) / 100 × total_rated_kw × interval_seconds

    起點為 context.last_command.p_target（上次保護後實際送出的 P）。

    RuntimeParameters keys:
        trigger_key: 觸發旗標 (bool/int)，預設 "battery_status"
        ramp_rate_key: 斜率百分比 (%/s)，預設 "ramp_rate"

    Args:
        params: RuntimeParameters 實例
        total_rated_kw: 系統額定功率 (kW)
        interval_seconds: 控制週期（秒），用於計算每步降幅
        trigger_key: 觸發旗標的 key
        trigger_value: 觸發值（預設 1，與 battery_status=1 對應）
        ramp_rate_key: 斜率的 key
        default_ramp_rate: 無 key 時的預設斜率（%/s）
    """

    def __init__(
        self,
        params: RuntimeParameters,
        total_rated_kw: float,
        interval_seconds: float = 0.3,
        trigger_key: str = "battery_status",
        trigger_value: int = 1,
        ramp_rate_key: str = "ramp_rate",
        default_ramp_rate: float = 5.0,
    ) -> None:
        self._params = params
        self._rated = total_rated_kw
        self._interval = interval_seconds
        self._trigger_key = trigger_key
        self._trigger_value = trigger_value
        self._ramp_rate_key = ramp_rate_key
        self._default_ramp_rate = default_ramp_rate
        self._is_triggered = False

    @property
    def name(self) -> str:
        return "ramp_stop_protection"

    @property
    def is_triggered(self) -> bool:
        return self._is_triggered

    def evaluate(self, command: Command, context: StrategyContext) -> Command:
        trigger = self._params.get(self._trigger_key, 0)
        if trigger != self._trigger_value:
            self._is_triggered = False
            return command

        self._is_triggered = True

        # 以上次保護後的 P 為起點斜坡降至 0
        current_p = context.last_command.p_target
        ramp_rate = float(self._params.get(self._ramp_rate_key, self._default_ramp_rate))
        ramp_step = ramp_rate / 100.0 * self._rated * self._interval

        if abs(current_p) <= ramp_step:
            target_p = 0.0
        elif current_p > 0:
            target_p = current_p - ramp_step
        else:
            target_p = current_p + ramp_step

        logger.debug(
            f"RampStop: triggered, current_p={current_p:.1f}kW, "
            f"ramp_step={ramp_step:.1f}kW, target={target_p:.1f}kW"
        )
        return command.with_p(target_p)


__all__ = [
    "DynamicSOCProtection",
    "GridLimitProtection",
    "RampStopProtection",
]
