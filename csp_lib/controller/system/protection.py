# =============== Protection Guard ===============
#
# 保護規則與保護鏈
#
# 保護規則：
#   - SOCProtection: SOC 保護（高限禁充、低限禁放、警戒區漸進限制）
#   - ReversePowerProtection: 表後逆送保護
#   - SystemAlarmProtection: 系統告警保護（強制 P=0, Q=0）
#
# 保護鏈：
#   - ProtectionGuard: 鏈式套用所有規則

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from csp_lib.controller.core import Command, StrategyContext, is_no_change
from csp_lib.core import get_logger
from csp_lib.core._numeric import is_non_finite_float

logger = get_logger("csp_lib.controller.system.protection")


# =============== Abstract Rule ===============


class ProtectionRule(ABC):
    """保護規則抽象基礎類別"""

    @property
    @abstractmethod
    def name(self) -> str:
        """規則名稱"""

    @abstractmethod
    def evaluate(self, command: Command, context: StrategyContext) -> Command:
        """
        評估並可能修改命令

        Args:
            command: 原始命令
            context: 策略上下文

        Returns:
            保護後的命令（可能與原始相同）
        """

    @property
    @abstractmethod
    def is_triggered(self) -> bool:
        """該規則是否處於觸發狀態（診斷用）"""


# =============== SOC Protection ===============


@dataclass(frozen=True, slots=True)
class SOCProtectionConfig:
    """
    SOC 保護配置

    Attributes:
        soc_high: SOC 上限（%），達到時禁止充電
        soc_low: SOC 下限（%），達到時禁止放電
        warning_band: 警戒區寬度（%），進入時漸進限制
    """

    soc_high: float = 95.0
    soc_low: float = 5.0
    warning_band: float = 5.0


class SOCProtection(ProtectionRule):
    """
    SOC 保護

    P > 0 = 放電，P < 0 = 充電

    - SOC >= soc_high: 禁止充電 → clamp P >= 0
    - SOC <= soc_low: 禁止放電 → clamp P <= 0
    - 警戒區漸進限制: ratio = 距離上下限的比例
    - SOC 為 None 時不介入
    """

    def __init__(self, config: SOCProtectionConfig | None = None) -> None:
        warnings.warn(
            "SOCProtection is deprecated, use DynamicSOCProtection with SOCProtectionConfig instead",
            DeprecationWarning,
            stacklevel=2,
        )
        self._config = config or SOCProtectionConfig()
        self._is_triggered = False

    @property
    def name(self) -> str:
        return "soc_protection"

    @property
    def is_triggered(self) -> bool:
        return self._is_triggered

    def evaluate(self, command: Command, context: StrategyContext) -> Command:
        soc = context.soc
        if soc is None:
            self._is_triggered = False
            return command

        # NO_CHANGE：策略不變更 P 軸，SOC 保護不介入（設備保留上次實際功率）
        if is_no_change(command.p_target):
            self._is_triggered = False
            return command

        # SEC-013a L4：soc 為非有限 float（NaN/Inf）視同資料不可用，
        # 沿用上次 is_triggered 並 passthrough（參考 DynamicSOCProtection 的設計）。
        if is_non_finite_float(soc):
            return command

        cfg = self._config
        p: float = command.p_target

        # SOC 過高：禁止充電（P < 0 為充電）
        if soc >= cfg.soc_high:
            if p < 0:
                self._is_triggered = True
                logger.warning(f"SOC protection: SOC={soc}% >= {cfg.soc_high}%, clamp P from {p} to 0 (no charging)")
                return command.with_p(0.0)
            self._is_triggered = False
            return command

        # SOC 過低：禁止放電（P > 0 為放電）
        if soc <= cfg.soc_low:
            if p > 0:
                self._is_triggered = True
                logger.warning(f"SOC protection: SOC={soc}% <= {cfg.soc_low}%, clamp P from {p} to 0 (no discharging)")
                return command.with_p(0.0)
            self._is_triggered = False
            return command

        # 高側警戒區：漸進限制充電
        warning_high = cfg.soc_high - cfg.warning_band
        if soc >= warning_high and cfg.warning_band > 0:
            if p < 0:
                # ratio: 1.0 (在 warning_high) → 0.0 (在 soc_high)
                ratio = (cfg.soc_high - soc) / cfg.warning_band
                limited_p = p * ratio
                self._is_triggered = True
                logger.debug(f"SOC protection: high warning zone SOC={soc}%, ratio={ratio:.2f}, P: {p} -> {limited_p}")
                return command.with_p(limited_p)

        # 低側警戒區：漸進限制放電
        warning_low = cfg.soc_low + cfg.warning_band
        if soc <= warning_low and cfg.warning_band > 0:
            if p > 0:
                # ratio: 1.0 (在 warning_low) → 0.0 (在 soc_low)
                ratio = (soc - cfg.soc_low) / cfg.warning_band
                limited_p = p * ratio
                self._is_triggered = True
                logger.debug(f"SOC protection: low warning zone SOC={soc}%, ratio={ratio:.2f}, P: {p} -> {limited_p}")
                return command.with_p(limited_p)

        self._is_triggered = False
        return command


# =============== Reverse Power Protection ===============


