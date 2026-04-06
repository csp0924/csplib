"""
Example 11: CascadingStrategy — 級聯功率分配策略深入示範

Demonstrates:
  - CascadingStrategy: delta-based clamping 的運作原理
  - Multi-layer allocation: PQ (高優先) + QV (低優先) 容量分配
  - Capacity constraint: S² = P² + Q² ≤ S_max² 的視在功率限制
  - Context propagation: remaining_s_kva 如何在層間傳遞
  - Edge cases: 超容量、零容量、單層等情境

Scenario:
  A 1MW ESS site with two concurrent control objectives:
    - PQ Mode (Layer 1, high priority): 維持 P=600kW 有功輸出
    - QV Mode (Layer 2, low priority): 根據電壓偏差調節 Q
    - System capacity: S_max = 1000 kVA

  CascadingStrategy 確保：
    1. PQ 的分配永遠被保護（不會因 QV 而被縮減）
    2. QV 只能使用 PQ 佔用後的剩餘容量
    3. 總功率滿足 √(P² + Q²) ≤ 1000 kVA

Architecture:
  ContextBuilder.build() → StrategyContext
       ↓
  CascadingStrategy.execute(context)
       ├─ Layer 1 (PQ): execute → P=600, Q=0
       │   accumulated = Command(P=600, Q=0)
       │   S_used = 600, remaining = 400
       ├─ Layer 2 (QV): execute → P=600, Q=250 (wants more)
       │   delta_p=0, delta_q=250
       │   new_S = √(600² + 250²) = 650 ≤ 1000 ✓
       │   accumulated = Command(P=600, Q=250)
       └─ Final output: Command(P=600, Q=250)

  If QV wants Q=900:
       │   delta_q=900, new_S = √(600² + 900²) = 1082 > 1000
       │   → delta clamped: scale = 0.889, Q ≈ 800
       └─ Final output: Command(P=600, Q=800)
"""

import math

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext, SystemBase
from csp_lib.controller.system.cascading import CapacityConfig, CascadingStrategy

# ============================================================
# Step 1: Define Strategies
# ============================================================


class SimplePQStrategy(Strategy):
    """固定 P/Q 輸出策略"""

    def __init__(self, p: float = 0.0, q: float = 0.0):
        self._p = p
        self._q = q

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command(p_target=self._p, q_target=self._q)

    def __str__(self) -> str:
        return f"PQ(P={self._p}, Q={self._q})"


class SimpleQVStrategy(Strategy):
    """簡化的 QV 策略：根據電壓偏差計算 Q"""

    def __init__(self, nominal_voltage: float = 380.0, q_gain: float = 5.0):
        self._nominal = nominal_voltage
        self._q_gain = q_gain

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        voltage = context.extra.get("voltage", self._nominal)
        v_error = (self._nominal - voltage) / self._nominal
        q_target = v_error * self._q_gain * 1000  # Scale to kVar

        # 保持 P 不變
        return Command(p_target=context.last_command.p_target, q_target=q_target)

    def __str__(self) -> str:
        return f"QV(V_nom={self._nominal}, gain={self._q_gain})"


# ============================================================
# Step 2: Demo Scenarios
# ============================================================


