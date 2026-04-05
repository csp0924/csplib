"""
Example 20: 多電表微電網模擬 — SimulationServer + 設備聯動 + 電表聚合

展示 v0.6.2 新功能：
- SimulationServer — Modbus TCP 模擬伺服器，外部 client 可連線讀寫所有設備 register
- BMSSimulator — 獨立電池管理系統模擬（SOC、溫度、電壓、告警）
- DeviceLink — PCS/Load 到獨立電表的功率路由（含線路損耗）
- MeterAggregation — 子電表到總表的功率聚合（任意深度樹）
- power_sign — 表前（發電側 +放電）與表後（用電側 +用電）符號慣例

架構：
  SimulationServer (Modbus TCP :5020)
       ↕ Modbus TCP（外部 client 可讀寫 PCS setpoint）
  MicrogridSimulator
    ├─ PCS1+BMS1 ──(2% loss)──▶ Meter1  (表前, sign=-1) ──┐
    ├─ PCS2+BMS2 ──(2% loss)──▶ Meter2  (表前, sign=-1) ──┼──▶ Meter_Total (表前, sign=-1)
    └─ Load ───────────────────▶ Meter_Load (表後, sign=+1)─┘

Modbus Register Map (all Float32=2 regs, UInt16=1 reg):

  PCS (unit 10, 11):
    Addr  Name              Type     RW   Initial   說明
    0     p_setpoint        Float32  RW   0.0       有功功率設定 (kW, +放電/-充電)
    2     q_setpoint        Float32  RW   0.0       無功功率設定 (kVar)
    4     p_actual          Float32  R    0.0       實際有功功率
    6     q_actual          Float32  R    0.0       實際無功功率
    8     soc               Float32  R    50.0      電池 SOC (%) — 有 BMS 時由 BMS 同步
    10    operating_mode    UInt16   R    0         運行模式 (0=off, 1=on)
    11    alarm_register_1  UInt16   R    0         告警暫存器 1 (auto-reset)
    12    alarm_register_2  UInt16   R    0         告警暫存器 2 (manual/latched)
    13    alarm_reset_cmd   UInt16   RW   0         告警重置命令
    14    start_cmd         UInt16   RW   0         啟停命令 (1=run, 0=stop)
    15    voltage           Float32  R    380.0     系統電壓 (V)
    17    frequency         Float32  R    60.0      系統頻率 (Hz)

  BMS (unit 20, 21):
    Addr  Name              Type     RW   Initial   說明
    0     soc               Float32  RW   50.0      SOC (%) — 可寫入 debug
    2     soh               Float32  R    100.0     SOH (%)
    4     voltage           Float32  R    700.0     電池組電壓 (V, 隨 SOC 變化)
    6     current           Float32  R    0.0       電流 (A, +放電/-充電)
    8     temperature       Float32  RW   25.0      平均電芯溫度 (°C) — 可寫入測試 alarm
    10    cell_voltage_min  Float32  R    3.5       最低電芯電壓 (V)
    12    cell_voltage_max  Float32  R    3.5       最高電芯電壓 (V)
    14    alarm_register    UInt16   R    0         告警 (bit0=過溫,1=欠壓,2=過壓,3=SOC低,4=SOC高)
    15    status            UInt16   R    0         狀態 (0=standby, 1=charging, 2=discharging)

  Load (unit 30):
    Addr  Name              Type     RW   Initial   說明
    0     p_setpoint        Float32  R*   0.0       功率設定 (*可控負載為 RW)
    2     p_actual          Float32  R    0.0       實際有功功率 (kW)
    4     q_actual          Float32  R    0.0       實際無功功率 (kVar)
    6     voltage           Float32  R    380.0     電壓 (V)
    8     current           Float32  R    0.0       電流 (A)
    10    frequency         Float32  R    60.0      頻率 (Hz)
    12    status            UInt16   R    1         狀態

  Meter (unit 1, 2, 3, 4):
    Addr  Name              Type     RW   Initial   說明
    0     voltage_a         Float32  R    380.0     A 相電壓 (V)
    2     voltage_b         Float32  R    380.0     B 相電壓 (V)
    4     voltage_c         Float32  R    380.0     C 相電壓 (V)
    6     current_a         Float32  R    0.0       A 相電流 (A)
    8     current_b         Float32  R    0.0       B 相電流 (A)
    10    current_c         Float32  R    0.0       C 相電流 (A)
    12    active_power      Float32  R    0.0       有功功率 (kW, 含 power_sign)
    14    reactive_power    Float32  R    0.0       無功功率 (kVar, 含 power_sign)
    16    apparent_power    Float32  R    0.0       視在功率 (kVA)
    18    power_factor      Float32  R    1.0       功率因數
    20    frequency         Float32  R    60.0      頻率 (Hz)
    22    energy_total      Float32  R    0.0       累積電量 (kWh)
    24    status            UInt16   R    1         狀態

操作方式：
  1. 啟動此 example
  2. 用任意 Modbus TCP client（如 ModbusPoll、pymodbus）連線 127.0.0.1:5020
  3. 寫入 PCS1 (unit=10) addr=0 Float32 值來改變 P setpoint
  4. 觀察 terminal 上的即時 dashboard 變化

Run: uv run python examples/20_multi_meter_simulation.py
Run: uv run python examples/20_multi_meter_simulation.py --curve fp_step
Stop: Ctrl+C
"""

