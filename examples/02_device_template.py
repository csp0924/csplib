"""
Example 02: Device Template — 設備模板

學習目標：
  - EquipmentTemplate 定義可重用的設備模型
  - DeviceFactory 從模板批次建立多台設備
  - DeviceConfig 設定（read_interval, auto_reconnect）
  - 同時連線多台設備，展示模板複用優勢

Run:
  uv run python examples/02_device_template.py
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
from csp_lib.equipment.device import DeviceConfig
from csp_lib.equipment.template import DeviceFactory, EquipmentTemplate
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config

# ============================================================
# 模擬伺服器設定
# ============================================================
SIM_HOST, SIM_PORT = "127.0.0.1", 5020


def create_sim() -> SimulationServer:
    """建立模擬伺服器，包含 3 台 PCS 模擬器"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    # 建立 3 台 PCS，各自不同 unit_id 和初始 SOC
    for i, (uid, initial_soc) in enumerate([(10, 80.0), (11, 50.0), (12, 30.0)]):
        pcs = PCSSimulator(
            config=default_pcs_config(f"pcs_{i + 1:02d}", unit_id=uid),
            capacity_kwh=200.0,
            p_ramp_rate=50.0,
        )
        pcs.set_value("soc", initial_soc)
        pcs.set_value("operating_mode", 1)
        pcs._running = True
        server.add_simulator(pcs)

    return server


# ============================================================
# Step 1: 定義 PCS 設備模板（EquipmentTemplate）
# ============================================================
# 模板定義一次，所有同型號設備共用

pcs_template = EquipmentTemplate(
    model="GenericPCS-200kW",
    description="通用型 200kW PCS 模板",
    always_points=(
        ReadPoint(
            name="p_actual",
            address=4,
            data_type=Float32(),
            metadata=PointMetadata(unit="kW", description="實際有功功率"),
        ),
        ReadPoint(
            name="q_actual",
            address=6,
            data_type=Float32(),
            metadata=PointMetadata(unit="kVar", description="實際無功功率"),
        ),
        ReadPoint(
            name="soc",
            address=8,
            data_type=Float32(),
            metadata=PointMetadata(unit="%", description="電池荷電狀態"),
        ),
        ReadPoint(
            name="operating_mode",
            address=10,
            data_type=UInt16(),
            metadata=PointMetadata(
                description="運行模式",
                value_map={0: "停機", 1: "運行", 2: "故障"},
            ),
        ),
    ),
    write_points=(
        WritePoint(
            name="p_setpoint",
            address=0,
            data_type=Float32(),
            validator=RangeValidator(min_value=-200.0, max_value=200.0),
            metadata=PointMetadata(unit="kW", description="有功功率設定值"),
        ),
        WritePoint(
            name="q_setpoint",
            address=2,
            data_type=Float32(),
            validator=RangeValidator(min_value=-100.0, max_value=100.0),
            metadata=PointMetadata(unit="kVar", description="無功功率設定值"),
        ),
    ),
    alarm_evaluators=(
        ThresholdAlarmEvaluator(
            point_name="soc",
            conditions=[
                ThresholdCondition(
                    alarm=AlarmDefinition(
                        code="SOC_LOW",
                        name="SOC 過低",
                        level=AlarmLevel.WARNING,
                        description="SOC 低於 20%",
                    ),
                    operator=Operator.LT,
                    value=20.0,
                ),
                ThresholdCondition(
                    alarm=AlarmDefinition(
                        code="SOC_HIGH",
                        name="SOC 過高",
                        level=AlarmLevel.WARNING,
                        description="SOC 超過 95%",
                    ),
                    operator=Operator.GT,
                    value=95.0,
                ),
            ],
        ),
    ),
)