def demo_basic_cascading():
    """基本級聯示範：PQ + QV 在容量限制下"""
    print("=" * 60)
    print("Demo 1: Basic Cascading (PQ + QV)")
    print("=" * 60)

    pq = SimplePQStrategy(p=600.0, q=0.0)
    qv = SimpleQVStrategy(nominal_voltage=380.0, q_gain=5.0)

    cascading = CascadingStrategy(
        layers=[pq, qv],
        capacity=CapacityConfig(s_max_kva=1000.0),
    )

    # 場景 1：電壓正常 → QV Q≈0
    ctx_normal = StrategyContext(
        system_base=SystemBase(p_base=1000.0, q_base=500.0),
        extra={"voltage": 380.0},
    )
    result = cascading.execute(ctx_normal)
    s = math.hypot(result.p_target, result.q_target)
    print("\n  Voltage=380V (normal):")
    print(f"    Output: {result}")
    print(f"    S = {s:.1f} kVA (limit: 1000)")

    # 場景 2：電壓偏低 → QV 要求 Q
    ctx_low_v = StrategyContext(
        system_base=SystemBase(p_base=1000.0, q_base=500.0),
        extra={"voltage": 370.0},
    )
    result = cascading.execute(ctx_low_v)
    s = math.hypot(result.p_target, result.q_target)
    print("\n  Voltage=370V (low):")
    print(f"    Output: {result}")
    print(f"    S = {s:.1f} kVA (limit: 1000)")

    # 場景 3：電壓嚴重偏低 → QV 要求大量 Q → delta clamping
    ctx_very_low = StrategyContext(
        system_base=SystemBase(p_base=1000.0, q_base=500.0),
        extra={"voltage": 300.0},
    )
    result = cascading.execute(ctx_very_low)
    s = math.hypot(result.p_target, result.q_target)
    print("\n  Voltage=300V (very low, QV wants large Q):")
    print(f"    Output: {result}")
    print(f"    S = {s:.1f} kVA (limit: 1000)")
    print("    P preserved at 600kW [OK]" if abs(result.p_target - 600.0) < 0.1 else "    P changed!")
    print("    Q clamped to fit S <= 1000" if s <= 1000.1 else "    S EXCEEDED!")


def demo_delta_clamping_detail():
    """詳細展示 delta-based clamping 計算過程"""
    print("\n" + "=" * 60)
    print("Demo 2: Delta-Based Clamping Detail")
    print("=" * 60)

    # Layer 1: P=800kW（佔用大量容量）
    # Layer 2: Q=900kVar（需要 clamping）
    pq = SimplePQStrategy(p=800.0, q=0.0)
    qv = SimplePQStrategy(p=800.0, q=900.0)  # 注意：同時輸出 P 和 Q

    cascading = CascadingStrategy(
        layers=[pq, qv],
        capacity=CapacityConfig(s_max_kva=1000.0),
    )

    ctx = StrategyContext()
    result = cascading.execute(ctx)
    s = math.hypot(result.p_target, result.q_target)

    print("\n  Layer 1 (PQ): P=800, Q=0 -> accumulated P=800, Q=0, S=800")
    print("  Layer 2 wants: P=800, Q=900 -> delta_p=0, delta_q=900")
    print(f"  Without clamping: S = sqrt(800^2 + 900^2) = {math.hypot(800, 900):.1f} > 1000")
    print(f"  After clamping: {result}")
    print(f"  Final S = {s:.1f} kVA ~ 1000")
    print("  P still 800kW [OK] (high-priority layer protected)")


def demo_three_layers():
    """三層級聯：PQ + QV + 額外功率限制"""
    print("\n" + "=" * 60)
    print("Demo 3: Three-Layer Cascading")
    print("=" * 60)

    layer1 = SimplePQStrategy(p=400.0, q=0.0)  # 基礎有功
    layer2 = SimplePQStrategy(p=400.0, q=300.0)  # 加入無功
    layer3 = SimplePQStrategy(p=600.0, q=300.0)  # 嘗試增加有功

    cascading = CascadingStrategy(
        layers=[layer1, layer2, layer3],
        capacity=CapacityConfig(s_max_kva=800.0),
    )

    ctx = StrategyContext()
    result = cascading.execute(ctx)
    s = math.hypot(result.p_target, result.q_target)

    print("\n  Capacity: 800 kVA")
    print("  Layer 1: P=400, Q=0   -> S=400")
    print("  Layer 2: +Q=300        -> S=500 <= 800 [OK]")
    print("  Layer 3: +P=200        -> S=671 <= 800 [OK]")
    print(f"  Result: {result}")
    print(f"  Final S = {s:.1f} kVA")


