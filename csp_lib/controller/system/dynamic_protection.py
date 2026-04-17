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

from csp_lib.controller.core import Command, StrategyContext, is_no_change
from csp_lib.core import get_logger
from csp_lib.core._numeric import clamp, is_non_finite_float

from .protection import ProtectionRule, SOCProtectionConfig

if TYPE_CHECKING:
    from csp_lib.core.runtime_params import RuntimeParameters

logger = get_logger(__name__)


# =============== Dynamic SOC Protection ===============


class DynamicSOCProtection(ProtectionRule):
    """
    動態 SOC 保護

    支援兩種參數來源：

    1. **RuntimeParameters**（動態）：每次 evaluate() 從 RuntimeParameters 讀取
       soc_max / soc_min，支援即時更新（如來自 EMS/Modbus 的寫入）。
    2. **SOCProtectionConfig**（靜態）：從 frozen dataclass 讀取固定的
       soc_high / soc_low / warning_band，取代已棄用的 SOCProtection。

    P > 0 = 放電；P < 0 = 充電

    RuntimeParameters keys (僅 RuntimeParameters 模式):
        soc_max: SOC 上限（%），預設 95.0
        soc_min: SOC 下限（%），預設 5.0

    Args:
        params: RuntimeParameters 或 SOCProtectionConfig 實例
        soc_max_key: soc_max 在 RuntimeParameters 中的 key（SOCProtectionConfig 模式忽略）
        soc_min_key: soc_min 在 RuntimeParameters 中的 key（SOCProtectionConfig 模式忽略）
        warning_band: 警戒區寬度（%），0 = 不啟用漸進限制（SOCProtectionConfig 模式使用 config 值）
    """

    def __init__(
        self,
        params: RuntimeParameters | SOCProtectionConfig,
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

    def _resolve_limits(self) -> tuple[float, float, float]:
        """Resolve soc_max, soc_min, warning_band from the parameter source."""
        if isinstance(self._params, SOCProtectionConfig):
            soc_max = self._params.soc_high
            soc_min = self._params.soc_low
            wb = self._params.warning_band
        else:
            # RuntimeParameters path
            soc_max = float(self._params.get(self._soc_max_key, 95.0))
            soc_min = float(self._params.get(self._soc_min_key, 5.0))
            wb = self._warning_band

        # SEC-013a + SEC-004：先驗證非有限值（NaN/Inf clamp 後仍是 NaN/Inf，
        # 後續 BUG-003 的 < 比較對 NaN 永遠 False，會無聲繞過反轉檢查與
        # SOC 保護。必須在 clamp 前明確攔截）。
        if is_non_finite_float(soc_max) or is_non_finite_float(soc_min):
            raise ValueError(
                f"DynamicSOC: soc_max ({soc_max}) / soc_min ({soc_min}) 含 NaN/Inf — "
                f"無效配置，請檢查 RuntimeParameters '{self._soc_max_key}' / '{self._soc_min_key}'"
            )

        # SEC-004：SOC 百分比物理合理範圍為 [0, 100]，clamp 以防 EMS/Modbus
        # 寫入異常值（如 soc_max=150 會讓上限保護永不觸發，可能過充）。
        soc_max = clamp(soc_max, 0.0, 100.0)
        soc_min = clamp(soc_min, 0.0, 100.0)

        # BUG-003：若使用者誤設 soc_max < soc_min（反轉配置），明確拋錯。
        # 不自動 swap：配置錯誤靜默運作會掩蓋問題，使用者無從察覺，
        # 應由 ProtectionGuard 上層捕捉並記錄，由配置端修正。
        if soc_max < soc_min:
            raise ValueError(
                f"DynamicSOC: soc_max ({soc_max}) < soc_min ({soc_min}) — "
                f"無效的反轉配置，請檢查 RuntimeParameters '{self._soc_max_key}' / '{self._soc_min_key}'"
            )

        return soc_max, soc_min, wb

    def evaluate(self, command: Command, context: StrategyContext) -> Command:
        soc = context.soc
        if soc is None:
            self._is_triggered = False
            return command

        # NO_CHANGE：策略不變更 P 軸，SOC 保護不介入
        if is_no_change(command.p_target):
            self._is_triggered = False
            return command

        # SEC-013a L4：soc 為非有限 float（NaN/Inf）視同資料不可用，
        # 沿用上次 is_triggered 值並 passthrough command。
        # 不強制觸發保護（避免通訊瞬態 NaN 造成功率閃爍），
        # 也不重置為 False（避免上層誤判保護解除）。
        if is_non_finite_float(soc):
            return command

        soc_max, soc_min, wb = self._resolve_limits()
        p: float = command.p_target

        # SOC 過高：禁止充電
        if soc >= soc_max:
            if p < 0:
                self._is_triggered = True
                logger.warning(f"DynamicSOC: SOC={soc:.1f}% >= {soc_max}%, block charging, P: {p:.1f} → 0")
                return command.with_p(0.0)
            self._is_triggered = False
            return command

        # SOC 過低：禁止放電
        if soc <= soc_min:
            if p > 0:
                self._is_triggered = True
                logger.warning(f"DynamicSOC: SOC={soc:.1f}% <= {soc_min}%, block discharging, P: {p:.1f} → 0")
                return command.with_p(0.0)
            self._is_triggered = False
            return command

        # 高側警戒區：漸進限制充電
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
        # NO_CHANGE：策略不變更 P 軸，功率限制不介入
        if is_no_change(command.p_target):
            self._is_triggered = False
            return command

        pct_raw = self._params.get(self._limit_key, 100)

        # SEC-013a L4：grid_limit_pct 為非有限 float → 視同資料不可用，
        # 沿用上次 is_triggered 並 passthrough。避免 max_p=NaN 造成比較恆 False
        # 把 is_triggered 無聲重置為 False。
        if is_non_finite_float(pct_raw):
            return command

        pct = float(pct_raw)
        # SEC-004：grid_limit_pct 物理合理範圍為 [0, 100]，clamp 以防
        # 上越界（pct=250 讓 max_p 超過額定）或下越界（pct=-50 讓放電變充電）。
        pct = clamp(pct, 0.0, 100.0)
        max_p = self._rated * pct / 100.0
        p: float = command.p_target

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

        # 以上次保護後的 P 為起點斜坡降至 0（NO_CHANGE 降級為 0.0）
        current_p = context.last_command.effective_p(0.0)
        ramp_rate = float(self._params.get(self._ramp_rate_key, self._default_ramp_rate))
        ramp_step = ramp_rate / 100.0 * self._rated * self._interval

        if abs(current_p) <= ramp_step:
            target_p = 0.0
        elif current_p > 0:
            target_p = current_p - ramp_step
        else:
            target_p = current_p + ramp_step

        logger.debug(
            f"RampStop: triggered, current_p={current_p:.1f}kW, ramp_step={ramp_step:.1f}kW, target={target_p:.1f}kW"
        )
        return command.with_p(target_p)


__all__ = [
    "DynamicSOCProtection",
    "GridLimitProtection",
    "RampStopProtection",
]
