"""
Example 03: Control Strategies — 控制策略

Demonstrates:
  - Built-in strategies: PQ, QV, FP
  - StrategyExecutor with context_provider and on_command callback
  - ExecutionMode: PERIODIC, TRIGGERED, HYBRID
  - SystemBase for percent-to-kW conversion
  - Dynamic config update

This example runs strategies against simulated context data (no real devices).
"""

import asyncio
from datetime import datetime, timezone

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, StrategyContext, SystemBase
from csp_lib.controller.executor import StrategyExecutor
from csp_lib.controller.strategies import (
    FPConfig,
    FPStrategy,
    PQModeConfig,
    PQModeStrategy,
    QVConfig,
    QVStrategy,
    StopStrategy,
)

# ============================================================
# Example A: PQ Mode — Fixed Power Output (固定功率模式)
# ============================================================


def example_pq_strategy():
    """PQ mode outputs a fixed P and Q."""
    print("=== PQ Mode Strategy ===")

    config = PQModeConfig(p=50.0, q=10.0)
    strategy = PQModeStrategy(config)

    # Execute with a simple context
    context = StrategyContext(soc=80.0)
    command = strategy.execute(context)
    print(f"Command: P={command.p_target} kW, Q={command.q_target} kVar")
    # → P=50.0 kW, Q=10.0 kVar

    # Dynamic reconfiguration (e.g., SCADA sends new setpoint)
    strategy.update_config(PQModeConfig(p=75.0, q=-20.0))
    command = strategy.execute(context)
    print(f"Updated: P={command.p_target} kW, Q={command.q_target} kVar")
    # → P=75.0 kW, Q=-20.0 kVar


# ============================================================
# Example B: QV Strategy — Voltage-Reactive Power (電壓無功控制)
# ============================================================


def example_qv_strategy():
    """QV strategy adjusts Q based on voltage deviation."""
    print("\n=== QV Strategy ===")

    config = QVConfig(
        nominal_voltage=380.0,  # 額定電壓 (V)
        v_set=100.0,  # 電壓設定值 (%)
        droop=5.0,  # 下垂係數 (%)
        v_deadband=0.0,  # 死區 (%)
        q_max_ratio=0.5,  # Q 最大比值
    )
    strategy = QVStrategy(config)

    # System base for percent → kVar conversion
    system_base = SystemBase(p_base=100.0, q_base=100.0)

    # Voltage too low → output positive Q (provide reactive power)
    context = StrategyContext(system_base=system_base, extra={"voltage": 370.0})
    command = strategy.execute(context)
    print(f"V=370V → Q={command.q_target:.1f} kVar (inject reactive)")

    # Voltage normal → Q ≈ 0
    context = StrategyContext(system_base=system_base, extra={"voltage": 380.0})
    command = strategy.execute(context)
    print(f"V=380V → Q={command.q_target:.1f} kVar (normal)")

    # Voltage too high → output negative Q (absorb reactive)
    context = StrategyContext(system_base=system_base, extra={"voltage": 395.0})
    command = strategy.execute(context)
    print(f"V=395V → Q={command.q_target:.1f} kVar (absorb reactive)")


# ============================================================
# Example C: FP Strategy — Frequency-Power (頻率功率控制 / AFC)
# ============================================================


def example_fp_strategy():
    """FP strategy (AFC) adjusts P based on frequency deviation."""
    print("\n=== FP Strategy (AFC) ===")

    # 6-point piecewise linear: frequency → power %
    config = FPConfig(
        f1=59.0,
        p1=100.0,  # f ≤ 59 Hz → 100% discharge
        f2=59.5,
        p2=50.0,  # f = 59.5 Hz → 50% discharge
        f3=59.98,
        p3=0.0,  # f = 59.98 Hz → 0% (deadband lower)
        f4=60.02,
        p4=0.0,  # f = 60.02 Hz → 0% (deadband upper)
        f5=60.5,
        p5=-50.0,  # f = 60.5 Hz → 50% charge
        f6=61.0,
        p6=-100.0,  # f ≥ 61 Hz → 100% charge
    )
    strategy = FPStrategy(config)

    system_base = SystemBase(p_base=100.0, q_base=50.0)

    for freq in [58.5, 59.5, 60.0, 60.5, 61.5]:
        context = StrategyContext(system_base=system_base, extra={"frequency": freq})
        command = strategy.execute(context)
        print(f"f={freq:5.1f} Hz → P={command.p_target:7.1f} kW")


# ============================================================
# Example D: StrategyExecutor — Running a Strategy Loop
# ============================================================


async def example_executor():
    """StrategyExecutor manages the periodic execution loop."""
    print("\n=== StrategyExecutor ===")

    # Simulated sensor data (changes over time)
    cycle = {"count": 0}

    def context_provider() -> StrategyContext:
        """Called each cycle to build fresh context from device values."""
        cycle["count"] += 1
        return StrategyContext(
            soc=80.0,
            system_base=SystemBase(p_base=100.0, q_base=50.0),
            extra={"voltage": 375.0 + cycle["count"] * 2},
        )

    async def on_command(command: Command) -> None:
        """Called after each strategy execution — send to devices."""
        print(f"  Cycle {cycle['count']}: P={command.p_target:.1f} kW, Q={command.q_target:.1f} kVar")

    # Create executor
    executor = StrategyExecutor(
        context_provider=context_provider,
        on_command=on_command,
    )

    # Set initial strategy
    strategy = QVStrategy(QVConfig(nominal_voltage=380.0, droop=5.0))
    await executor.set_strategy(strategy)

    # Run in background
    task = asyncio.create_task(executor.run())

    # Let it run for a few cycles
    await asyncio.sleep(3.5)

    # Switch strategy mid-flight
    print("  --- Switching to PQ mode ---")
    pq = PQModeStrategy(PQModeConfig(p=60.0, q=0.0))
    await executor.set_strategy(pq)

    await asyncio.sleep(2.5)

    # Stop
    executor.stop()
    await task

    print(f"  Final command: {executor.last_command}")


# ============================================================
# Example E: Execution Modes
# ============================================================


def example_execution_modes():
    """Show the three execution modes."""
    print("\n=== Execution Modes ===")

    # PERIODIC: runs every N seconds (most strategies)
    pq = PQModeStrategy()
    print(f"PQ: mode={pq.execution_config.mode.name}, interval={pq.execution_config.interval_seconds}s")

    # TRIGGERED: only runs when executor.trigger() is called
    from csp_lib.controller.strategies import BypassStrategy

    bypass = BypassStrategy()
    print(f"Bypass: mode={bypass.execution_config.mode.name}")

    # HYBRID: periodic + can be triggered early
    hybrid_config = ExecutionConfig(mode=ExecutionMode.HYBRID, interval_seconds=5)
    print(f"Custom hybrid: mode={hybrid_config.mode.name}, interval={hybrid_config.interval_seconds}s")


# ============================================================
# Run All Examples
# ============================================================


async def main():
    example_pq_strategy()
    example_qv_strategy()
    example_fp_strategy()
    await example_executor()
    example_execution_modes()


if __name__ == "__main__":
    asyncio.run(main())
