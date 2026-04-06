"""
csp_lib Example 07: 多機功率分配 — PowerDistributor

學習目標：
  - ProportionalDistributor — 按額定容量比例分配功率
  - SOCBalancingDistributor — SOC 平衡分配（高 SOC 多放、低 SOC 多充）
  - CascadingStrategy — 多策略級聯（PQ+QV 在同一台設備上組合）
  - 動態分配 — PCS 離線時自動重分配

架構：
  SystemController 產出系統級 Command(P=200kW)
       ↓
  PowerDistributor 分配到 3 台 PCS
       ↓
  PCS_A(100kW) + PCS_B(150kW) + PCS_C(200kW)

Run: uv run python examples/07_cascading_power.py
預計時間: 15 分鐘
"""

import asyncio
import sys

from csp_lib.controller.core import Command
from csp_lib.integration.distributor import (
    DeviceSnapshot,
    EqualDistributor,
    ProportionalDistributor,
    SOCBalancingDistributor,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


async def main() -> None:
    print("=" * 60)
    print("  Example 07: 多機功率分配 — PowerDistributor")
    print("=" * 60)

    # ============================================================
    # Section A: PowerDistributor 獨立展示（不需要 SimulationServer）
    # ============================================================

    # 3 台 PCS，不同額定容量
    devices = [
        DeviceSnapshot(device_id="pcs_a", metadata={"rated_p": 100.0}, latest_values={"soc": 70.0}),
        DeviceSnapshot(device_id="pcs_b", metadata={"rated_p": 150.0}, latest_values={"soc": 50.0}),
        DeviceSnapshot(device_id="pcs_c", metadata={"rated_p": 200.0}, latest_values={"soc": 30.0}),
    ]

    system_command = Command(p_target=200.0, q_target=50.0)
    print(f"\n  系統指令：P={system_command.p_target}kW, Q={system_command.q_target}kVar")
    print("  PCS 額定：A=100kW, B=150kW, C=200kW（總容量 450kW）")

    # ================================================
    # Step 1: EqualDistributor — 均分
    # ================================================
    print("\n=== Step 1: EqualDistributor — 均分 ===")
    equal = EqualDistributor()
    result = equal.distribute(system_command, devices)
    for dev_id, cmd in result.items():
        print(f"  {dev_id}: P={cmd.p_target:.1f}kW, Q={cmd.q_target:.1f}kVar")
    print("  -> 每台分得相同功率，不考慮容量差異")

    # ================================================
    # Step 2: ProportionalDistributor — 按容量比例
    # ================================================
    print("\n=== Step 2: ProportionalDistributor — 按額定容量比例分配 ===")
    proportional = ProportionalDistributor(rated_key="rated_p")
    result = proportional.distribute(system_command, devices)
    total_rated = 100.0 + 150.0 + 200.0
    for dev_id, cmd in result.items():
        rated = next(d.metadata["rated_p"] for d in devices if d.device_id == dev_id)
        print(
            f"  {dev_id} (額定 {rated:.0f}kW, 比例 {rated / total_rated:.1%}): P={cmd.p_target:.1f}kW, Q={cmd.q_target:.1f}kVar"
        )
    print("  -> 按額定容量比例分配，大機器分得多")

    # ================================================
    # Step 3: SOCBalancingDistributor — SOC 平衡
    # ================================================
    print("\n=== Step 3: SOCBalancingDistributor — SOC 平衡分配 ===")
    print("  放電場景（P>0）：SOC 高的多放")
    print("  SOC 狀態：A=70%, B=50%, C=30%（平均 50%）")

    # SOCBalancingDistributor 需要 capability 格式的 SOC
    devices_with_cap = [
        DeviceSnapshot(
            device_id="pcs_a",
            metadata={"rated_p": 100.0},
            capabilities={"soc_readable": {"soc": 70.0}},
        ),
        DeviceSnapshot(
            device_id="pcs_b",
            metadata={"rated_p": 150.0},
            capabilities={"soc_readable": {"soc": 50.0}},
        ),
        DeviceSnapshot(
            device_id="pcs_c",
            metadata={"rated_p": 200.0},
            capabilities={"soc_readable": {"soc": 30.0}},
        ),
    ]

    soc_balancer = SOCBalancingDistributor(rated_key="rated_p", gain=2.0)
    result = soc_balancer.distribute(system_command, devices_with_cap)
    for dev_id, cmd in result.items():
        soc = next(d.capabilities["soc_readable"]["soc"] for d in devices_with_cap if d.device_id == dev_id)
        print(f"  {dev_id} (SOC={soc:.0f}%): P={cmd.p_target:.1f}kW, Q={cmd.q_target:.1f}kVar")
    print("  -> SOC 70% 的 A 比 SOC 30% 的 C 分得更多放電功率")

    # ================================================
    # Step 4: 充電場景 — SOC 低的多充
    # ================================================
    print("\n=== Step 4: 充電場景 — SOC 低的多充 ===")
    charge_command = Command(p_target=-200.0, q_target=0.0)
    result = soc_balancer.distribute(charge_command, devices_with_cap)
    for dev_id, cmd in result.items():
        soc = next(d.capabilities["soc_readable"]["soc"] for d in devices_with_cap if d.device_id == dev_id)
        print(f"  {dev_id} (SOC={soc:.0f}%): P={cmd.p_target:.1f}kW")
    print("  -> SOC 30% 的 C 比 SOC 70% 的 A 分得更多充電功率")

    # ================================================
    # Step 5: PCS 離線 — 自動重分配
    # ================================================
    print("\n=== Step 5: PCS_C 離線 — 自動重分配到可用設備 ===")
    available_devices = devices[:2]  # 只剩 A 和 B
    result = proportional.distribute(system_command, available_devices)
    remaining_rated = 100.0 + 150.0
    for dev_id, cmd in result.items():
        rated = next(d.metadata["rated_p"] for d in available_devices if d.device_id == dev_id)
        print(f"  {dev_id} (額定 {rated:.0f}kW, 比例 {rated / remaining_rated:.1%}): P={cmd.p_target:.1f}kW")
    print(f"  -> PCS_C 離線後，200kW 由 A+B（共 {remaining_rated:.0f}kW）按比例分配")

    # ================================================
    # Step 6: 硬體限幅 — per_device_max_p
    # ================================================
    print("\n=== Step 6: SOCBalancingDistributor + 硬體限幅 ===")
    soc_with_clamp = SOCBalancingDistributor(rated_key="rated_p", gain=2.0, per_device_max_p=80.0)
    big_command = Command(p_target=300.0, q_target=0.0)
    print(f"  系統指令：P={big_command.p_target}kW，硬體限幅 80kW/台")
    result = soc_with_clamp.distribute(big_command, devices_with_cap)
    for dev_id, cmd in result.items():
        print(f"  {dev_id}: P={cmd.p_target:.1f}kW")
    print("  -> 超過 80kW 的部分被限幅，溢出轉移到其他設備")

    # ============================================================
    # Section B: CascadingStrategy — 多策略級聯（同一台設備）
    # ============================================================
    print("\n" + "=" * 60)
    print("  Section B: CascadingStrategy — 多策略在同一台設備上級聯")
    print("=" * 60)

    from csp_lib.controller.core import StrategyContext, SystemBase
    from csp_lib.controller.strategies import PQModeConfig, PQModeStrategy, QVConfig, QVStrategy
    from csp_lib.controller.system.cascading import CapacityConfig, CascadingStrategy

    # PQ 控制 P，QV 控制 Q，級聯組合
    pq = PQModeStrategy(PQModeConfig(p=80.0, q=0.0))
    qv = QVStrategy(QVConfig(nominal_voltage=380.0, v_set=100.0, droop=5.0))

    cascading = CascadingStrategy(
        layers=[pq, qv],
        capacity=CapacityConfig(s_max_kva=200.0),
    )

    system_base = SystemBase(p_base=200.0, q_base=200.0)

    # 電壓正常（QV 不出力）
    ctx = StrategyContext(system_base=system_base, extra={"voltage": 380.0})
    cmd = cascading.execute(ctx)
    print(f"\n  電壓 380V（正常）：P={cmd.p_target:.1f}kW, Q={cmd.q_target:.1f}kVar")
    print("  -> PQ 設 P=80kW，QV 因電壓正常不加 Q")

    # 電壓偏低（QV 輸出正 Q）
    ctx = StrategyContext(system_base=system_base, extra={"voltage": 365.0})
    cmd = cascading.execute(ctx)
    print(f"\n  電壓 365V（偏低）：P={cmd.p_target:.1f}kW, Q={cmd.q_target:.1f}kVar")
    s = (cmd.p_target**2 + cmd.q_target**2) ** 0.5
    print(f"  -> PQ 設 P=80kW，QV 加 Q 提供無功支撐，S={s:.1f}kVA（限制 200kVA）")

    # ============================================================
    # 摘要
    # ============================================================
    print("\n" + "=" * 60)
    print("  學到了什麼：")
    print("  1. EqualDistributor：均分功率到所有設備")
    print("  2. ProportionalDistributor：按額定容量比例分配")
    print("  3. SOCBalancingDistributor：SOC 高的多放、低的多充")
    print("  4. per_device_max_p：硬體限幅 + 溢出自動轉移")
    print("  5. PCS 離線時自動重分配到可用設備")
    print("  6. CascadingStrategy：多策略在同一台設備上組合（PQ+QV）")
    print("  7. PowerDistributor = 多機分配，CascadingStrategy = 多策略組合")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
