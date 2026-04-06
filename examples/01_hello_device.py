"""
Example 01: Hello Device — 第一次連線

學習目標：
  - AsyncModbusDevice + Point 定義 + 讀寫 + 事件
  - SimulationServer 模擬真實 Modbus TCP 設備
  - 事件驅動通知（value_change, alarm_triggered）
  - 告警定義與觸發機制

Run:
  uv run python examples/01_hello_device.py
"""

import asyncio

from csp_lib.equipment.alarm import (
    AlarmDefinition,
    AlarmLevel,
    Operator,
    ThresholdAlarmEvaluator,
    ThresholdCondition,
)
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config

# ============================================================
# 模擬伺服器設定
# ============================================================
SIM_HOST, SIM_PORT = "127.0.0.1", 5020


def create_sim() -> SimulationServer:
    """建立模擬伺服器，包含一台 PCS 模擬器"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))
    pcs = PCSSimulator(
        config=default_pcs_config("pcs_01", unit_id=10),
        capacity_kwh=200.0,
        p_ramp_rate=50.0,
    )
    # 設定初始狀態：SOC=70%，運行模式
    pcs.set_value("soc", 70.0)
    pcs.set_value("operating_mode", 1)
    pcs._running = True
    server.add_simulator(pcs)
    return server


# ============================================================
# Step 1: 定義讀取點位（ReadPoint）
# ============================================================
# PCS register 佈局（unit_id=10）：
#   p_actual: addr=4, Float32
#   q_actual: addr=6, Float32
#   soc:      addr=8, Float32

p_actual = ReadPoint(
    name="p_actual",
    address=4,
    data_type=Float32(),
    metadata=PointMetadata(unit="kW", description="實際有功功率"),
)

q_actual = ReadPoint(
    name="q_actual",
    address=6,
    data_type=Float32(),
    metadata=PointMetadata(unit="kVar", description="實際無功功率"),
)

soc = ReadPoint(
    name="soc",
    address=8,
    data_type=Float32(),
    metadata=PointMetadata(unit="%", description="電池荷電狀態"),
)

operating_mode = ReadPoint(
    name="operating_mode",
    address=10,
    data_type=UInt16(),
    metadata=PointMetadata(
        description="運行模式",
        value_map={0: "停機", 1: "運行", 2: "故障"},
    ),
)

# ============================================================
# Step 2: 定義寫入點位（WritePoint）
# ============================================================
# PCS register 佈局：
#   p_setpoint: addr=0, Float32, writable

p_set = WritePoint(
    name="p_setpoint",
    address=0,
    data_type=Float32(),
    validator=RangeValidator(min_value=-200.0, max_value=200.0),
    metadata=PointMetadata(unit="kW", description="有功功率設定值"),
)

# ============================================================
# Step 3: 定義告警（Alarm）
# ============================================================
# 當 SOC < 20% 時觸發 WARNING 等級告警

soc_alarm_evaluator = ThresholdAlarmEvaluator(
    point_name="soc",
    conditions=[
        ThresholdCondition(
            alarm=AlarmDefinition(
                code="SOC_LOW",
                name="SOC 過低",
                level=AlarmLevel.WARNING,
                description="SOC 低於 20%，建議充電",
            ),
            operator=Operator.LT,
            value=20.0,
        ),
    ],
)


async def main() -> None:
    print("=" * 60)
    print("  Example 01: Hello Device — 第一次連線")
    print("=" * 60)

    # ========================================================
    # Step 4: 啟動模擬伺服器
    # ========================================================
    print("\n=== Step 1: 啟動模擬伺服器 ===")
    sim_server = create_sim()
    async with sim_server:
        print(f"  模擬伺服器已啟動：{SIM_HOST}:{SIM_PORT}")

        # ====================================================
        # Step 5: 建立 Modbus 客戶端與設備
        # ====================================================
        print("\n=== Step 2: 建立 AsyncModbusDevice ===")
        client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
        config = DeviceConfig(
            device_id="pcs_01",
            unit_id=10,
            read_interval=1.0,
            disconnect_threshold=5,
        )
        device = AsyncModbusDevice(
            config=config,
            client=client,
            always_points=[p_actual, q_actual, soc, operating_mode],
            write_points=[p_set],
            alarm_evaluators=[soc_alarm_evaluator],
        )
        print(f"  設備建立完成：{device}")

        # ====================================================
        # Step 6: 註冊事件處理器
        # ====================================================
        print("\n=== Step 3: 註冊事件處理器 ===")

        async def on_value_change(payload) -> None:
            print(f"  [VALUE_CHANGE] {payload.point_name}: {payload.old_value} -> {payload.new_value}")

        async def on_alarm_triggered(payload) -> None:
            event = payload.alarm_event
            print(f"  [ALARM] {event.alarm.code}: {event.alarm.name} ({event.alarm.level.name})")

        async def on_alarm_cleared(payload) -> None:
            event = payload.alarm_event
            print(f"  [CLEAR] {event.alarm.code}: {event.alarm.name}")

        cancel_vc = device.on("value_change", on_value_change)
        cancel_alarm = device.on("alarm_triggered", on_alarm_triggered)
        cancel_clear = device.on("alarm_cleared", on_alarm_cleared)
        print("  已註冊 value_change, alarm_triggered, alarm_cleared 事件")

        # ====================================================
        # Step 7: 連線並讀取設備值
        # ====================================================
        print("\n=== Step 4: 連線並讀取設備值 ===")
        async with device:
            # 等待第一次讀取完成
            await asyncio.sleep(1.5)

            values = device.latest_values
            print("  最新讀取值（latest_values）：")
            for name, val in values.items():
                print(f"    {name}: {val}")

            # ================================================
            # Step 8: 寫入功率設定值
            # ================================================
            print("\n=== Step 5: 寫入 P 設定值 = 50.0 kW ===")
            result = await device.write("p_setpoint", 50.0)
            print(f"  寫入結果：{result.status.value}")

            # 等待 PCS 模擬器追蹤到 setpoint
            print("\n=== Step 6: 觀察 P 追蹤（等待 3 秒）===")
            for i in range(3):
                await asyncio.sleep(1.0)
                p_val = device.latest_values.get("p_actual", "N/A")
                print(f"  第 {i + 1} 秒 — p_actual = {p_val}")

            # ================================================
            # Step 9: 觸發告警（設定 SOC = 15%）
            # ================================================
            print("\n=== Step 7: 觸發 SOC 低告警（設定 SOC=15%）===")
            pcs_sim = sim_server.simulators[10]
            pcs_sim.set_value("soc", 15.0)
            print("  已將模擬器 SOC 設為 15%")

            # 等待讀取到新值並觸發告警
            await asyncio.sleep(2.0)
            print(f"  設備 is_protected: {device.is_protected}")
            print(f"  活躍告警數量: {len(device.active_alarms)}")
            for alarm_state in device.active_alarms:
                print(
                    f"    [{alarm_state.definition.level.name}] {alarm_state.definition.code}: {alarm_state.definition.name}"
                )

            # ================================================
            # Step 10: 恢復 SOC，觀察告警清除
            # ================================================
            print("\n=== Step 8: 恢復 SOC = 50%，觀察告警清除 ===")
            pcs_sim.set_value("soc", 50.0)
            await asyncio.sleep(2.0)
            print(f"  設備 is_protected: {device.is_protected}")
            print(f"  活躍告警數量: {len(device.active_alarms)}")

        # ====================================================
        # 清理
        # ====================================================
        print("\n=== Step 9: 清理 ===")
        cancel_vc()
        cancel_alarm()
        cancel_clear()
        print("  事件處理器已取消")

    # ============================================================
    # 摘要
    # ============================================================
    print("\n" + "=" * 60)
    print("  學到了什麼：")
    print("  1. ReadPoint / WritePoint 定義 Modbus 點位")
    print("  2. AsyncModbusDevice 管理連線、讀取、寫入")
    print("  3. device.on() 註冊事件，value_change 追蹤值變化")
    print("  4. ThresholdAlarmEvaluator 定義告警條件")
    print("  5. device.is_protected / device.active_alarms 查看告警狀態")
    print("  6. async with device 管理生命週期（連線 → 讀取 → 斷線）")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
