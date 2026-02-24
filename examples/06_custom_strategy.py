"""
Example 06: Custom Strategy — 自定義策略

Demonstrates:
  - Subclassing Strategy to create a custom control strategy
  - ConfigMixin for frozen config with from_dict() (SCADA-friendly)
  - Stateful PID control across execution cycles
  - on_activate() / on_deactivate() lifecycle hooks for state reset
  - Triggered (event-driven) strategy for load shedding
  - Wiring custom strategies into StrategyExecutor

Scenario A (PF Adjustment):
  A PF correction strategy that uses PID control to maintain a target
  power factor by adjusting reactive power (Q). The PID accumulates
  integral/derivative state across cycles and resets on mode switch.

Scenario B (Load Shedding):
  A trigger-based strategy that sheds load to a target power level.
  Only runs when explicitly triggered (e.g., by a demand response signal).
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from csp_lib.controller.core import (
    Command,
    ConfigMixin,
    ExecutionConfig,
    ExecutionMode,
    Strategy,
    StrategyContext,
    SystemBase,
)
from csp_lib.controller.executor import StrategyExecutor

# ============================================================
# Scenario A: PF Adjustment with PID Control
# ============================================================


@dataclass
class PFConfig(ConfigMixin):
    """
    功率因數校正策略配置

    Attributes:
        target_pf: 目標功率因數 (0.0 ~ 1.0, 正=lagging)
        kp: 比例增益
        ki: 積分增益
        kd: 微分增益
        q_max: Q 輸出上限 (kVar)
        q_min: Q 輸出下限 (kVar)
    """

    target_pf: float = 0.95
    kp: float = 10.0
    ki: float = 2.0
    kd: float = 0.5
    q_max: float = 100.0
    q_min: float = -100.0


class PFAdjustmentStrategy(Strategy):
    """
    功率因數校正策略 (PID-based)

    每個週期讀取當前 PF，通過 PID 控制器計算 Q 輸出，
    使功率因數趨近目標值。

    Required context.extra keys:
        - "power_factor": 當前功率因數 (float)
        - "active_power": 當前有功功率 kW (float, optional, for feedforward)

    PID 狀態在 on_activate() 時重置，確保策略切換後不會
    因為舊的積分殘留而產生突跳。
    """

    def __init__(self, config: PFConfig | None = None) -> None:
        self._config = config or PFConfig()

        # PID state (reset on activate)
        self._integral: float = 0.0
        self._prev_error: float = 0.0
        self._prev_time: datetime | None = None

    @property
    def config(self) -> PFConfig:
        return self._config

    @property
    def execution_config(self) -> ExecutionConfig:
        """每秒執行一次"""
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        """
        PID 控制迴圈

        error = target_pf - current_pf
        Q = Kp * error + Ki * integral(error) + Kd * d(error)/dt
        """
        current_pf = context.extra.get("power_factor")
        if current_pf is None:
            return context.last_command

        cfg = self._config
        error = cfg.target_pf - current_pf

        # Calculate dt
        now = context.current_time or datetime.now(timezone.utc)
        dt = 1.0
        if self._prev_time is not None:
            dt = max((now - self._prev_time).total_seconds(), 0.001)
        self._prev_time = now

        # PID terms
        p_term = cfg.kp * error
        self._integral += error * dt
        i_term = cfg.ki * self._integral
        d_term = cfg.kd * (error - self._prev_error) / dt
        self._prev_error = error

        # Calculate Q output with clamping
        q_output = p_term + i_term + d_term
        q_output = max(cfg.q_min, min(cfg.q_max, q_output))

        # Keep P from last command (PF strategy only adjusts Q)
        return Command(p_target=context.last_command.p_target, q_target=q_output)

    async def on_activate(self) -> None:
        """策略啟用時重置 PID 狀態"""
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None
        print("  [PFAdjustment] PID state reset on activate")

    async def on_deactivate(self) -> None:
        """策略停用時清理"""
        print(f"  [PFAdjustment] Deactivated (final integral={self._integral:.3f})")

    def update_config(self, config: PFConfig) -> None:
        """動態更新配置 (e.g., SCADA 下發新目標 PF)"""
        self._config = config

    def __str__(self) -> str:
        return f"PFAdjustmentStrategy(target_pf={self._config.target_pf})"


# ============================================================
# Scenario B: Load Shedding (Triggered Strategy)
# ============================================================


@dataclass
class LoadShedConfig(ConfigMixin):
    """
    負載削減配置

    Attributes:
        target_power: 目標功率 (kW), 通常為 0 或低值
        ramp_rate: 每次觸發的降載速率 (kW/trigger)
    """

    target_power: float = 0.0
    ramp_rate: float = 50.0


class LoadSheddingStrategy(Strategy):
    """
    負載削減策略 (Triggered)

    僅在外部觸發時執行 (需量反應、電網告警等)。
    每次觸發時，將功率向目標值 ramp 一步。

    Usage:
        executor.set_strategy(shedding)
        executor.trigger()  # 每次觸發降載一步
    """

    def __init__(self, config: LoadShedConfig | None = None) -> None:
        self._config = config or LoadShedConfig()

    @property
    def execution_config(self) -> ExecutionConfig:
        """觸發模式：僅在 trigger() 呼叫時執行"""
        return ExecutionConfig(mode=ExecutionMode.TRIGGERED)

    def execute(self, context: StrategyContext) -> Command:
        cfg = self._config
        current_p = context.last_command.p_target

        # Ramp toward target
        if current_p > cfg.target_power:
            new_p = max(cfg.target_power, current_p - cfg.ramp_rate)
        elif current_p < cfg.target_power:
            new_p = min(cfg.target_power, current_p + cfg.ramp_rate)
        else:
            new_p = cfg.target_power

        return Command(p_target=new_p, q_target=0.0)

    async def on_activate(self) -> None:
        print("  [LoadShedding] Activated — waiting for triggers")

    def __str__(self) -> str:
        return f"LoadSheddingStrategy(target={self._config.target_power}kW)"


# ============================================================
# Run Examples
# ============================================================


async def example_pf_pid():
    """PF adjustment with PID — watch Q converge to target PF."""
    print("=== PF Adjustment with PID Control ===\n")

    # Simulated PF drifting from 0.85 toward 0.95 as Q is applied
    state = {"pf": 0.85, "p": 200.0}

    def context_provider() -> StrategyContext:
        return StrategyContext(
            soc=80.0,
            system_base=SystemBase(p_base=500.0, q_base=250.0),
            extra={"power_factor": state["pf"], "active_power": state["p"]},
        )

    commands = []

    async def on_command(command: Command) -> None:
        commands.append(command)
        # Simulate PF improving as Q is injected
        # (simplified: each 10 kVar of Q improves PF by ~0.01)
        q_effect = command.q_target * 0.001
        state["pf"] = min(1.0, state["pf"] + q_effect)
        print(f"  PF={state['pf']:.3f}  →  Q={command.q_target:+.1f} kVar")

    # Create executor with PF strategy
    executor = StrategyExecutor(context_provider=context_provider, on_command=on_command)
    pf_strategy = PFAdjustmentStrategy(PFConfig(target_pf=0.95, kp=15.0, ki=3.0, kd=0.5))
    await executor.set_strategy(pf_strategy)

    # Run for a few cycles
    task = asyncio.create_task(executor.run())
    await asyncio.sleep(5.5)

    # Dynamic config update (SCADA changes target PF)
    print("\n  --- SCADA: target PF changed to 0.98 ---")
    pf_strategy.update_config(PFConfig(target_pf=0.98, kp=15.0, ki=3.0, kd=0.5))
    await asyncio.sleep(3.5)

    executor.stop()
    await task

    print(f"\n  Final PF: {state['pf']:.3f}")
    print(f"  Total cycles: {len(commands)}")


async def example_load_shedding():
    """Load shedding — triggered mode with ramping."""
    print("\n=== Load Shedding (Triggered Mode) ===\n")

    # Track current power
    state = {"p": 300.0}

    def context_provider() -> StrategyContext:
        return StrategyContext(soc=50.0)

    async def on_command(command: Command) -> None:
        state["p"] = command.p_target
        print(f"  Power: {command.p_target:.0f} kW")

    executor = StrategyExecutor(context_provider=context_provider, on_command=on_command)

    shedding = LoadSheddingStrategy(LoadShedConfig(target_power=50.0, ramp_rate=80.0))
    await executor.set_strategy(shedding)

    # Set initial power level (executor tracks last_command internally)
    # We use execute_once() to establish the starting point
    executor._last_command = Command(p_target=300.0)

    # Run executor in background
    task = asyncio.create_task(executor.run())

    # Simulate external triggers (demand response signals)
    print("  Initial: 300 kW → shedding to 50 kW (80 kW/step)")
    for i in range(5):
        await asyncio.sleep(0.5)
        print(f"  --- Trigger #{i + 1} (demand response) ---")
        executor.trigger()
        await asyncio.sleep(0.1)  # Let execution happen

    executor.stop()
    await task

    print(f"\n  Final power: {state['p']:.0f} kW")


async def example_config_from_dict():
    """ConfigMixin: create configs from JSON/dict (SCADA integration)."""
    print("\n=== ConfigMixin: from_dict() ===\n")

    # Simulating SCADA JSON payload
    scada_payload = {"targetPf": 0.97, "kp": 20.0, "ki": 5.0, "kd": 1.0, "qMax": 200.0, "qMin": -200.0}

    # ConfigMixin auto-converts camelCase → snake_case
    config = PFConfig.from_dict(scada_payload)
    print(f"  From SCADA JSON: {config}")
    print(f"  target_pf={config.target_pf}, kp={config.kp}, q_max={config.q_max}")

    # Also works with snake_case keys
    config2 = PFConfig.from_dict({"target_pf": 0.99, "kp": 10.0})
    print(f"  From snake_case: target_pf={config2.target_pf}")

    # to_dict for serialization
    print(f"  to_dict(): {config.to_dict()}")


async def main():
    await example_pf_pid()
    await example_load_shedding()
    await example_config_from_dict()


if __name__ == "__main__":
    asyncio.run(main())
