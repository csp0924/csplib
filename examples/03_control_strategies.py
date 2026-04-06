"""
Example 03: Control Strategies — 控制策略入門

學習目標：
  - PQModeStrategy / QVStrategy / FPStrategy 策略定義
  - StrategyExecutor 執行策略並產出 Command
  - 策略切換（set_strategy）與手動觸發（execute_once）
  - 策略的 context 需求（extra["frequency"], extra["voltage"]）

Run:
  uv run python examples/03_control_strategies.py
"""

import asyncio

from csp_lib.controller.core import StrategyContext, SystemBase
from csp_lib.controller.executor import StrategyExecutor
from csp_lib.controller.strategies import (
    FPConfig,
    FPStrategy,
    PQModeConfig,
    PQModeStrategy,
    QVConfig,
    QVStrategy,
)
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient
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

    # PCS 模擬器
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
    ReadPoint(name="reactive_power", address=14, data_type=Float32(), metadata=PointMetadata(unit="kVar")),
    ReadPoint(name="frequency", address=20, data_type=Float32(), metadata=PointMetadata(unit="Hz")),
]


async def main() -> None:
    print("=" * 60)
    print("  Example 03: Control Strategies — 控制策略入門")
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
        print("\n=== Step 2: 建立 PCS 和電表設備 ===")
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

        async with pcs_device, meter_device:
            # 等待初始讀取
            await asyncio.sleep(2.0)
            print(f"  PCS: SOC={pcs_device.latest_values.get('soc')}, P={pcs_device.latest_values.get('p_actual')}")
            print(
                f"  電表: V={meter_device.latest_values.get('voltage_a')}, "
                f"F={meter_device.latest_values.get('frequency')}"
            )

            # ================================================
            # Step 3: PQ 模式策略
            # ================================================
            print("\n=== Step 3: PQ 模式策略 ===")
            pq_config = PQModeConfig(p=30.0, q=10.0)
            pq_strategy = PQModeStrategy(pq_config)
            print(f"  策略：{pq_strategy}")
            print(f"  執行模式：{pq_strategy.execution_config.mode.name}")
            print(f"  執行間隔：{pq_strategy.execution_config.interval_seconds} 秒")

            # 建立 SystemBase（額定容量，讓 QV/FP 策略輸出 kVar 而非比值）
            system_base = SystemBase(p_base=200.0, q_base=200.0)
            print(f"  SystemBase: P_base={system_base.p_base} kW, Q_base={system_base.q_base} kVar")

            # 建立 context（手動模式，不透過 SystemController）
            def build_context() -> StrategyContext:
                return StrategyContext(
                    soc=pcs_device.latest_values.get("soc"),
                    system_base=system_base,
                    extra={
                        "voltage": meter_device.latest_values.get("voltage_a", 380.0),
                        "frequency": meter_device.latest_values.get("frequency", 60.0),
                        "meter_power": meter_device.latest_values.get("active_power", 0.0),
                    },
                )

            # 建立 StrategyExecutor
            executor = StrategyExecutor(context_provider=build_context)
            await executor.set_strategy(pq_strategy)

            # 手動觸發一次執行
            command = await executor.execute_once()
            print(f"  PQ 命令輸出：{command}")
            print(f"    P_target = {command.p_target:.1f} kW")
            print(f"    Q_target = {command.q_target:.1f} kVar")

            # 將命令寫入 PCS
            await pcs_device.write("p_setpoint", command.p_target)
            await pcs_device.write("q_setpoint", command.q_target)
            print("  已寫入 PCS")

            # 等待追蹤
            await asyncio.sleep(2.0)
            print(
                f"  PCS 實際：P={pcs_device.latest_values.get('p_actual')}, "
                f"Q={pcs_device.latest_values.get('q_actual')}"
            )

            # ================================================
            # Step 4: QV 模式策略（電壓-無功功率控制）
            # ================================================
            print("\n=== Step 4: QV 模式策略 ===")
            qv_config = QVConfig(
                nominal_voltage=380.0,
                v_set=100.0,
                droop=5.0,
                q_max_ratio=0.5,
            )
            qv_strategy = QVStrategy(qv_config)
            print(f"  策略：{qv_strategy}")
            print(f"  額定電壓：{qv_config.nominal_voltage} V")
            print(f"  下垂係數：{qv_config.droop}%")

            # 切換策略
            await executor.set_strategy(qv_strategy)
            command = await executor.execute_once()
            print(f"  QV 命令輸出：{command}")
            print(f"    P_target = {command.p_target:.1f} kW（保持上次 P）")
            print(f"    Q_target = {command.q_target:.1f} kVar")

            # 模擬電壓偏低的情況
            print("\n  模擬電壓偏低（設定 V=365V）...")
            meter_sim = sim_server.simulators[1]
            meter_sim.set_system_reading(v=365.0, f=60.0, p=20.0, q=5.0)
            await asyncio.sleep(1.5)

            command = await executor.execute_once()
            current_voltage = meter_device.latest_values.get("voltage_a", 380.0)
            print(f"  目前電壓：{current_voltage}")
            print(f"  QV 命令輸出：{command}")
            print(f"    Q_target = {command.q_target:.4f}（電壓偏低 -> 正 Q -> 提供無功）")

            # ================================================
            # Step 5: FP 模式策略（頻率-功率控制）
            # ================================================
            print("\n=== Step 5: FP 模式策略（AFC）===")
            fp_config = FPConfig(
                f_base=60.0,
                f1=-0.5,
                f2=-0.25,
                f3=-0.02,
                f4=0.02,
                f5=0.25,
                f6=0.5,
                p1=100.0,
                p2=52.0,
                p3=9.0,
                p4=-9.0,
                p5=-52.0,
                p6=-100.0,
            )
            fp_strategy = FPStrategy(fp_config)
            print(f"  策略：{fp_strategy}")
            print(f"  基準頻率：{fp_config.f_base} Hz")
            print(f"  死區範圍：{fp_config.f_base + fp_config.f3:.2f} ~ {fp_config.f_base + fp_config.f4:.2f} Hz")

            # 切換策略
            await executor.set_strategy(fp_strategy)

            # 正常頻率（死區內）
            meter_sim.set_system_reading(v=380.0, f=60.0, p=20.0, q=5.0)
            await asyncio.sleep(1.5)
            command = await executor.execute_once()
            print("\n  頻率 60.00 Hz（死區內）：")
            print(f"    P_target = {command.p_target:.1f} kW（接近 0，死區內不動作）")

            # 頻率偏低（需要放電）
            meter_sim.set_system_reading(v=380.0, f=59.7, p=20.0, q=5.0)
            await asyncio.sleep(1.5)
            command = await executor.execute_once()
            print("\n  頻率 59.70 Hz（偏低）：")
            print(f"    P_target = {command.p_target:.1f} kW（正值 -> 放電支撐頻率）")

            # 頻率偏高（需要充電）
            meter_sim.set_system_reading(v=380.0, f=60.3, p=20.0, q=5.0)
            await asyncio.sleep(1.5)
            command = await executor.execute_once()
            print("\n  頻率 60.30 Hz（偏高）：")
            print(f"    P_target = {command.p_target:.1f} kW（負值 -> 充電抑制頻率）")

            # ================================================
            # 清理
            # ================================================
            executor.stop()

    # ============================================================
    # 摘要
    # ============================================================
    print("\n" + "=" * 60)
    print("  學到了什麼：")
    print("  1. PQModeStrategy：固定 P/Q 輸出，最簡單的策略")
    print("  2. QVStrategy：根據電壓偏差計算無功功率（Volt-VAR 控制，只管 Q）")
    print("  3. FPStrategy：根據頻率偏差計算功率（AFC，分段線性插值，只管 P）")
    print("  4. StrategyExecutor：管理策略執行，支援 set_strategy 切換")
    print("  5. execute_once()：手動觸發一次策略執行，取得 Command")
    print("  6. StrategyContext.extra：策略所需的外部量測值（voltage, frequency）")
    print("  7. SystemBase：提供額定容量，讓策略輸出 kW/kVar 而非比值")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