import argparse
import asyncio
import sys

# Windows 環境下強制 UTF-8 輸出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.equipment.simulation.curve import CurvePoint, CurveRegistry, CurveType
from csp_lib.modbus_server import (
    BMSSimConfig,
    ControllabilityMode,
    DeviceLinkConfig,
    LoadSimConfig,
    MeterAggregationConfig,
    MicrogridConfig,
    MicrogridSimulator,
    PCSSimConfig,
    PowerMeterSimConfig,
    ServerConfig,
    SimulationServer,
)
from csp_lib.modbus_server.behaviors.curve import CurveBehavior
from csp_lib.modbus_server.simulator.bms import BMSSimulator, default_bms_config
from csp_lib.modbus_server.simulator.load import default_load_config
from csp_lib.modbus_server.simulator.pcs import PCSSimulator, default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import PowerMeterSimulator, default_meter_config

SIM_HOST = "127.0.0.1"
SIM_PORT = 5020
DASHBOARD_INTERVAL = 2.0  # 每 N 秒刷新 dashboard


# ============================================================
# 測試曲線定義（使用 CurveRegistry）
# ============================================================


def create_curve_registry() -> CurveRegistry:
    """建立預定義的測試曲線庫

    CurvePoint 支援三種模式：
    - Step:          CurvePoint(value=380, duration=10, ...)           固定值
    - Ramp to target: CurvePoint(value=380, duration=60, ..., end_value=350)  線性到目標
    - Ramp by rate:   CurvePoint(value=60, duration=100, ..., rate=-0.01)     按速率變化

    使用者可自行新增曲線：
        registry.register("my_curve", lambda: iter([
            CurvePoint(value=380, duration=10, curve_type=CurveType.VOLTAGE),
            CurvePoint(value=380, duration=60, curve_type=CurveType.VOLTAGE, end_value=350),
        ]))
    """
    registry = CurveRegistry()

    # QV 測試：電壓 ramp 下降 → 回復（測試 QV 策略的無功調節）
    registry.register(
        "qv_ramp",
        lambda: iter(
            [
                CurvePoint(value=380.0, duration=5.0, curve_type=CurveType.VOLTAGE),
                CurvePoint(value=380.0, duration=20.0, curve_type=CurveType.VOLTAGE, end_value=355.0),
                CurvePoint(value=355.0, duration=10.0, curve_type=CurveType.VOLTAGE),
                CurvePoint(value=355.0, duration=20.0, curve_type=CurveType.VOLTAGE, end_value=380.0),
                CurvePoint(value=380.0, duration=5.0, curve_type=CurveType.VOLTAGE),
            ]
        ),
    )

    # FP 測試：頻率 ramp 擾動，-0.01 Hz/s（測試 FP 策略的有功調節）
    registry.register(
        "fp_ramp",
        lambda: iter(
            [
                CurvePoint(value=60.0, duration=5.0, curve_type=CurveType.FREQUENCY),
                CurvePoint(value=60.0, duration=50.0, curve_type=CurveType.FREQUENCY, rate=-0.01),  # → 59.5
                CurvePoint(value=59.5, duration=10.0, curve_type=CurveType.FREQUENCY),
                CurvePoint(value=59.5, duration=50.0, curve_type=CurveType.FREQUENCY, rate=0.01),  # → 60.0
                CurvePoint(value=60.0, duration=5.0, curve_type=CurveType.FREQUENCY),
            ]
        ),
    )

    # 電壓驟降 (voltage sag)：快速 ramp down → hold → ramp up
    registry.register(
        "voltage_sag",
        lambda: iter(
            [
                CurvePoint(value=380.0, duration=5.0, curve_type=CurveType.VOLTAGE),
                CurvePoint(value=380.0, duration=3.0, curve_type=CurveType.VOLTAGE, end_value=320.0),
                CurvePoint(value=320.0, duration=5.0, curve_type=CurveType.VOLTAGE),
                CurvePoint(value=320.0, duration=10.0, curve_type=CurveType.VOLTAGE, end_value=380.0),
                CurvePoint(value=380.0, duration=5.0, curve_type=CurveType.VOLTAGE),
            ]
        ),
    )

    # FP step 測試（階梯式，向後相容）
    registry.register(
        "fp_step",
        lambda: iter(
            [
                CurvePoint(value=60.0, duration=10.0, curve_type=CurveType.FREQUENCY),
                CurvePoint(value=59.7, duration=10.0, curve_type=CurveType.FREQUENCY),
                CurvePoint(value=59.5, duration=10.0, curve_type=CurveType.FREQUENCY),
                CurvePoint(value=60.3, duration=10.0, curve_type=CurveType.FREQUENCY),
                CurvePoint(value=60.0, duration=10.0, curve_type=CurveType.FREQUENCY),
            ]
        ),
    )

    return registry