def demo_edge_cases():
    """邊緣案例"""
    print("\n" + "=" * 60)
    print("Demo 4: Edge Cases")
    print("=" * 60)

    # Case 1: 空層列表
    empty_cascading = CascadingStrategy(layers=[], capacity=CapacityConfig(s_max_kva=1000.0))
    ctx = StrategyContext(last_command=Command(p_target=100.0, q_target=50.0))
    result = empty_cascading.execute(ctx)
    print(f"\n  Empty layers: preserves last_command -> {result}")

    # Case 2: 單層
    single = CascadingStrategy(
        layers=[SimplePQStrategy(p=500.0, q=300.0)],
        capacity=CapacityConfig(s_max_kva=1000.0),
    )
    result = single.execute(StrategyContext())
    print(f"  Single layer: no clamping needed -> {result}")

    # Case 3: 超過容量的單層
    over = CascadingStrategy(
        layers=[SimplePQStrategy(p=800.0, q=800.0)],
        capacity=CapacityConfig(s_max_kva=1000.0),
    )
    result = over.execute(StrategyContext())
    s = math.hypot(result.p_target, result.q_target)
    print(f"  Single layer over capacity: {result}, S={s:.1f}")

    # Case 4: Zero delta (Layer 2 = Layer 1 output)
    same = CascadingStrategy(
        layers=[SimplePQStrategy(p=500.0, q=0.0), SimplePQStrategy(p=500.0, q=0.0)],
        capacity=CapacityConfig(s_max_kva=1000.0),
    )
    result = same.execute(StrategyContext())
    print(f"  Zero delta (same output): {result}")


def demo_hierarchical_preview():
    """預覽：階層控制概念（SubExecutorAgent 介面）"""
    print("\n" + "=" * 60)
    print("Demo 5: Hierarchical Control Preview")
    print("=" * 60)

    from csp_lib.integration.hierarchical import DispatchCommand, ExecutorStatus, StatusReport, SubExecutorAgent

    # 展示 SubExecutorAgent 為 runtime_checkable Protocol
    print(f"\n  SubExecutorAgent is runtime_checkable: {hasattr(SubExecutorAgent, '__protocol_attrs__')}")

    # 展示 DispatchCommand 序列化
    cmd = DispatchCommand(
        source_site_id="scada_01",
        target_site_id="site_bms",
        command=Command(p_target=500.0, q_target=100.0),
    )
    serialized = cmd.to_dict()
    print("\n  DispatchCommand serialization:")
    print(f"    source: {serialized['source_site_id']}")
    print(f"    target: {serialized['target_site_id']}")
    print(f"    command: P={serialized['command']['p_target']}kW, Q={serialized['command']['q_target']}kVar")
    print(f"    priority: {serialized['priority']}")

    # 反序列化
    restored = DispatchCommand.from_dict(serialized)
    print(f"\n  Roundtrip: {restored.command}")
    assert restored.command.p_target == cmd.command.p_target
    assert restored.command.q_target == cmd.command.q_target
    print("    Roundtrip verified [OK]")

    # 展示 StatusReport
    report = StatusReport(
        site_id="site_bms",
        status=ExecutorStatus(
            strategy_name="cascading(pq+qv)",
            last_command=Command(p_target=600.0, q_target=250.0),
            active_overrides=(),
            base_modes=("pq", "qv"),
            is_running=True,
            device_count=3,
            healthy_device_count=3,
        ),
        metrics={"soc": 75.0, "voltage": 378.5},
    )
    report_dict = report.to_dict()
    restored_report = StatusReport.from_dict(report_dict)
    print("\n  StatusReport roundtrip:")
    print(f"    site: {restored_report.site_id}")
    print(f"    strategy: {restored_report.status.strategy_name}")
    print(f"    command: {restored_report.status.last_command}")
    print(f"    modes: {restored_report.status.base_modes}")
    print(f"    metrics: SOC={restored_report.metrics.get('soc')}%")
    print("    Roundtrip verified [OK]")


# ============================================================
# Main
# ============================================================


def main():
    print("CascadingStrategy Deep Dive — Delta-Based Clamping\n")

    demo_basic_cascading()
    demo_delta_clamping_detail()
    demo_three_layers()
    demo_edge_cases()
    demo_hierarchical_preview()

    print("\n" + "=" * 60)
    print("All demos completed successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
