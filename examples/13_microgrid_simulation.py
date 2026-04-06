"""
Example 13: Microgrid Simulation — 完整微電網模擬

學習目標:
  - MicrogridSimulator: 微電網系統聯動協調器
  - PCS + BMS + 電表 + Solar + Load 完整設備模擬
  - PCS↔BMS 連結: SOC 由 BMS 管理
  - Solar/Load 功率聚合到電表
  - 場景模擬: 白天充電、晚上放電、尖峰削峰

架構:
  SimulationServer (:5020)
    └─ MicrogridSimulator
         ├─ PCS (200kW) + BMS (200kWh, SOC 追蹤)
         ├─ Solar (50kW 初始 DC 功率)
         ├─ Load (80kW 基礎負載)
         └─ Meter (市電側功率平衡)

  P_grid = P_load - P_solar - P_pcs
  正值=從電網取電, 負值=輸出到電網

Run: uv run python examples/12_microgrid_simulation.py
預計時間: 30 min
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.modbus_server import (
    BMSSimConfig,
    ControllabilityMode,
    DeviceLinkConfig,
    LoadSimConfig,
    MicrogridConfig,
    MicrogridSimulator,
    PCSSimConfig,
    PowerMeterSimConfig,
    ServerConfig,
    SimulationServer,
    SolarSimConfig,
)
from csp_lib.modbus_server.simulator.bms import BMSSimulator, default_bms_config
from csp_lib.modbus_server.simulator.load import LoadSimulator, default_load_config
from csp_lib.modbus_server.simulator.pcs import PCSSimulator, default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import PowerMeterSimulator, default_meter_config
from csp_lib.modbus_server.simulator.solar import SolarSimulator, default_solar_config

SIM_HOST = "127.0.0.1"
SIM_PORT = 5020


# ============================================================
# Step 1: 建立微電網設備
# ============================================================


def create_microgrid() -> tuple[
    MicrogridSimulator,
    PCSSimulator,
    BMSSimulator,
    SolarSimulator,
    LoadSimulator,
    PowerMeterSimulator,
]:
    """建立完整微電網: PCS + BMS + Solar + Load + Meter"""

    mg = MicrogridSimulator(
        MicrogridConfig(
            grid_voltage=380.0,
            grid_frequency=60.0,
            voltage_noise=0.0,
            frequency_noise=0.0,
        )
    )

    # ---- PCS: 200kW 儲能變流器 ----
    pcs = PCSSimulator(
        config=default_pcs_config(device_id="pcs_1", unit_id=10),
        sim_config=PCSSimConfig(
            capacity_kwh=200.0,
            p_ramp_rate=100.0,  # 100 kW/s 斜率
            q_ramp_rate=50.0,
            tick_interval=1.0,
        ),
    )
    pcs.on_write("start_cmd", 0, 1)  # 啟動 PCS
    mg.add_pcs(pcs)

    # ---- BMS: 200kWh 電池管理系統 ----
    bms = BMSSimulator(
        config=default_bms_config(device_id="bms_1", unit_id=20),
        sim_config=BMSSimConfig(
            capacity_kwh=200.0,
            initial_soc=70.0,  # 初始 SOC 70%
            nominal_voltage=700.0,
            cells_in_series=192,
            charge_efficiency=0.95,
        ),
    )
    mg.add_bms(bms)

    # PCS↔BMS 連結: SOC 由 BMS 管理
    mg.link_pcs_bms("pcs_1", "bms_1")

    # ---- Solar: 太陽能模擬器 ----
    solar = SolarSimulator(
        config=default_solar_config(device_id="solar_1", unit_id=30),
        sim_config=SolarSimConfig(
            efficiency=0.95,  # DC→AC 轉換效率
            power_noise=0.0,
        ),
    )
    solar.set_target_power(50.0)  # 初始 50kW DC 發電
    mg.add_solar(solar)

    # ---- Load: 負載模擬器（不可控）----
    load = LoadSimulator(
        config=default_load_config(device_id="load_1", unit_id=40, controllable=False),
        sim_config=LoadSimConfig(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            power_factor=0.9,
            ramp_rate=50.0,
            base_load=80.0,  # 初始 80kW 基礎負載
            load_noise=0.0,
        ),
    )
    mg.add_load(load)

    # ---- Meter: 市電側電表 ----
    meter = PowerMeterSimulator(
        config=default_meter_config(device_id="meter_1", unit_id=1),
        sim_config=PowerMeterSimConfig(
            power_sign=1.0,  # 正值=從電網取電
            voltage_noise=0.0,
            frequency_noise=0.0,
        ),
    )
    mg.set_meter(meter)

    # 設備連結到電表（含損耗）
    mg.add_device_link(DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_1", loss_factor=0.02))
    mg.add_device_link(DeviceLinkConfig(source_device_id="solar_1", target_meter_id="meter_1"))
    mg.add_device_link(DeviceLinkConfig(source_device_id="load_1", target_meter_id="meter_1"))

    return mg, pcs, bms, solar, load, meter


# ============================================================
# Step 2: Dashboard 輸出
# ============================================================


def print_status(
    label: str,
    pcs: PCSSimulator,
    bms: BMSSimulator,
    solar: SolarSimulator,
    load: LoadSimulator,
    meter: PowerMeterSimulator,
) -> None:
    """印出系統即時狀態"""
    p_actual = float(pcs.get_value("p_actual") or 0.0)
    soc = float(bms.get_value("soc") or 0.0)
    bms_v = float(bms.get_value("voltage") or 0.0)
    bms_i = float(bms.get_value("current") or 0.0)
    solar_p = float(solar.get_value("ac_power") or 0.0)
    load_p = float(load.get_value("p_actual") or 0.0)
    grid_p = float(meter.get_value("active_power") or 0.0)
    grid_v = float(meter.get_value("voltage_a") or 380.0)
    energy = float(meter.get_value("energy_total") or 0.0)

    # BMS 狀態文字
    bms_status = int(bms.get_value("status") or 0)
    status_text = {0: "standby", 1: "charging", 2: "discharging"}.get(bms_status, "unknown")

    print(f"  [{label}]")
    print(f"    PCS:   P={p_actual:+7.1f} kW ({'放電' if p_actual > 0 else '充電' if p_actual < 0 else '停機'})")
    print(f"    BMS:   SOC={soc:5.1f}% | V={bms_v:6.0f}V | I={bms_i:+6.1f}A | {status_text}")
    print(f"    Solar: P={solar_p:+7.1f} kW")
    print(f"    Load:  P={load_p:+7.1f} kW")
    print(f"    Grid:  P={grid_p:+7.1f} kW | V={grid_v:.0f}V | E={energy:.3f}kWh")
    print(f"    Balance: Load({load_p:.0f}) - Solar({solar_p:.0f}) - PCS({p_actual:.0f}) = Grid({grid_p:.0f})")


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    print("=" * 60)
    print("  Example 13: Microgrid Simulation — 完整微電網模擬")
    print("=" * 60)

    # ---- Step 1: 建立微電網 ----
    print("\n=== Step 1: 建立微電網設備 ===")
    mg, pcs, bms, solar, load, meter = create_microgrid()
    print("  PCS:   200kW / 200kWh (已啟動)")
    print("  BMS:   200kWh, SOC=70%, 192s cells")
    print("  Solar: 50kW DC (效率 95%)")
    print("  Load:  80kW 基礎負載 (不可控)")
    print("  Meter: 市電側 (power_sign=+1)")
    print("\n  P_grid = P_load - P_solar - P_pcs")
    print("  初始: 80 - 47.5 - 0 = 32.5 kW (從電網取電)")

    # ---- Step 2: 啟動 SimulationServer ----
    print("\n=== Step 2: 啟動 SimulationServer ===")
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))
    server.set_microgrid(mg)

    async with server:
        print(f"  SimulationServer 啟動: {SIM_HOST}:{SIM_PORT}")
        print(f"  設備數: {len(server.simulators)}")

        # 等待初始 tick
        await asyncio.sleep(1.5)
        print_status("初始狀態", pcs, bms, solar, load, meter)

        # ============================================================
        # 場景 A: 白天 — Solar 高發，PCS 充電
        # ============================================================
        print("\n=== Step 3: 場景 A — 白天 (Solar 高發, PCS 充電) ===")
        print("  Solar: 50kW → 150kW (日照增強)")
        print("  PCS:   充電 -80kW")

        solar.set_target_power(150.0)  # Solar 發電增加到 150kW
        pcs.on_write("p_setpoint", 0, -80.0)  # PCS 充電 80kW

        for i in range(3):
            await asyncio.sleep(1.5)
            print_status(f"白天 t={i + 1}", pcs, bms, solar, load, meter)

        # ============================================================
        # 場景 B: 晚上 — Solar 降低，PCS 放電
        # ============================================================
        print("\n=== Step 4: 場景 B — 晚上 (Solar 降低, PCS 放電) ===")
        print("  Solar: 150kW → 0kW (日落)")
        print("  PCS:   放電 +100kW")

        solar.set_target_power(0.0)  # 太陽能停止發電
        pcs.on_write("p_setpoint", -80.0, 100.0)  # PCS 放電 100kW

        for i in range(3):
            await asyncio.sleep(1.5)
            print_status(f"晚上 t={i + 1}", pcs, bms, solar, load, meter)

        # ============================================================
        # 場景 C: 尖峰 — Load 增加，PCS 削峰
        # ============================================================
        print("\n=== Step 5: 場景 C — 尖峰 (Load 增加, PCS 削峰) ===")
        print("  Load:  80kW → 200kW (尖峰用電)")
        print("  PCS:   放電 +150kW (削峰)")

        load.set_base_load(200.0)  # 負載增加到 200kW
        pcs.on_write("p_setpoint", 100.0, 150.0)  # PCS 放電 150kW

        for i in range(3):
            await asyncio.sleep(1.5)
            print_status(f"尖峰 t={i + 1}", pcs, bms, solar, load, meter)

        # ============================================================
        # Step 6: BMS 告警展示
        # ============================================================
        print("\n=== Step 6: BMS 告警展示 ===")
        alarm_reg = int(bms.get_value("alarm_register") or 0)
        cell_min = float(bms.get_value("cell_voltage_min") or 0.0)
        cell_max = float(bms.get_value("cell_voltage_max") or 0.0)
        temp = float(bms.get_value("temperature") or 0.0)
        soc = float(bms.get_value("soc") or 0.0)

        print(f"  BMS 告警暫存器: 0x{alarm_reg:04X}")
        print(f"    bit0 (過溫>55°C):   {'觸發' if alarm_reg & 1 else '正常'} (T={temp:.1f}°C)")
        print(f"    bit1 (欠壓<2.5V):   {'觸發' if alarm_reg & 2 else '正常'} (min={cell_min:.2f}V)")
        print(f"    bit2 (過壓>4.25V):  {'觸發' if alarm_reg & 4 else '正常'} (max={cell_max:.2f}V)")
        print(f"    bit3 (SOC低<5%):    {'觸發' if alarm_reg & 8 else '正常'} (SOC={soc:.1f}%)")
        print(f"    bit4 (SOC高>95%):   {'觸發' if alarm_reg & 16 else '正常'} (SOC={soc:.1f}%)")

        # ============================================================
        # Step 7: 停機
        # ============================================================
        print("\n=== Step 7: 停機 ===")
        pcs.on_write("p_setpoint", 150.0, 0.0)  # 功率歸零
        await asyncio.sleep(2.0)
        print_status("停機", pcs, bms, solar, load, meter)

        # 微電網累積電量
        print(f"\n  微電網累積電量: {mg.accumulated_energy:.4f} kWh")

    print("\n--- 完成 ---")
    print("  SimulationServer 已停止")
    print("\n要點回顧:")
    print("  1. MicrogridSimulator 管理所有設備的物理關係")
    print("  2. link_pcs_bms() 讓 BMS 管理 PCS 的 SOC")
    print("  3. DeviceLinkConfig 連結設備到指定電表（含線路損耗）")
    print("  4. 功率平衡: P_grid = P_load - P_solar - P_pcs")
    print("  5. BMS 自動偵測告警（過溫、過壓、欠壓、SOC 高低）")


if __name__ == "__main__":
    asyncio.run(main())