async def main() -> None:
    print("=" * 60)
    print("  Example 02: Device Template — 設備模板")
    print("=" * 60)

    # ========================================================
    # Step 2: 啟動模擬伺服器
    # ========================================================
    print("\n=== Step 1: 啟動模擬伺服器（3 台 PCS）===")
    sim_server = create_sim()
    async with sim_server:
        print(f"  模擬伺服器已啟動：{SIM_HOST}:{SIM_PORT}")
        for uid, sim in sim_server.simulators.items():
            print(f"  - unit_id={uid}, device_id={sim.device_id}, SOC={sim.get_value('soc')}")

        # ====================================================
        # Step 3: 用模板 + DeviceFactory 建立 3 台設備
        # ====================================================
        print("\n=== Step 2: 用模板建立 3 台 PCS 設備 ===")
        print(f"  模板型號：{pcs_template.model}")
        print(f"  模板描述：{pcs_template.description}")
        print(f"  讀取點位：{[p.name for p in pcs_template.always_points]}")
        print(f"  寫入點位：{[p.name for p in pcs_template.write_points]}")
        print("============================")

        # 定義 3 台設備的配置
        configs = [
            DeviceConfig(device_id="pcs_01", unit_id=10, read_interval=1.0),
            DeviceConfig(device_id="pcs_02", unit_id=11, read_interval=1.0),
            DeviceConfig(device_id="pcs_03", unit_id=12, read_interval=1.0),
        ]

        # 共用同一個 Modbus TCP 連線（因為是同一台模擬伺服器）
        # 使用 client_factory 為每台設備建立獨立的 client
        def client_factory(cfg: DeviceConfig) -> PymodbusTcpClient:
            return PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))

        # 批次建立
        devices = DeviceFactory.create_batch(
            template=pcs_template,
            instances=configs,
            client_factory=client_factory,
        )

        for dev in devices:
            print(f"  已建立設備：{dev.device_id} (unit_id={dev._config.unit_id})")
            print(f"    讀取點位：{[p.name for p in dev.read_points]}")
            print(f"    寫入點位：{dev.write_point_names}")

        # ====================================================
        # Step 4: 同時連線並讀取所有設備
        # ====================================================
        print("\n=== Step 3: 同時連線所有設備 ===")

        # 使用 gather 同時連線（真正的並行）
        await asyncio.gather(*(dev.connect() for dev in devices))
        await asyncio.gather(*(dev.start() for dev in devices))

        print("  所有設備已連線並啟動讀取循環")

        # 等待讀取
        await asyncio.sleep(2.0)

        # ====================================================
        # Step 5: 展示所有設備的即時值
        # ====================================================
        print("\n=== Step 4: 讀取所有設備的即時值 ===")
        for dev in devices:
            values = dev.latest_values
            soc_val = values.get("soc", "N/A")
            p_val = values.get("p_actual", "N/A")
            mode = values.get("operating_mode", "N/A")
            print(f"  {dev.device_id}: SOC={soc_val}, P={p_val} kW, Mode={mode}")

        # ====================================================
        # Step 6: 同時對所有設備下達命令
        # ====================================================
        print("\n=== Step 5: 批次下達功率命令 ===")
        setpoints = [30.0, 50.0, 20.0]
        # 使用 gather 同時寫入（真正的並行）
        results = await asyncio.gather(
            *(dev.write("p_setpoint", sp) for dev, sp in zip(devices, setpoints, strict=True))
        )
        for dev, sp, result in zip(devices, setpoints, results, strict=True):
            print(f"  {dev.device_id}: 寫入 P={sp} kW, 結果={result.status.value}")

        # 等待追蹤
        print("\n=== Step 6: 觀察功率追蹤（等待 3 秒）===")
        for i in range(3):
            await asyncio.sleep(1.0)
            line = f"  第 {i + 1} 秒 —"
            for dev in devices:
                p_val = dev.latest_values.get("p_actual", 0)
                if isinstance(p_val, float):
                    line += f" {dev.device_id}: P={p_val:.1f}"
                else:
                    line += f" {dev.device_id}: P={p_val}"
            print(line)

        # ====================================================
        # Step 7: 展示 DeviceConfig 的差異
        # ====================================================
        print("\n=== Step 7: DeviceConfig 參數說明 ===")
        sample = configs[0]
        print(f"  device_id:           {sample.device_id}")
        print(f"  unit_id:             {sample.unit_id}")
        print(f"  read_interval:       {sample.read_interval} 秒（讀取間隔）")
        print(f"  reconnect_interval:  {sample.reconnect_interval} 秒（重連間隔）")
        print(f"  disconnect_threshold:{sample.disconnect_threshold}（連續失敗次數閾值）")

        # ====================================================
        # 清理
        # ====================================================
        print("\n=== Step 8: 清理 ===")
        for dev in devices:
            await dev.stop()
            await dev.disconnect()
        print("  所有設備已斷線")

    # ============================================================
    # 摘要
    # ============================================================
    print("\n" + "=" * 60)
    print("  學到了什麼：")
    print("  1. EquipmentTemplate 定義可重用的設備模型（點位+告警）")
    print("  2. DeviceFactory.create_batch() 一次建立多台同型設備")
    print("  3. 每台設備有獨立的 DeviceConfig（unit_id, read_interval）")
    print("  4. 模板 + 工廠模式消除重複定義，新增設備只需一行配置")
    print("  5. create_stride() 可用於固定位址步幅的場景（如 BMS sub-module）")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
