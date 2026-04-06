"""
Example 11: ModbusGateway — EMS/SCADA Modbus TCP 閘道

學習目標:
  - ModbusGatewayServer: 對外暴露系統狀態給 EMS/SCADA
  - GatewayRegisterDef: 宣告式 register 定義
  - PollingCallbackSource: 定期從設備同步資料到 gateway register
  - CallbackHook: 寫入事件回呼（EMS 下指令）
  - 用獨立 Modbus TCP client 從 gateway 讀取 register（EMS 視角）

架構:
  SimulationServer (:5020)  ← PCS + 電表模擬
       ↓ (內部連線)
  ModbusGatewayServer (:5021)  ← EMS/SCADA 透過 Modbus TCP 讀寫
       ↑ (PollingCallbackSource)
  設備資料同步

Run: uv run python examples/10_modbus_gateway.py
預計時間: 20 min
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.modbus import ByteOrder, Float32, ModbusTcpConfig, PymodbusTcpClient, RegisterOrder, UInt16
from csp_lib.modbus_gateway import (
    CallbackHook,
    GatewayRegisterDef,
    GatewayServerConfig,
    ModbusGatewayServer,
    PollingCallbackSource,
    RegisterType,
    WatchdogConfig,
)
from csp_lib.modbus_server import (
    MicrogridConfig,
    MicrogridSimulator,
    PCSSimConfig,
    PowerMeterSimConfig,
    ServerConfig,
    SimulationServer,
)
from csp_lib.modbus_server.simulator.pcs import PCSSimulator, default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import PowerMeterSimulator, default_meter_config

# ============================================================
# 常數
# ============================================================

# Modbus 標準位元組順序
BE = ByteOrder.BIG_ENDIAN
HF = RegisterOrder.HIGH_FIRST

SIM_HOST = "127.0.0.1"
SIM_PORT = 5020
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 5021


# ============================================================
# Step 1: 建立 SimulationServer（PCS + 電表）
# ============================================================


def create_simulation() -> tuple[SimulationServer, MicrogridSimulator, PCSSimulator, PowerMeterSimulator]:
    """建立 PCS + 電表的 SimulationServer"""
    mg = MicrogridSimulator(MicrogridConfig(voltage_noise=0.0, frequency_noise=0.0))

    # PCS: 200kW 儲能
    pcs = PCSSimulator(
        config=default_pcs_config(device_id="pcs_1", unit_id=10),
        sim_config=PCSSimConfig(capacity_kwh=200.0, p_ramp_rate=100.0),
    )
    pcs.on_write("start_cmd", 0, 1)  # 啟動 PCS

    # 電表: 市電側
    meter = PowerMeterSimulator(
        config=default_meter_config(device_id="meter_1", unit_id=1),
        sim_config=PowerMeterSimConfig(power_sign=1.0, voltage_noise=0.0, frequency_noise=0.0),
    )

    # 註冊到微電網
    mg.add_pcs(pcs)
    mg.set_meter(meter)

    # 建立 SimulationServer
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))
    server.set_microgrid(mg)

    return server, mg, pcs, meter


# ============================================================
# Step 2: 定義 Gateway Register Map
# ============================================================


def create_gateway_registers() -> list[GatewayRegisterDef]:
    """定義 gateway 暴露給 EMS 的 register

    Register Map:
      HR (Holding Register, 可讀寫):
        0-1: p_command (Float32) — EMS 功率指令 (kW)
        2-3: q_command (Float32) — EMS 無功指令 (kVar)
        4:   mode_command (UInt16) — EMS 模式指令

      IR (Input Register, 唯讀):
        0-1: system_power (Float32) — 系統功率 (kW)
        2-3: system_soc (Float32) — 電池 SOC (%)
        4-5: grid_voltage (Float32) — 電網電壓 (V)
        6-7: grid_frequency (Float32) — 電網頻率 (Hz)
        8:   pcs_status (UInt16) — PCS 狀態
    """
    f32 = Float32()
    u16 = UInt16()

    return [
        # ---- Holding Registers（EMS 可寫入指令）----
        GatewayRegisterDef(
            name="p_command",
            address=0,
            data_type=f32,
            register_type=RegisterType.HOLDING,
            unit="kW",
            initial_value=0.0,
            description="EMS 有功功率指令",
        ),
        GatewayRegisterDef(
            name="q_command",
            address=2,
            data_type=f32,
            register_type=RegisterType.HOLDING,
            unit="kVar",
            initial_value=0.0,
            description="EMS 無功功率指令",
        ),
        GatewayRegisterDef(
            name="mode_command",
            address=4,
            data_type=u16,
            register_type=RegisterType.HOLDING,
            initial_value=0,
            description="EMS 模式指令 (0=idle, 1=charge, 2=discharge)",
        ),
        # ---- Input Registers（唯讀系統狀態）----
        GatewayRegisterDef(
            name="system_power",
            address=0,
            data_type=f32,
            register_type=RegisterType.INPUT,
            unit="kW",
            initial_value=0.0,
            description="系統有功功率",
        ),
        GatewayRegisterDef(
            name="system_soc",
            address=2,
            data_type=f32,
            register_type=RegisterType.INPUT,
            unit="%",
            initial_value=50.0,
            description="電池 SOC",
        ),
        GatewayRegisterDef(
            name="grid_voltage",
            address=4,
            data_type=f32,
            register_type=RegisterType.INPUT,
            unit="V",
            initial_value=380.0,
            description="電網電壓",
        ),
        GatewayRegisterDef(
            name="grid_frequency",
            address=6,
            data_type=f32,
            register_type=RegisterType.INPUT,
            unit="Hz",
            initial_value=60.0,
            description="電網頻率",
        ),
        GatewayRegisterDef(
            name="pcs_status",
            address=8,
            data_type=u16,
            register_type=RegisterType.INPUT,
            initial_value=0,
            description="PCS 運行狀態",
        ),
    ]


# ============================================================
# Step 3: 建立資料同步源（PollingCallbackSource）
# ============================================================


def create_sync_source(pcs: PCSSimulator, meter: PowerMeterSimulator) -> PollingCallbackSource:
    """建立資料同步源，定期從設備讀值同步到 gateway register"""

    async def sync_callback() -> dict[str, object]:
        """從模擬設備讀取即時數據"""
        return {
            "system_power": float(pcs.get_value("p_actual") or 0.0),
            "system_soc": float(pcs.get_value("soc") or 50.0),
            "grid_voltage": float(meter.get_value("voltage_a") or 380.0),
            "grid_frequency": float(meter.get_value("frequency") or 60.0),
            "pcs_status": int(pcs.get_value("operating_mode") or 0),
        }

    return PollingCallbackSource(callback=sync_callback, interval=1.0)


# ============================================================
# Step 4: 建立 Gateway WriteHook（EMS 寫入回呼）
# ============================================================


def create_write_hook(pcs: PCSSimulator) -> CallbackHook:
    """建立寫入回呼，將 EMS 指令轉發到 PCS"""

    async def on_ems_write(register_name: str, old_value: object, new_value: object) -> None:
        """處理 EMS 寫入的功率指令"""
        if register_name == "p_command":
            print(f"  [Gateway] EMS 寫入 P 指令: {old_value} -> {new_value} kW")
            # 轉發到 PCS（在真實場景中這裡會透過 CommandRouter 處理）
            pcs.on_write("p_setpoint", old_value, new_value)
        elif register_name == "q_command":
            print(f"  [Gateway] EMS 寫入 Q 指令: {old_value} -> {new_value} kVar")
            pcs.on_write("q_setpoint", old_value, new_value)
        elif register_name == "mode_command":
            print(f"  [Gateway] EMS 寫入模式指令: {old_value} -> {new_value}")

    return CallbackHook(on_ems_write)


# ============================================================
# Step 5: EMS 視角 — 用 Modbus TCP Client 讀取 Gateway
# ============================================================


async def ems_read_gateway() -> None:
    """模擬 EMS 從 gateway 讀取系統狀態"""
    print("\n=== Step 5: EMS 視角 — 從 Gateway 讀取系統狀態 ===")

    # 建立 Modbus TCP client 連到 gateway
    ems_config = ModbusTcpConfig(host=GATEWAY_HOST, port=GATEWAY_PORT)
    ems_client = PymodbusTcpClient(ems_config)

    try:
        await ems_client.connect()
        print(f"  EMS 已連線到 Gateway ({GATEWAY_HOST}:{GATEWAY_PORT})")

        # 讀取 Input Registers（系統狀態）— FC04
        # 讀取 address=0, count=9（5 個 register: 4 個 Float32 + 1 個 UInt16）
        ir_values = await ems_client.read_input_registers(address=0, count=9, unit_id=1)
        if ir_values is not None:
            f32 = Float32()
            u16 = UInt16()

            system_power = f32.decode(ir_values[0:2], BE, HF)
            system_soc = f32.decode(ir_values[2:4], BE, HF)
            grid_voltage = f32.decode(ir_values[4:6], BE, HF)
            grid_frequency = f32.decode(ir_values[6:8], BE, HF)
            pcs_status = u16.decode(ir_values[8:9], BE, HF)

            print(f"  系統功率: {system_power:.1f} kW")
            print(f"  電池 SOC: {system_soc:.1f} %")
            print(f"  電網電壓: {grid_voltage:.1f} V")
            print(f"  電網頻率: {grid_frequency:.2f} Hz")
            print(f"  PCS 狀態: {pcs_status} ({'運行中' if pcs_status == 1 else '停機'})")
        else:
            print("  讀取 IR 失敗")

        # 讀取 Holding Registers（目前指令值）— FC03
        hr_values = await ems_client.read_holding_registers(address=0, count=5, unit_id=1)
        if hr_values is not None:
            f32 = Float32()
            u16 = UInt16()

            p_cmd = f32.decode(hr_values[0:2], BE, HF)
            q_cmd = f32.decode(hr_values[2:4], BE, HF)
            mode_cmd = u16.decode(hr_values[4:5], BE, HF)

            print(f"\n  目前 P 指令: {p_cmd:.1f} kW")
            print(f"  目前 Q 指令: {q_cmd:.1f} kVar")
            print(f"  目前模式: {mode_cmd}")
        else:
            print("  讀取 HR 失敗")

    finally:
        await ems_client.disconnect()
        print("  EMS 已斷線")


# ============================================================
# Step 6: EMS 視角 — 寫入功率指令到 Gateway
# ============================================================


async def ems_write_gateway() -> None:
    """模擬 EMS 透過 gateway 下達功率指令"""
    print("\n=== Step 6: EMS 視角 — 透過 Gateway 下達功率指令 ===")

    ems_config = ModbusTcpConfig(host=GATEWAY_HOST, port=GATEWAY_PORT)
    ems_client = PymodbusTcpClient(ems_config)

    try:
        await ems_client.connect()

        # EMS 寫入放電 50kW 指令到 HR address=0 (p_command, Float32)
        f32 = Float32()
        registers = f32.encode(50.0, BE, HF)
        await ems_client.write_multiple_registers(address=0, values=registers, unit_id=1)
        print("  EMS 已寫入 P 指令: 50.0 kW (放電)")

        await asyncio.sleep(1.0)

        # 讀回確認
        hr_values = await ems_client.read_holding_registers(address=0, count=2, unit_id=1)
        if hr_values is not None:
            p_cmd = f32.decode(hr_values[0:2], BE, HF)
            print(f"  確認 P 指令已生效: {p_cmd:.1f} kW")

    finally:
        await ems_client.disconnect()


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    print("=" * 60)
    print("  Example 11: ModbusGateway — EMS/SCADA 整合閘道")
    print("=" * 60)

    # ---- Step 1: 啟動 SimulationServer ----
    print("\n=== Step 1: 啟動 SimulationServer ===")
    sim_server, mg, pcs, meter = create_simulation()

    # ---- Step 2: 定義 Gateway Register Map ----
    print("\n=== Step 2: 定義 Gateway Register Map ===")
    register_defs = create_gateway_registers()
    for reg in register_defs:
        rtype = "HR" if reg.register_type == RegisterType.HOLDING else "IR"
        print(
            f"  [{rtype}] addr={reg.address:3d} {reg.name:20s} ({reg.data_type.__class__.__name__}) {reg.description}"
        )

    # ---- Step 3: 建立 Gateway ----
    print("\n=== Step 3: 建立 ModbusGatewayServer ===")
    gateway_config = GatewayServerConfig(
        host=GATEWAY_HOST,
        port=GATEWAY_PORT,
        unit_id=1,
        watchdog=WatchdogConfig(timeout_seconds=30.0, enabled=False),
    )

    # 資料同步源
    sync_source = create_sync_source(pcs, meter)

    # 寫入回呼
    write_hook = create_write_hook(pcs)

    gateway = ModbusGatewayServer(
        config=gateway_config,
        register_defs=register_defs,
        hooks=[write_hook],
        sync_sources=[sync_source],
    )
    print(f"  Gateway 設定: {GATEWAY_HOST}:{GATEWAY_PORT}, unit_id=1")
    print(
        f"  Register 數: {len(register_defs)} ({sum(1 for r in register_defs if r.register_type == RegisterType.HOLDING)} HR + {sum(1 for r in register_defs if r.register_type == RegisterType.INPUT)} IR)"
    )

    # ---- Step 4: 啟動並執行 ----
    print("\n=== Step 4: 啟動 SimulationServer + Gateway ===")
    async with sim_server:
        print(f"  SimulationServer 啟動: {SIM_HOST}:{SIM_PORT}")

        async with gateway:
            print(f"  ModbusGatewayServer 啟動: {GATEWAY_HOST}:{GATEWAY_PORT}")

            # 等待資料同步穩定
            await asyncio.sleep(2.0)

            # 透過 gateway API 直接讀取 register（程式化存取）
            print("\n--- Gateway 程式化存取 ---")
            all_regs = gateway.get_all_registers()
            for name, value in sorted(all_regs.items()):
                print(f"  {name}: {value}")

            # ---- Step 5: EMS 讀取 ----
            await ems_read_gateway()

            # ---- Step 6: EMS 寫入指令 ----
            await ems_write_gateway()

            # 等待 PCS 追蹤指令
            print("\n=== Step 7: 觀察 PCS 追蹤指令 ===")
            for i in range(3):
                await asyncio.sleep(1.5)
                p_actual = float(pcs.get_value("p_actual") or 0.0)
                soc = float(pcs.get_value("soc") or 0.0)
                gw_power = gateway.get_register("system_power")
                print(
                    f"  [t={i + 1}] PCS P_actual={p_actual:+.1f} kW | SOC={soc:.1f}% | Gateway.system_power={gw_power}"
                )

    print("\n--- 完成 ---")
    print("  SimulationServer 和 Gateway 已停止")
    print("\n要點回顧:")
    print("  1. GatewayRegisterDef 定義 HR/IR register map")
    print("  2. PollingCallbackSource 定期同步設備資料到 gateway")
    print("  3. CallbackHook 處理 EMS 寫入事件")
    print("  4. EMS 用標準 Modbus TCP 協定 (FC03/FC04/FC16) 讀寫 gateway")


if __name__ == "__main__":
    asyncio.run(main())
