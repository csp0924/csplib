"""
csp_lib Example 06: 進階保護規則

學習目標：
  - DynamicSOCProtection — SOC 動態上下限保護（漸進限制充放電）
  - EventDrivenOverride — 事件驅動的自動模式切換
  - RampStopStrategy — 斜坡降功率策略（緩停）
  - ReversePowerProtection — 電表逆功率保護
  - 完整的「保護觸發 → 切換策略 → 恢復」流程

架構：
  SimulationServer (Modbus TCP 模擬器)
       ↕ TCP
  AsyncModbusDevice (PCS + 電表)
       ↓ context
  SystemController
    ├── DynamicSOCProtection — SOC 低於下限時削減放電
    ├── ReversePowerProtection — 防止逆送電力
    ├── ProtectionGuard — 鏈式套用保護規則
    ├── EventDrivenOverride — 系統告警時自動推入 RampStop
    └── RampStopStrategy — 保護觸發時斜坡降至 0

Run: uv run python examples/06_advanced_protection.py
"""

import asyncio
import sys

# Windows 終端 UTF-8 支援
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.controller.core import Command, StrategyContext
from csp_lib.controller.strategies import PQModeConfig, PQModeStrategy, StopStrategy
from csp_lib.controller.strategies.ramp_stop import RampStopStrategy
from csp_lib.controller.system import (
    DynamicSOCProtection,
    ModePriority,
    ProtectionGuard,
    ReversePowerProtection,
    SOCProtectionConfig,
)
from csp_lib.controller.system.event_override import ContextKeyOverride
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.integration import (
    CommandMapping,
    ContextMapping,
    DeviceRegistry,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, PowerMeterSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import default_meter_config

# ============================================================
# 常量
# ============================================================

SIM_HOST = "127.0.0.1"
SIM_PORT = 5060  # 避免與其他範例衝突


# ============================================================
# Section 1: SimulationServer 建立
# ============================================================


def create_simulation_server() -> tuple[SimulationServer, PCSSimulator, PowerMeterSimulator]:
    """建立模擬伺服器：1 台 PCS + 1 台電表"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    # PCS — unit_id=10，初始 SOC=70%，容量 200kWh
    pcs_config = default_pcs_config("pcs_01", unit_id=10)
    pcs_sim = PCSSimulator(config=pcs_config, capacity_kwh=200.0, p_ramp_rate=200.0)
    pcs_sim.set_value("soc", 70.0)
    pcs_sim.set_value("operating_mode", 1)
    pcs_sim._running = True

    # 電表 — unit_id=1，初始負載 20kW
    meter_config = default_meter_config("meter_01", unit_id=1)
    meter_sim = PowerMeterSimulator(config=meter_config)
    meter_sim.set_system_reading(v=380.0, f=60.0, p=100.0, q=5.0)

    server.add_simulator(pcs_sim)
    server.add_simulator(meter_sim)
    return server, pcs_sim, meter_sim


# ============================================================
# Section 2: AsyncModbusDevice 建立
# ============================================================


def create_devices() -> tuple[AsyncModbusDevice, AsyncModbusDevice]:
    """建立 PCS 和電表的 AsyncModbusDevice"""
    tcp_config = ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT, timeout=2.0)
    f32 = Float32()
    u16 = UInt16()

    # --- PCS 設備 ---
    pcs_read_points = [
        ReadPoint(name="p_actual", address=4, data_type=f32, metadata=PointMetadata(unit="kW")),
        ReadPoint(name="q_actual", address=6, data_type=f32, metadata=PointMetadata(unit="kVar")),
        ReadPoint(name="soc", address=8, data_type=f32, metadata=PointMetadata(unit="%")),
        ReadPoint(name="operating_mode", address=10, data_type=u16),
        ReadPoint(name="alarm_register", address=11, data_type=u16),
        ReadPoint(name="voltage", address=15, data_type=f32, metadata=PointMetadata(unit="V")),
        ReadPoint(name="frequency", address=17, data_type=f32, metadata=PointMetadata(unit="Hz")),
    ]
    # PCS 告警定義：alarm_register bit0 = CRITICAL 系統故障
    from csp_lib.equipment.alarm import AlarmDefinition, AlarmLevel, BitMaskAlarmEvaluator

    pcs_alarm_evaluators = [
        BitMaskAlarmEvaluator(
            point_name="alarm_register",
            bit_alarms={0: AlarmDefinition(code="PCS_FAULT", name="PCS 系統故障", level=AlarmLevel.ALARM)},
        ),
    ]
    pcs_write_points = [
        WritePoint(name="p_setpoint", address=0, data_type=f32, metadata=PointMetadata(unit="kW")),
        WritePoint(name="q_setpoint", address=2, data_type=f32, metadata=PointMetadata(unit="kVar")),
    ]
    pcs_client = PymodbusTcpClient(tcp_config)
    pcs_device = AsyncModbusDevice(
        config=DeviceConfig(device_id="pcs_01", unit_id=10, read_interval=0.5),
        client=pcs_client,
        always_points=pcs_read_points,
        write_points=pcs_write_points,
        alarm_evaluators=pcs_alarm_evaluators,
    )

    # --- 電表設備 ---
    meter_read_points = [
        ReadPoint(name="active_power", address=12, data_type=f32, metadata=PointMetadata(unit="kW")),
        ReadPoint(name="reactive_power", address=14, data_type=f32, metadata=PointMetadata(unit="kVar")),
        ReadPoint(name="frequency", address=20, data_type=f32, metadata=PointMetadata(unit="Hz")),
    ]
    meter_client = PymodbusTcpClient(tcp_config)
    meter_device = AsyncModbusDevice(
        config=DeviceConfig(device_id="meter_01", unit_id=1, read_interval=0.5),
        client=meter_client,
        always_points=meter_read_points,
    )

    return pcs_device, meter_device


# ============================================================
# Section 3: 獨立展示 — ProtectionGuard + DynamicSOCProtection
# ============================================================


async def demo_protection_guard_standalone():
    """
    獨立展示 ProtectionGuard 的保護鏈機制，不需要 SimulationServer。
    直接建構 Command 和 StrategyContext 來測試保護規則。
    """
    print("=" * 70)
    print("Section A: ProtectionGuard 獨立展示")
    print("=" * 70)

    # 建立 DynamicSOCProtection — 使用靜態 SOCProtectionConfig
    soc_config = SOCProtectionConfig(soc_high=90.0, soc_low=20.0, warning_band=5.0)
    soc_protection = DynamicSOCProtection(soc_config)

    # 建立逆功率保護
    reverse_power = ReversePowerProtection(threshold=0.0, meter_power_key="meter_power")

    # 建立保護鏈
    guard = ProtectionGuard(rules=[soc_protection, reverse_power])

    # --- 場景 1: SOC 正常（70%），放電 100kW ---
    print("\n--- 場景 1: SOC=70%，放電 100kW ---")
    cmd = Command(p_target=100.0, q_target=0.0)
    ctx = StrategyContext(soc=70.0, extra={"meter_power": 150.0})
    result = guard.apply(cmd, ctx)
    print(f"  原始命令: P={cmd.p_target:.1f}kW")
    print(f"  保護後:   P={result.protected_command.p_target:.1f}kW")
    print(f"  觸發規則: {result.triggered_rules}")
    print(f"  已修改:   {result.was_modified}")

    # --- 場景 2: SOC 過低（15%），嘗試放電 ---
    print("\n--- 場景 2: SOC=15%（低於下限 20%），放電 100kW ---")
    cmd = Command(p_target=100.0, q_target=0.0)
    ctx = StrategyContext(soc=15.0, extra={"meter_power": 150.0})
    result = guard.apply(cmd, ctx)
    print(f"  原始命令: P={cmd.p_target:.1f}kW")
    print(f"  保護後:   P={result.protected_command.p_target:.1f}kW")
    print(f"  觸發規則: {result.triggered_rules}")
    print(f"  說明: SOC={15}% <= soc_low={20}%，禁止放電，P 被削減為 0")

    # --- 場景 3: SOC 在低側警戒區（22%），放電受限 ---
    print("\n--- 場景 3: SOC=22%（低側警戒區 20%~25%），放電 100kW ---")
    cmd = Command(p_target=100.0, q_target=0.0)
    ctx = StrategyContext(soc=22.0, extra={"meter_power": 150.0})
    result = guard.apply(cmd, ctx)
    ratio = (22.0 - 20.0) / 5.0  # warning_band=5
    print(f"  原始命令: P={cmd.p_target:.1f}kW")
    print(f"  保護後:   P={result.protected_command.p_target:.1f}kW")
    print(f"  觸發規則: {result.triggered_rules}")
    print(f"  說明: 漸進限制比例 = (SOC - soc_low) / warning_band = {ratio:.2f}")

    # --- 場景 4: 逆功率保護觸發 ---
    print("\n--- 場景 4: 電表功率=10kW，嘗試放電 50kW（會逆送） ---")
    cmd = Command(p_target=50.0, q_target=0.0)
    ctx = StrategyContext(soc=70.0, extra={"meter_power": 10.0})
    result = guard.apply(cmd, ctx)
    print(f"  原始命令: P={cmd.p_target:.1f}kW")
    print(f"  保護後:   P={result.protected_command.p_target:.1f}kW")
    print(f"  觸發規則: {result.triggered_rules}")
    print(f"  說明: 放電上限 = meter_power + threshold = {10.0 + 0.0:.1f}kW")


# ============================================================
# Section 4: 完整系統 — SystemController + EventDrivenOverride
# ============================================================


async def demo_system_controller_protection():
    """
    完整展示 SystemController 整合保護規則與事件驅動 Override。
    使用 SimulationServer 進行真實 Modbus TCP 通訊。
    """
    print("\n" + "=" * 70)
    print("Section B: SystemController + EventDrivenOverride 完整展示")
    print("=" * 70)

    # --- 建立模擬伺服器 ---
    server, pcs_sim, meter_sim = create_simulation_server()
    pcs_device, meter_device = create_devices()

    async with server:
        print("\n[1] SimulationServer 啟動完成")
        await asyncio.sleep(0.5)

        async with pcs_device, meter_device:
            print("[2] PCS 和電表設備已連線")
            await asyncio.sleep(1.5)  # 等待首次讀取

            # --- 註冊設備到 Registry ---
            registry = DeviceRegistry()
            registry.register(pcs_device, traits=["pcs"])
            registry.register(meter_device, traits=["meter"])

            # --- 建立保護規則 ---
            soc_config = SOCProtectionConfig(soc_high=90.0, soc_low=20.0, warning_band=5.0)
            soc_protection = DynamicSOCProtection(soc_config)
            reverse_power = ReversePowerProtection(threshold=0.0)

            # --- 建立 SystemController 配置 ---
            config = SystemControllerConfig(
                context_mappings=[
                    ContextMapping(point_name="soc", context_field="soc", device_id="pcs_01"),
                    ContextMapping(point_name="active_power", context_field="extra.meter_power", device_id="meter_01"),
                ],
                command_mappings=[
                    CommandMapping(command_field="p_target", point_name="p_setpoint", device_id="pcs_01"),
                    CommandMapping(command_field="q_target", point_name="q_setpoint", device_id="pcs_01"),
                ],
                protection_rules=[soc_protection, reverse_power],
                auto_stop_on_alarm=False,  # 我們自己管理 override
            )

            controller = SystemController(registry, config)

            # --- 註冊模式 ---
            # 基礎模式：PQ 放電 80kW
            pq_strategy = PQModeStrategy(PQModeConfig(p=80.0, q=0.0))
            controller.register_mode("pq", pq_strategy, ModePriority.SCHEDULE, "PQ 放電模式")

            # 保護模式：RampStopStrategy（斜坡降至 0）
            ramp_stop = RampStopStrategy(rated_power=200.0, ramp_rate_pct=10.0)
            controller.register_mode("ramp_stop", ramp_stop, ModePriority.PROTECTION, "斜坡停機")

            # 停機模式：立即停止
            controller.register_mode("emergency_stop", StopStrategy(), ModePriority.PROTECTION + 1, "緊急停機")

            # --- 註冊 EventDrivenOverride ---
            # 當 context.extra["system_alarm"] 為 True 時，自動推入 ramp_stop
            alarm_override = ContextKeyOverride(
                name="ramp_stop",
                context_key="system_alarm",
                activate_when=lambda v: v is True,
                cooldown_seconds=3.0,
            )
            controller.register_event_override(alarm_override)

            # --- 設定基礎模式並啟動 ---
            await controller.set_base_mode("pq")

            async with controller:
                print("[3] SystemController 已啟動，基礎模式: PQ (P=80kW)\n")

                # --- 階段 1: 正常運行 ---
                print("--- 階段 1: 正常運行（SOC=70%, 電表 P=20kW）---")
                await asyncio.sleep(3)
                vals = pcs_device.latest_values
                print(f"  PCS 讀值: P_actual={vals.get('p_actual', 'N/A'):.1f}kW, SOC={vals.get('soc', 'N/A'):.1f}%")
                print(f"  電表讀值: P_meter={meter_device.latest_values.get('active_power', 'N/A'):.1f}kW")
                print("  -> PQ 策略正常輸出 P=80kW，保護未觸發\n")

                # --- 階段 2: 降低 SOC → 觸發 DynamicSOCProtection ---
                print("--- 階段 2: 降低 SOC 至 18%（低於 soc_low=20%）---")
                pcs_sim.set_value("soc", 18.0)
                await asyncio.sleep(3)
                vals = pcs_device.latest_values
                print(f"  PCS 讀值: P_actual={vals.get('p_actual', 'N/A'):.1f}kW, SOC={vals.get('soc', 'N/A'):.1f}%")
                print("  -> DynamicSOCProtection 觸發：SOC 過低，放電被削減至 P=0\n")

                # --- 階段 3: 恢復 SOC ---
                print("--- 階段 3: 恢復 SOC 至 60% ---")
                pcs_sim.set_value("soc", 60.0)
                await asyncio.sleep(3)
                vals = pcs_device.latest_values
                print(f"  PCS 讀值: P_actual={vals.get('p_actual', 'N/A'):.1f}kW, SOC={vals.get('soc', 'N/A'):.1f}%")
                print("  -> SOC 恢復正常，放電限制解除\n")

                # --- 階段 4: 觸發系統告警 → EventDrivenOverride 自動切換 ---
                print("--- 階段 4: 觸發 PCS 系統故障告警 ---")
                print("  設定模擬器 alarm_register bit0=1 → PCS_FAULT (CRITICAL)")
                print("  → device.is_protected=True → system_alarm=True")
                print("  → ContextKeyOverride 自動推入 ramp_stop")
                pcs_sim.set_value("alarm_register_1", 1)  # bit0 = PCS_FAULT
                await asyncio.sleep(4)
                vals = pcs_device.latest_values
                print(f"  PCS: P_actual={vals.get('p_actual', 'N/A'):.1f}kW, is_protected={pcs_device.is_protected}")
                print("  -> RampStopStrategy 啟動，功率正在斜坡降至 0\n")

                # --- 階段 5: 清除告警 → EventDrivenOverride 自動恢復 ---
                print("--- 階段 5: 清除 PCS 故障告警 ---")
                print("  設定模擬器 alarm_register bit0=0 → 告警清除")
                pcs_sim.set_value("alarm_register_1", 0)
                await asyncio.sleep(5)
                vals = pcs_device.latest_values
                print(f"  PCS: P_actual={vals.get('p_actual', 'N/A'):.1f}kW, is_protected={pcs_device.is_protected}")
                print("  -> 告警清除，ContextKeyOverride 自動移除 override，恢復 PQ 模式\n")

            print("[4] SystemController 已停止")
        print("[5] 設備已斷線")
    print("[6] SimulationServer 已關閉")


# ============================================================
# Section 5: 獨立展示 — RampStopStrategy 運作原理
# ============================================================


async def demo_ramp_stop_standalone():
    """獨立展示 RampStopStrategy 的斜坡降功率行為"""
    print("\n" + "=" * 70)
    print("Section C: RampStopStrategy 獨立展示")
    print("=" * 70)

    ramp = RampStopStrategy(rated_power=200.0, ramp_rate_pct=20.0)
    # 模擬 on_activate 重設狀態
    await ramp.on_activate()

    # 模擬從 P=100kW 開始斜坡降至 0
    last_cmd = Command(p_target=100.0, q_target=0.0)
    print(f"\n  初始功率: P={last_cmd.p_target:.1f}kW")
    print(f"  額定功率: 200kW，斜率: 20%/s = {200.0 * 0.20:.0f}kW/s")
    print()

    for step in range(8):
        ctx = StrategyContext(last_command=last_cmd)
        cmd = ramp.execute(ctx)
        print(f"  Step {step}: P={cmd.p_target:.1f}kW, Q={cmd.q_target:.1f}kVar")
        last_cmd = cmd
        await asyncio.sleep(0.3)  # 模擬控制週期

    await ramp.on_deactivate()
    print("\n  -> 功率已斜坡降至 0，RampStopStrategy 停用")


# ============================================================
# Main
# ============================================================


async def main():
    print()
    print("csp_lib Example 06: 進階保護規則")
    print("================================")

    # Section A: ProtectionGuard 獨立展示
    await demo_protection_guard_standalone()

    # Section B: SystemController 完整展示
    await demo_system_controller_protection()

    # Section C: RampStopStrategy 獨立展示
    await demo_ramp_stop_standalone()

    print("\n" + "=" * 70)
    print("範例完成！")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
