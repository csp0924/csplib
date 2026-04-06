"""
Example 04: System Controller — 系統控制器

學習目標：
  - SystemController.builder() fluent API 建構配置
  - DeviceRegistry 設備註冊與查詢
  - ContextMapping / CommandMapping 設備-策略映射
  - DynamicSOCProtection 動態 SOC 保護
  - CommandRouter 自動路由命令到設備
  - 完整控制迴圈：策略 -> 保護 -> 路由 -> 設備

Run:
  uv run python examples/04_system_controller.py
"""

import asyncio

from csp_lib.controller.strategies import (
    PQModeConfig,
    PQModeStrategy,
)
from csp_lib.controller.system import (
    DynamicSOCProtection,
    ModePriority,
    SOCProtectionConfig,
)
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.integration import (
    DeviceRegistry,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import (
    PCSSimulator,
    PowerMeterSimulator,
    ServerConfig,
    SimulationServer,
)
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import default_meter_config

# ============================================================
# 模擬伺服器設定
# ============================================================
SIM_HOST, SIM_PORT = "127.0.0.1", 5020


def create_sim() -> SimulationServer:
    """建立模擬伺服器：1 台 PCS + 1 台電表"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    # PCS 模擬器（初始 SOC=70%）
    pcs = PCSSimulator(
        config=default_pcs_config("pcs_01", unit_id=10),
        capacity_kwh=200.0,
        p_ramp_rate=50.0,
    )
    pcs.set_value("soc", 70.0)
    pcs.set_value("operating_mode", 1)
    pcs._running = True

    # 電表模擬器
    meter = PowerMeterSimulator(
        config=default_meter_config("meter_01", unit_id=1),
        voltage_noise=1.5,
        frequency_noise=0.01,
    )
    meter.set_system_reading(v=380.0, f=60.0, p=20.0, q=5.0)

    server.add_simulator(pcs)
    server.add_simulator(meter)
    return server


# ============================================================
# 設備點位定義
# ============================================================

# PCS 讀取點位
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
        validator=RangeValidator(min_value=-200.0, max_value=200.0),
    ),
    WritePoint(
        name="q_setpoint",
        address=2,
        data_type=Float32(),
        validator=RangeValidator(min_value=-100.0, max_value=100.0),
    ),
]

# 電表讀取點位
meter_read_points = [
    ReadPoint(name="voltage_a", address=0, data_type=Float32(), metadata=PointMetadata(unit="V")),
    ReadPoint(name="active_power", address=12, data_type=Float32(), metadata=PointMetadata(unit="kW")),
    ReadPoint(name="frequency", address=20, data_type=Float32(), metadata=PointMetadata(unit="Hz")),
]


async def main() -> None:
    print("=" * 60)
    print("  Example 04: System Controller — 系統控制器")
    print("=" * 60)

    # ========================================================
    # Step 1: 啟動模擬伺服器
    # ========================================================
    print("\n=== Step 1: 啟動模擬伺服器 ===")
    sim_server = create_sim()
    async with sim_server:
        print(f"  模擬伺服器已啟動：{SIM_HOST}:{SIM_PORT}")

        # ====================================================
        # Step 2: 建立設備
        # ====================================================
        print("\n=== Step 2: 建立設備 ===")
        pcs_client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
        pcs_device = AsyncModbusDevice(
            config=DeviceConfig(device_id="pcs_01", unit_id=10, read_interval=1.0),
            client=pcs_client,
            always_points=pcs_read_points,
            write_points=pcs_write_points,
        )

        meter_client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
        meter_device = AsyncModbusDevice(
            config=DeviceConfig(device_id="meter_01", unit_id=1, read_interval=1.0),
            client=meter_client,
            always_points=meter_read_points,
        )

        # ====================================================
        # Step 3: 建立 DeviceRegistry 並註冊設備
        # ====================================================
        print("\n=== Step 3: 建立 DeviceRegistry ===")
        registry = DeviceRegistry()
        registry.register(pcs_device, traits=["pcs", "energy_storage"])
        registry.register(meter_device, traits=["meter"])
        print(f"  已註冊設備：{[d.device_id for d in registry.all_devices]}")

        # ====================================================
        # Step 4: 用 builder() 建構 SystemControllerConfig
        # ====================================================
        print("\n=== Step 4: 建構 SystemControllerConfig ===")

        # SOC 保護配置：SOC 上限 95%、下限 5%、警戒區 5%
        soc_protection_config = SOCProtectionConfig(
            soc_high=95.0,
            soc_low=5.0,
            warning_band=5.0,
        )

        config = (
            SystemControllerConfig.builder()
            # --- Context Mapping: 設備讀值 -> StrategyContext ---
            # PCS 的 SOC 映射到 context.soc
            .map_context(point_name="soc", target="soc", device_id="pcs_01")
            # 電表的頻率映射到 context.extra["frequency"]
            .map_context(point_name="frequency", target="extra.frequency", device_id="meter_01")
            # 電表的電壓映射到 context.extra["voltage"]
            .map_context(point_name="voltage_a", target="extra.voltage", device_id="meter_01")
            # 電表的功率映射到 context.extra["meter_power"]
            .map_context(point_name="active_power", target="extra.meter_power", device_id="meter_01")
            # --- Command Mapping: Command -> 設備寫入 ---
            # P_target 寫入 PCS 的 p_setpoint
            .map_command(field="p_target", point_name="p_setpoint", device_id="pcs_01")
            # Q_target 寫入 PCS 的 q_setpoint
            .map_command(field="q_target", point_name="q_setpoint", device_id="pcs_01")
            # --- 保護規則 ---
            # 使用 DynamicSOCProtection + SOCProtectionConfig（非 deprecated SOCProtection）
            .protect(DynamicSOCProtection(soc_protection_config))
            # --- 自動停機 ---
            .auto_stop(enabled=True)
            .build()
        )

        print("  Config 建構完成：")
        print(f"    Context mappings: {len(config.context_mappings)} 個")
        print(f"    Command mappings: {len(config.command_mappings)} 個")
        print(f"    Protection rules: {len(config.protection_rules)} 個")
        print(f"    Auto stop on alarm: {config.auto_stop_on_alarm}")

        # ====================================================
        # Step 5: 建立 SystemController 並註冊模式
        # ====================================================
        print("\n=== Step 5: 建立 SystemController ===")
        controller = SystemController(registry, config)

        # 註冊 PQ 模式作為初始策略
        pq_strategy = PQModeStrategy(PQModeConfig(p=40.0, q=10.0))
        controller.register_mode("pq", pq_strategy, ModePriority.SCHEDULE, "PQ 固定功率模式")
        print(f"  已註冊模式：pq ({pq_strategy})")

        # 設定 PQ 為基礎模式
        await controller.set_base_mode("pq")
        print("  基礎模式設為：pq")

        # ====================================================
        # Step 6: 啟動控制器，觀察完整控制迴圈
        # ====================================================
        print("\n=== Step 6: 啟動控制迴圈 ===")

        # 先連線設備
        await pcs_device.connect()
        await pcs_device.start()
        await meter_device.connect()
        await meter_device.start()
        print("  設備已連線")

        # 啟動 SystemController
        async with controller:
            print("  SystemController 已啟動")
            print("  控制迴圈開始運行...")

            # 等待幾個控制週期
            for cycle in range(5):
                await asyncio.sleep(1.0)
                p_val = pcs_device.latest_values.get("p_actual", 0)
                q_val = pcs_device.latest_values.get("q_actual", 0)
                soc_val = pcs_device.latest_values.get("soc", 0)
                p_str = f"{p_val:.1f}" if isinstance(p_val, float) else str(p_val)
                q_str = f"{q_val:.1f}" if isinstance(q_val, float) else str(q_val)
                soc_str = f"{soc_val:.1f}" if isinstance(soc_val, float) else str(soc_val)
                print(f"  Cycle {cycle + 1}: P={p_str} kW, Q={q_str} kVar, SOC={soc_str}%")

            # ================================================
            # Step 7: 觀察 SOC 保護削減命令
            # ================================================
            print("\n=== Step 7: 測試 SOC 保護（設定 SOC=3%）===")
            pcs_sim = sim_server.simulators[10]
            pcs_sim.set_value("soc", 3.0)
            print("  已將模擬器 SOC 設為 3%（低於下限 5%）")
            print("  預期行為：保護規則禁止放電（P>0 將被削減為 0）")

            for cycle in range(4):
                await asyncio.sleep(1.0)
                p_val = pcs_device.latest_values.get("p_actual", 0)
                soc_val = pcs_device.latest_values.get("soc", 0)
                p_str = f"{p_val:.1f}" if isinstance(p_val, float) else str(p_val)
                soc_str = f"{soc_val:.1f}" if isinstance(soc_val, float) else str(soc_val)
                print(f"  Cycle {cycle + 1}: P={p_str} kW, SOC={soc_str}% (P 應逐漸趨近 0 — 保護規則禁止放電)")

            # ================================================
            # Step 8: 恢復 SOC，觀察正常運行
            # ================================================
            print("\n=== Step 8: 恢復 SOC=60%，觀察命令恢復 ===")
            pcs_sim.set_value("soc", 60.0)

            for cycle in range(4):
                await asyncio.sleep(1.0)
                p_val = pcs_device.latest_values.get("p_actual", 0)
                soc_val = pcs_device.latest_values.get("soc", 0)
                p_str = f"{p_val:.1f}" if isinstance(p_val, float) else str(p_val)
                soc_str = f"{soc_val:.1f}" if isinstance(soc_val, float) else str(soc_val)
                print(f"  Cycle {cycle + 1}: P={p_str} kW, SOC={soc_str}% (P 應恢復到 40 kW)")

        # ====================================================
        # 清理
        # ====================================================
        print("\n=== Step 9: 清理 ===")
        await pcs_device.stop()
        await pcs_device.disconnect()
        await meter_device.stop()
        await meter_device.disconnect()
        print("  設備已斷線，控制器已停止")

    # ============================================================
    # 摘要
    # ============================================================
    print("\n" + "=" * 60)
    print("  學到了什麼：")
    print("  1. DeviceRegistry：集中管理設備，支援 trait-based 查詢")
    print("  2. SystemControllerConfig.builder()：fluent API 建構配置")
    print("  3. ContextMapping：設備讀值自動映射到 StrategyContext")
    print("  4. CommandMapping：Command 自動路由到設備寫入")
    print("  5. DynamicSOCProtection：SOC 上下限保護（非 deprecated SOCProtection）")
    print("  6. register_mode + set_base_mode：註冊策略並設為基礎模式")
    print("  7. 完整控制迴圈：策略執行 -> 保護削減 -> 命令路由 -> 設備寫入")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