class ReversePowerProtection(ProtectionRule):
    """
    表後逆送保護

    meter_power > 0 = 買電（從電網進），< 0 = 賣電（逆送到電網）

    約束: p_target <= meter_power + threshold
    預設 threshold=0（不允許逆送）

    meter_power 從 context.extra["meter_power"] 讀取。
    meter_power 為 None 時不介入。
    """

    def __init__(self, threshold: float = 0.0, meter_power_key: str = "meter_power") -> None:
        self._threshold = threshold
        self._meter_power_key = meter_power_key
        self._is_triggered = False

    @property
    def name(self) -> str:
        return "reverse_power_protection"

    @property
    def is_triggered(self) -> bool:
        return self._is_triggered

    def evaluate(self, command: Command, context: StrategyContext) -> Command:
        meter_power = context.extra.get(self._meter_power_key)
        if meter_power is None:
            self._is_triggered = False
            return command

        # NO_CHANGE：策略不變更 P 軸，逆送保護不介入
        if is_no_change(command.p_target):
            self._is_triggered = False
            return command

        # SEC-013a L4：meter_power 為非有限 float（NaN/Inf）視同資料不可用，
        # 沿用上次 is_triggered 並 passthrough。避免 max_discharge=NaN 讓
        # `p > NaN` 恆為 False 把 is_triggered 無聲重置為 False
        # （瞬間通訊 glitch 會誤導上層以為保護解除 → 允許繼續逆送）。
        if is_non_finite_float(meter_power):
            return command

        p: float = command.p_target

        # P < 0 為充電（從電網取電），不受逆送保護限制
        if p < 0:
            self._is_triggered = False
            return command

        # 放電上限 = meter_power + threshold
        max_discharge = meter_power + self._threshold
        if max_discharge < 0:
            max_discharge = 0.0

        if p > max_discharge:
            self._is_triggered = True
            logger.warning(
                f"Reverse power protection: meter={meter_power}, "
                f"clamp P from {p} to {max_discharge} (threshold={self._threshold})"
            )
            return command.with_p(max_discharge)

        self._is_triggered = False
        return command


# =============== System Alarm Protection ===============


class SystemAlarmProtection(ProtectionRule):
    """
    系統告警保護

    context.extra["system_alarm"] == True → 強制 P=0, Q=0
    """

    def __init__(self, alarm_key: str = "system_alarm") -> None:
        self._alarm_key = alarm_key
        self._is_triggered = False

    @property
    def name(self) -> str:
        return "system_alarm_protection"

    @property
    def is_triggered(self) -> bool:
        return self._is_triggered

    def evaluate(self, command: Command, context: StrategyContext) -> Command:
        if context.extra.get(self._alarm_key, False):
            self._is_triggered = True
            logger.warning("System alarm protection: forcing P=0, Q=0")
            return Command(p_target=0.0, q_target=0.0)
        self._is_triggered = False
        return command


# =============== Protection Result ===============


@dataclass(frozen=True, slots=True)
class ProtectionResult:
    """
    保護規則套用結果

    Attributes:
        original_command: 原始命令
        protected_command: 保護後命令
        triggered_rules: 觸發的規則名稱列表
    """

    original_command: Command
    protected_command: Command
    triggered_rules: list[str] = field(default_factory=list)

    @property
    def was_modified(self) -> bool:
        """命令是否被修改"""
        return self.original_command != self.protected_command


# =============== Protection Guard ===============


class ProtectionGuard:
    """
    保護鏈

    鏈式套用所有保護規則，追蹤觸發狀態。
    """

    def __init__(self, rules: list[ProtectionRule] | None = None) -> None:
        self._rules: list[ProtectionRule] = list(rules) if rules else []
        self._last_result: ProtectionResult | None = None

    def add_rule(self, rule: ProtectionRule) -> None:
        """新增保護規則"""
        self._rules.append(rule)

    def remove_rule(self, name: str) -> None:
        """依名稱移除保護規則"""
        self._rules = [r for r in self._rules if r.name != name]

    def apply(self, command: Command, context: StrategyContext) -> ProtectionResult:
        """
        鏈式套用所有保護規則

        Args:
            command: 原始命令
            context: 策略上下文

        Returns:
            ProtectionResult: 保護結果
        """
        original = command
        current = command
        triggered: list[str] = []

        for rule in self._rules:
            try:
                current = rule.evaluate(current, context)
                if rule.is_triggered:
                    triggered.append(rule.name)
            except Exception:
                logger.opt(exception=True).warning(
                    f"Protection rule '{rule.name}' failed, applying fail-safe (P=0, Q=0)"
                )
                current = Command(p_target=0.0, q_target=0.0)
                triggered.append(f"{rule.name}(fail-safe)")

        result = ProtectionResult(
            original_command=original,
            protected_command=current,
            triggered_rules=triggered,
        )
        self._last_result = result

        if result.was_modified:
            logger.info(f"Protection applied: {original} -> {current}, triggered: {triggered}")

        return result

    @property
    def last_result(self) -> ProtectionResult | None:
        """上次套用結果"""
        return self._last_result

    @property
    def rules(self) -> list[ProtectionRule]:
        """所有保護規則"""
        return list(self._rules)
