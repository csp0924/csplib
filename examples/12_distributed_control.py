"""
Example 12: Distributed Control — 多群組分散式控制

學習目標:
  - GroupControllerManager: 管理多個獨立 SystemController 群組
  - GroupDefinition: 群組定義（設備 ID + 獨立配置）
  - 各群組擁有獨立的 ModeManager / ProtectionGuard / StrategyExecutor
  - 群組獨立策略切換、群組間互不干擾
  - 使用真實 AsyncModbusDevice 連接 SimulationServer

架構:
  SimulationServer (:5020) ← 4 台 PCS (unit_id=10,11,12,13)
       ↕ Modbus TCP
  AsyncModbusDevice × 4
       ↕
  DeviceRegistry
       ↕
  GroupControllerManager
    ├─ Group A (pcs_1, pcs_2): PQ 策略 + EqualDistributor
    └─ Group B (pcs_3, pcs_4): QV 策略 + EqualDistributor

Run: uv run python examples/11_distributed_control.py
預計時間: 20 sec
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.controller.core import SystemBase
from csp_lib.controller.strategies import (
    PQModeConfig,
    PQModeStrategy,
    QVConfig,
    QVStrategy,
    StopStrategy,
)
from csp_lib.controller.system import ModePriority
from csp_lib.core import configure_logging
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.equipment.device.capability import (
    ACTIVE_POWER_CONTROL,
    REACTIVE_POWER_CONTROL,
    CapabilityBinding,
)
from csp_lib.integration import (
    CapabilityCommandMapping,
    DeviceRegistry,
    EqualDistributor,
    GroupControllerManager,
    GroupDefinition,
    SystemControllerConfig,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import (
    PCSSimulator,
    ServerConfig,
    SimulationServer,
)
from csp_lib.modbus_server.simulator.pcs import default_pcs_config

# ============================================================
# 模擬伺服器設定
# ============================================================
SIM_HOST = "127.0.0.1"
SIM_PORT = 5020


# ============================================================
# Step 1: 建立 SimulationServer（4 台 PCS）
# ============================================================


def create_simulation() -> tuple[SimulationServer, list[PCSSimulator]]:
    """建立 4 台 PCS 的 SimulationServer"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    pcs_list: list[PCSSimulator] = []
    soc_values = [85.0, 75.0, 60.0, 50.0]  # 不同 SOC 讓各群組表現不同
    for i in range(4):
        pcs = PCSSimulator(
            config=default_pcs_config(device_id=f"pcs_{i + 1}", unit_id=10 + i),
            capacity_kwh=200.0,
            p_ramp_rate=50.0,
        )
        pcs.set_value("soc", soc_values[i])
        pcs.set_value("operating_mode", 1)
        pcs.on_write("start_cmd", 0, 1)
        pcs._running = True
        server.add_simulator(pcs)
        pcs_list.append(pcs)

    return server, pcs_list


# ============================================================
# Step 2: 設備點位定義
# ============================================================

# PCS 讀取點位（對應 default_pcs_config 暫存器配置）
pcs_read_points = [
    ReadPoint(name="p_actual", address=4, data_type=Float32(), metadata=PointMetadata(unit="kW")),
    ReadPoint(name="q_actual", address=6, data_type=Float32(), metadata=PointMetadata(unit="kVar")),
    ReadPoint(name="soc", address=8, data_type=Float32(), metadata=PointMetadata(unit="%")),
    ReadPoint(name="operating_mode", address=10, data_type=UInt16()),
    ReadPoint(name="voltage", address=15, data_type=Float32(), metadata=PointMetadata(unit="V")),
    ReadPoint(name="frequency", address=17, data_type=Float32(), metadata=PointMetadata(unit="Hz")),
]

# PCS 寫入點位
pcs_write_points = [
    WritePoint(
        name="p_setpoint",
        address=0,
        data_type=Float32(),
        validator=RangeValidator(min_value=-500.0, max_value=500.0),
    ),
    WritePoint(
        name="q_setpoint",
        address=2,
        data_type=Float32(),
        validator=RangeValidator(min_value=-200.0, max_value=200.0),
    ),
]

# ============================================================
# Step 3: 建立 AsyncModbusDevice 實例
# ============================================================


def create_devices() -> list[AsyncModbusDevice]:
    """建立 4 台 PCS 的 AsyncModbusDevice 實例

    每台設備使用獨立的 PymodbusTcpClient，皆連接到同一 SimulationServer。
    """
    pcs_devices: list[AsyncModbusDevice] = []
    for i in range(4):
        client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
        device = AsyncModbusDevice(
            config=DeviceConfig(device_id=f"pcs_{i + 1}", unit_id=10 + i, read_interval=1.0),
            client=client,
            always_points=pcs_read_points,
            write_points=pcs_write_points,
        )
        # 綁定 capability：讓 PowerDistributor 能自動解析寫入點位
        device.add_capability(
            CapabilityBinding(ACTIVE_POWER_CONTROL, {"p_setpoint": "p_setpoint", "p_measurement": "p_actual"})
        )
        device.add_capability(CapabilityBinding(REACTIVE_POWER_CONTROL, {"q_setpoint": "q_setpoint"}))
        pcs_devices.append(device)

    return pcs_devices


