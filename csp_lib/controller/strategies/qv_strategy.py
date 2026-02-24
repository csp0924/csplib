# =============== QV (Voltage-Reactive Power) Strategy ===============
#
# 電壓-無功功率控制策略
# 根據系統電壓偏差計算無功功率輸出

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from csp_lib.controller.core import (
    Command,
    ConfigMixin,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
)


@dataclass
class QVConfig(ConfigMixin):
    """
    QV 模式配置

    使用下垂控制 (Droop Control) 計算無功功率。

    Attributes:
        nominal_voltage: 額定電壓 (V)
        v_set: 電壓設定值 (%)，預設 100%
        droop: 電壓下垂係數 (%)，預設 5%
        v_deadband: 電壓死區 (%)，預設 0%
        q_max_ratio: 最大無功功率比值，預設 0.5 (50%)
    """

    nominal_voltage: float = 380.0
    v_set: float = 100.0  # 電壓設定值 (%)
    droop: float = 5.0  # 下垂係數 (%)
    v_deadband: float = 0.0  # 死區 (%)
    q_max_ratio: float = 0.5  # Q 最大比值

    def validate(self) -> None:
        """驗證配置有效性"""
        if self.nominal_voltage <= 0:
            raise ValueError("額定電壓必須大於 0")
        if not (95 <= self.v_set <= 105):
            raise ValueError("電壓設定值必須在 95% ~ 105% 之間")
        if not (2 <= self.droop <= 10):
            raise ValueError("下垂係數必須在 2% ~ 10% 之間")
        if not (0 <= self.v_deadband <= 0.5):
            raise ValueError("死區必須在 0% ~ 0.5% 之間")


class QVStrategy(Strategy):
    """
    電壓-無功功率控制策略 (Volt-VAR)

    根據系統電壓偏差，透過下垂控制計算無功功率輸出。
    電壓過低時輸出正 Q (提供無功)，電壓過高時輸出負 Q (吸收無功)。

    計算邏輯:
        V_pu = V_measured / V_nominal
        V_set_pu = V_set / 100

        if V_pu <= V_set_pu - V_deadband:
            Q = min(0.5 * (V_set_pu - V_deadband - V_pu) / (V_set_pu * droop), Q_max)
        elif V_pu >= V_set_pu + V_deadband:
            Q = max(0.5 * (V_set_pu + V_deadband - V_pu) / (V_set_pu * droop), -Q_max)
        else:
            Q = 0 (死區)

    Usage:
        config = QVConfig(nominal_voltage=380, v_set=100, droop=5)
        strategy = QVStrategy(config)
    """

    def __init__(self, config: Optional[QVConfig] = None) -> None:
        self._config = config or QVConfig()

    @property
    def config(self) -> QVConfig:
        """當前配置"""
        return self._config

    @property
    def execution_config(self) -> ExecutionConfig:
        """執行配置: 每秒執行"""
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        """
        執行策略邏輯

        從 context.extra["voltage"] 取得系統電壓，計算無功功率輸出。

        Args:
            context: 策略上下文，需包含 extra["voltage"]

        Returns:
            Command: 計算出的無功功率命令 (比值需由 GridController 轉換)
        """
        voltage = context.extra.get("voltage")
        if voltage is None:
            # 無電壓資料，維持上一次命令
            return context.last_command

        q_ratio = self._calculate_q_ratio(voltage)

        # 轉換為 kVar (使用 system_base)
        if context.system_base is not None:
            q_kvar = context.percent_to_kvar(q_ratio * 100)
        else:
            q_kvar = q_ratio  # 無 system_base 時直接輸出比值

        # 保持 P 不變 (從 last_command)
        return Command(p_target=context.last_command.p_target, q_target=q_kvar)

    def _calculate_q_ratio(self, voltage: float) -> float:
        """根據電壓計算無功功率比值 (-1 ~ 1)"""
        cfg = self._config

        # 轉換為 p.u.
        v_pu = voltage / cfg.nominal_voltage
        v_set_pu = cfg.v_set / 100
        v_deadband_pu = cfg.v_deadband / 100
        droop_pu = cfg.droop / 100

        # 電壓過低: 輸出正 Q (提供無功)
        if v_pu <= v_set_pu - v_deadband_pu:
            q_ratio = 0.5 * (v_set_pu - v_deadband_pu - v_pu) / (v_set_pu * droop_pu)
            return min(q_ratio, cfg.q_max_ratio)

        # 電壓過高: 輸出負 Q (吸收無功)
        if v_pu >= v_set_pu + v_deadband_pu:
            q_ratio = 0.5 * (v_set_pu + v_deadband_pu - v_pu) / (v_set_pu * droop_pu)
            return max(q_ratio, -cfg.q_max_ratio)

        # 死區內: Q = 0
        return 0.0

    def update_config(self, config: QVConfig) -> None:
        """更新配置"""
        self._config = config

    def __str__(self) -> str:
        return f"QVStrategy(V_set={self._config.v_set}%, droop={self._config.droop}%)"