# ============================================================
# 建立 MicrogridSimulator 與所有設備
# ============================================================


def create_microgrid() -> tuple[MicrogridSimulator, BMSSimulator, BMSSimulator, PCSSimulator, PCSSimulator]:
    """建立完整微電網：2 PCS + 2 BMS + 1 Load + 4 Meter"""

    mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

    # PCS
    pcs1 = PCSSimulator(
        config=default_pcs_config(device_id="pcs_1", unit_id=10),
        sim_config=PCSSimConfig(capacity_kwh=100.0, p_ramp_rate=50.0),
    )
    pcs1._running = True

    pcs2 = PCSSimulator(
        config=default_pcs_config(device_id="pcs_2", unit_id=11),
        sim_config=PCSSimConfig(capacity_kwh=100.0, p_ramp_rate=50.0),
    )
    pcs2._running = True

    # BMS
    bms1 = BMSSimulator(
        config=default_bms_config(device_id="bms_1", unit_id=20),
        sim_config=BMSSimConfig(capacity_kwh=100.0, initial_soc=80.0),
    )
    bms2 = BMSSimulator(
        config=default_bms_config(device_id="bms_2", unit_id=21),
        sim_config=BMSSimConfig(capacity_kwh=100.0, initial_soc=60.0),
    )

    # 負載（不可控，固定 30kW）
    load_sim = default_load_config(device_id="load_1", unit_id=30, controllable=False)
    from csp_lib.modbus_server.simulator.load import LoadSimulator

    load = LoadSimulator(
        config=load_sim,
        sim_config=LoadSimConfig(
            controllability=ControllabilityMode.UNCONTROLLABLE,
            power_factor=0.9,
            ramp_rate=1000.0,
            base_load=30.0,
            load_noise=0.0,
        ),
    )

    # 電表
    meter1 = PowerMeterSimulator(
        config=default_meter_config(device_id="meter_pcs1", unit_id=1),
        sim_config=PowerMeterSimConfig(power_sign=-1.0, voltage_noise=0.0, frequency_noise=0.0),
    )
    meter2 = PowerMeterSimulator(
        config=default_meter_config(device_id="meter_pcs2", unit_id=2),
        sim_config=PowerMeterSimConfig(power_sign=-1.0, voltage_noise=0.0, frequency_noise=0.0),
    )
    meter_load = PowerMeterSimulator(
        config=default_meter_config(device_id="meter_load", unit_id=3),
        sim_config=PowerMeterSimConfig(power_sign=1.0, voltage_noise=0.0, frequency_noise=0.0),
    )
    meter_total = PowerMeterSimulator(
        config=default_meter_config(device_id="meter_total", unit_id=4),
        sim_config=PowerMeterSimConfig(power_sign=-1.0, voltage_noise=0.0, frequency_noise=0.0),
    )

    # 註冊
    mg.add_pcs(pcs1)
    mg.add_pcs(pcs2)
    mg.add_bms(bms1)
    mg.add_bms(bms2)
    mg.add_load(load)
    mg.add_meter(meter1, "meter_pcs1")
    mg.add_meter(meter2, "meter_pcs2")
    mg.add_meter(meter_load, "meter_load")
    mg.add_meter(meter_total, "meter_total")

    # 連結
    mg.link_pcs_bms("pcs_1", "bms_1")
    mg.link_pcs_bms("pcs_2", "bms_2")
    mg.add_device_link(DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_pcs1", loss_factor=0.02))
    mg.add_device_link(DeviceLinkConfig(source_device_id="pcs_2", target_meter_id="meter_pcs2", loss_factor=0.02))
    mg.add_device_link(DeviceLinkConfig(source_device_id="load_1", target_meter_id="meter_load"))
    mg.add_meter_aggregation(
        MeterAggregationConfig(
            source_meter_ids=("meter_pcs1", "meter_pcs2", "meter_load"),
            target_meter_id="meter_total",
        )
    )

    return mg, bms1, bms2, pcs1, pcs2


# ============================================================
# Dashboard
# ============================================================


def print_dashboard(
    mg: MicrogridSimulator,
    bms1: BMSSimulator,
    bms2: BMSSimulator,
    pcs1: PCSSimulator,
    pcs2: PCSSimulator,
) -> None:
    """清屏後印出即時 dashboard"""
    # ANSI clear screen + cursor home
    print("\033[2J\033[H", end="")

    print("=" * 70)
    print("  Example 20: 多電表微電網模擬 (Ctrl+C 停止)")
    print(f"  SimulationServer: {SIM_HOST}:{SIM_PORT}")
    print("=" * 70)

    # 電網 V/F
    meter_total = mg.meters.get("meter_total")
    grid_v = meter_total.get_value("voltage_a") if meter_total else 0.0
    grid_f = meter_total.get_value("frequency") if meter_total else 0.0
    v_mode = (
        "CURVE"
        if mg._voltage_curve and mg._voltage_curve.is_running
        else ("OVERRIDE" if mg._voltage_override is not None else "CONFIG")
    )
    f_mode = (
        "CURVE"
        if mg._frequency_curve and mg._frequency_curve.is_running
        else ("OVERRIDE" if mg._frequency_override is not None else "CONFIG")
    )
    print("\n  ── Grid ──")
    print(f"  Voltage={grid_v:.1f} V ({v_mode}) | Frequency={grid_f:.2f} Hz ({f_mode})")

    # PCS 狀態
    print("\n  ── PCS ──")
    for name, pcs in [("PCS1", pcs1), ("PCS2", pcs2)]:
        p_set = pcs.get_value("p_setpoint") or 0.0
        p_act = pcs.get_value("p_actual") or 0.0
        mode = "ON" if pcs._running else "OFF"
        print(f"  {name} (unit={pcs.unit_id:2d}) | Setpoint={p_set:+7.1f} kW | Actual={p_act:+7.1f} kW | {mode}")

    # BMS 狀態
    print("\n  ── BMS ──")
    for name, bms in [("BMS1", bms1), ("BMS2", bms2)]:
        soc = bms.get_value("soc") or 0.0
        temp = bms.get_value("temperature") or 0.0
        v = bms.get_value("voltage") or 0.0
        i = bms.get_value("current") or 0.0
        status = int(bms.get_value("status") or 0)
        alarm = int(bms.get_value("alarm_register") or 0)
        status_text = {0: "STANDBY", 1: "CHARGING", 2: "DISCHARGING"}.get(status, "?")
        print(
            f"  {name} (unit={bms.unit_id:2d}) | SOC={soc:5.1f}% | T={temp:5.1f}°C "
            f"| V={v:6.0f}V | I={i:+7.1f}A | {status_text:12s} | alarm=0x{alarm:04X}"
        )

    # 電表
    print("\n  ── Meters ──")
    print(f"  {'Name':12s} {'Sign':4s} | {'P (kW)':>10s} | {'Q (kVar)':>10s} | {'Energy (kWh)':>13s}")
    print(f"  {'─' * 62}")
    for mid, meter in mg.meters.items():
        p = meter.get_value("active_power") or 0.0
        q = meter.get_value("reactive_power") or 0.0
        e = meter.get_value("energy_total") or 0.0
        sign = "表前" if meter.power_sign < 0 else "表後"
        print(f"  {mid:12s} {sign:4s} | {p:+10.1f} | {q:+10.1f} | {e:+13.4f}")

    # 提示
    print("\n  ── Modbus 操作 ──")
    print("  PCS setpoint: unit=10/11, addr=0, Float32 (+放電/-充電)")
    print("  BMS SOC:      unit=20/21, addr=0, Float32 (0~100, debug 設定)")
    print("  BMS 溫度:     unit=20/21, addr=8, Float32 (>55 觸發過溫 alarm)")
    print("\n  ── 啟動參數 (--curve) ──")
    print("  qv_ramp       電壓 ramp 380→355→380 V（各 20s 線性）")
    print("  fp_ramp       頻率 ramp 60→59.5→60 Hz（-0.01 Hz/s）")
    print("  fp_step       頻率階梯 60→59.7→59.5→60.3→60 Hz")
    print("  voltage_sag   電壓驟降 380→320→380 V（快降慢回）")
    print()


# ============================================================
# 主程式
# ============================================================


async def main(curve_name: str | None = None) -> None:
    mg, bms1, bms2, pcs1, pcs2 = create_microgrid()
    registry = create_curve_registry()

    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))
    server.set_microgrid(mg)

    async with server:
        print(f"SimulationServer 啟動: {SIM_HOST}:{SIM_PORT} ({len(server.simulators)} devices)")
        print(f"可用曲線: {registry.list_curves()}")

        # 啟動指定曲線
        if curve_name:
            curve = registry.get_curve(curve_name)
            if curve is None:
                print(f"  曲線 '{curve_name}' 不存在，使用 config 預設值")
            else:
                # 判斷曲線類型：名稱含 fp/freq → 頻率曲線，其餘 → 電壓曲線
                # 進階用法：直接建立 CurveBehavior
                behavior = CurveBehavior(registry, default_value=380.0)
                if "fp" in curve_name or "freq" in curve_name:
                    behavior = CurveBehavior(registry, default_value=60.0)
                    behavior.start_curve(curve_name)
                    mg.set_frequency_behavior(behavior)
                    print(f"  已啟動頻率曲線: {curve_name}")
                else:
                    behavior.start_curve(curve_name)
                    mg.set_voltage_behavior(behavior)
                    print(f"  已啟動電壓曲線: {curve_name}")
        else:
            print("  未指定曲線，使用 config 預設 V/F (可用 --curve <name> 啟動)")

        # 也可以用簡便 API 直接傳 list：
        # mg.set_voltage_curve([(380, 5), (350, 10), (380, 5)])
        # mg.set_frequency_curve([(60, 5), (59.5, 10), (60, 5)])
        # 或 override 固定值：
        # mg.set_grid_voltage(350.0)
        # mg.set_grid_frequency(59.5)
        print("等待 Modbus client 連線... (Ctrl+C 停止)\n")

        try:
            while True:
                await asyncio.sleep(DASHBOARD_INTERVAL)
                print_dashboard(mg, bms1, bms2, pcs1, pcs2)
        except asyncio.CancelledError:
            pass

    print("\nSimulationServer 已停止")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="多電表微電網模擬")
    parser.add_argument("--curve", type=str, default=None, help="測試曲線名稱 (qv_step, fp_step, voltage_sag)")
    args = parser.parse_args()

    try:
        asyncio.run(main(curve_name=args.curve))
    except KeyboardInterrupt:
        print("\n已停止")