# ============================================================
# Step 4: 建立 GroupControllerManager
# ============================================================


def create_group_manager(registry: DeviceRegistry) -> GroupControllerManager:
    """建立 2 群組的 GroupControllerManager

    - Group A (pcs_1, pcs_2, meter_1): PQ 策略，需要 SOC
    - Group B (pcs_3, pcs_4, meter_2): QV 策略，需要 SOC + voltage
    """

    # Capability command mappings：由 PowerDistributor 自動分配到 trait="pcs" 的所有設備
    pq_cap_mappings = [
        CapabilityCommandMapping(
            command_field="p_target", capability=ACTIVE_POWER_CONTROL, slot="p_setpoint", trait="pcs"
        ),
        CapabilityCommandMapping(
            command_field="q_target", capability=REACTIVE_POWER_CONTROL, slot="q_setpoint", trait="pcs"
        ),
    ]

    # 群組 A 配置：PCS 1+2，PQ 策略，EqualDistributor 均分功率
    config_a = (
        SystemControllerConfig.builder()
        .map_context(point_name="soc", target="soc", device_id="pcs_1")
        .map_capability_command(pq_cap_mappings[0])
        .map_capability_command(pq_cap_mappings[1])
        .distributor(EqualDistributor())
        .system_base(SystemBase(p_base=500.0, q_base=200.0))
        .build()
    )

    # 群組 B 配置：PCS 3+4，QV 策略，EqualDistributor 均分功率
    # 電壓來源使用 PCS 自帶的 voltage（非電表），避免 meter 進入 group 影響分配
    config_b = (
        SystemControllerConfig.builder()
        .map_context(point_name="soc", target="soc", device_id="pcs_3")
        .map_context(point_name="voltage", target="extra.voltage", device_id="pcs_3")
        .map_capability_command(pq_cap_mappings[0])
        .map_capability_command(pq_cap_mappings[1])
        .distributor(EqualDistributor())
        .system_base(SystemBase(p_base=500.0, q_base=200.0))
        .build()
    )

    # 建立群組定義
    groups = [
        GroupDefinition(
            group_id="group_a",
            device_ids=["pcs_1", "pcs_2"],
            config=config_a,
        ),
        GroupDefinition(
            group_id="group_b",
            device_ids=["pcs_3", "pcs_4"],
            config=config_b,
        ),
    ]

    return GroupControllerManager(registry=registry, groups=groups)


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    # 初始化 logging（移除 loguru 預設 sink，建立 stderr sink）
    configure_logging(level="INFO")

    print("=" * 60)
    print("  Example 12: Distributed Control — 多群組分散式控制")
    print("=" * 60)

    # ---- Step 1: 啟動 SimulationServer ----
    print("\n=== Step 1: 啟動 SimulationServer (4 台 PCS) ===")
    sim_server, pcs_sims = create_simulation()

    async with sim_server:
        print(f"  SimulationServer 啟動: {SIM_HOST}:{SIM_PORT}")
        for pcs in pcs_sims:
            print(
                f"    {pcs.device_id} (unit_id={pcs.unit_id}): "
                f"容量={pcs.capacity_kwh}kWh, SOC={pcs.get_value('soc'):.0f}%"
            )

        # ---- Step 2: 建立 AsyncModbusDevice 並連線 ----
        print("\n=== Step 2: 建立 AsyncModbusDevice 並連線 ===")
        pcs_devices = create_devices()
        all_devices = pcs_devices

        # 連線並啟動所有設備
        for dev in all_devices:
            await dev.connect()
            await dev.start()
        print(f"  已連線 {len(all_devices)} 台設備")

        # 等待首次讀取完成
        await asyncio.sleep(2)
        for dev in all_devices:
            vals = dev.latest_values
            print(f"    {dev.device_id}: {dict(vals)}")

        # ---- Step 3: 建立 DeviceRegistry ----
        print("\n=== Step 3: 建立 DeviceRegistry ===")
        registry = DeviceRegistry()
        for dev in pcs_devices:
            registry.register(dev, traits=["pcs"])
        print(f"  已註冊設備: {[d.device_id for d in registry.all_devices]}")

        # ---- Step 4: 建立 GroupControllerManager ----
        print("\n=== Step 4: 建立 GroupControllerManager (2 群組) ===")
        manager = create_group_manager(registry)

        print(f"  群組數: {len(manager)}")
        print(f"  群組 ID: {manager.group_ids}")

        # ---- Step 5: 為各群組註冊策略 ----
        print("\n=== Step 5: 註冊群組策略 ===")

        # Group A: PQ 策略（功率設定: P=200kW 放電, Q=0）
        manager.register_mode(
            "group_a",
            "pq",
            PQModeStrategy(PQModeConfig(p=200.0, q=0.0)),
            ModePriority.SCHEDULE,
        )
        manager.register_mode(
            "group_a",
            "stop",
            StopStrategy(),
            ModePriority.PROTECTION,
        )
        print("  Group A: PQ(P=200kW) + Stop 策略已註冊")

        # Group B: QV 策略（電壓調節: 380V 基準, 5% 下降率）
        manager.register_mode(
            "group_b",
            "qv",
            QVStrategy(QVConfig(nominal_voltage=380.0, droop=5.0)),
            ModePriority.SCHEDULE,
        )
        manager.register_mode(
            "group_b",
            "stop",
            StopStrategy(),
            ModePriority.PROTECTION,
        )
        print("  Group B: QV(380V/5%) + Stop 策略已註冊")

        # ---- Step 6: 設定初始模式並啟動 ----
        print("\n=== Step 6: 設定初始模式並啟動 ===")
        await manager.set_base_mode("group_a", "pq")
        await manager.set_base_mode("group_b", "qv")

        async with manager:
            print(f"  GroupControllerManager 已啟動: is_running={manager.is_running}")
            print(f"  Group A 模式: {manager.effective_mode_name('group_a')}")
            print(f"  Group B 模式: {manager.effective_mode_name('group_b')}")

            # 等待控制迴圈執行幾個 cycle
            print("\n  等待控制迴圈執行...")
            for cycle in range(3):
                await asyncio.sleep(1.0)
                for dev in pcs_devices:
                    p = dev.latest_values.get("p_actual", 0)
                    soc = dev.latest_values.get("soc", 0)
                    p_str = f"{p:.1f}" if isinstance(p, float) else str(p)
                    soc_str = f"{soc:.1f}" if isinstance(soc, float) else str(soc)
                    print(f"    Cycle {cycle + 1} | {dev.device_id}: P={p_str} kW, SOC={soc_str}%")

            # ---- Step 7: 展示群組獨立控制 ----
            print("\n=== Step 7: 各群組獨立運行 ===")
            for gid in manager.group_ids:
                ctrl = manager.get_controller(gid)
                mode = manager.effective_mode_name(gid)
                print(f"  {gid}: mode={mode}, is_running={ctrl.is_running}")

            # ---- Step 8: 動態切換群組策略 ----
            print("\n=== Step 8: 動態切換群組策略 ===")

            # Group A: PQ -> Stop（緊急停機 override）
            print("  Group A: 推入 Stop override")
            await manager.push_override("group_a", "stop")
            await asyncio.sleep(1.5)
            print(f"    Group A 模式: {manager.effective_mode_name('group_a')}")
            print(f"    Group B 模式: {manager.effective_mode_name('group_b')} (不受影響)")

            # 觀察 PCS 1+2 功率趨近 0
            for dev in pcs_devices[:2]:
                p = dev.latest_values.get("p_actual", 0)
                p_str = f"{p:.1f}" if isinstance(p, float) else str(p)
                print(f"    {dev.device_id}: P={p_str} kW (應趨近 0)")

            await asyncio.sleep(1.0)

            # Group A: 移除 Stop override，恢復 PQ
            print("\n  Group A: 移除 Stop override，恢復 PQ")
            await manager.pop_override("group_a", "stop")
            await asyncio.sleep(1.5)
            print(f"    Group A 模式: {manager.effective_mode_name('group_a')}")

            # ---- Step 9: 健康檢查 ----
            print("\n=== Step 9: 聚合健康報告 ===")
            health = manager.health()
            print(f"  整體狀態: {health.status.name}")
            for child in health.children:
                print(f"    {child.component}: {child.status.name}")

            # ---- Step 10: 群組觸發 ----
            print("\n=== Step 10: 觸發所有群組策略執行 ===")
            manager.trigger_all()
            await asyncio.sleep(1.0)
            print("  所有群組已觸發")

            # 查詢群組包含關係
            print(f"\n  'group_a' in manager: {'group_a' in manager}")
            print(f"  'group_c' in manager: {'group_c' in manager}")
            print(f"  群組數: {len(manager)}")

        # 清理：停止並斷線所有設備
        print("\n=== 清理 ===")
        for dev in all_devices:
            await dev.stop()
            await dev.disconnect()
        print(f"  {len(all_devices)} 台設備已斷線")

    print("\n--- 完成 ---")
    print("  SimulationServer 和 GroupControllerManager 已停止")
    print("\n要點回顧:")
    print("  1. GroupControllerManager 為每個群組建立獨立的 SystemController")
    print("  2. 各群組擁有獨立的 ModeManager、ProtectionGuard、StrategyExecutor")
    print("  3. 一個群組的 override 不會影響其他群組")
    print("  4. health() 提供聚合健康報告")
    print("  5. 使用真實 AsyncModbusDevice 連接 SimulationServer（非 mock）")
    print("  6. 每台設備使用獨立的 PymodbusTcpClient，共享同一模擬伺服器")


if __name__ == "__main__":
    asyncio.run(main())
