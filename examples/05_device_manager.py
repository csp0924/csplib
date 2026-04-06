"""
Example 05: Device Manager — 設備管理

學習目標：
  - UnifiedDeviceManager 統一管理設備生命週期
  - InMemoryBatchUploader 記憶體內資料上傳（不需 MongoDB）
  - InMemoryAlarmRepository 記憶體內告警持久化
  - UnifiedConfig 配置各子管理器
  - 設備資料自動上傳與告警自動持久化

Run:
  uv run python examples/05_device_manager.py
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
from csp_lib.manager import (
    InMemoryAlarmRepository,
    InMemoryBatchUploader,
    UnifiedConfig,
    UnifiedDeviceManager,
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

# PCS 讀取點位（含告警定義）
pcs_read_points = [
    ReadPoint(name="p_actual", address=4, data_type=Float32(), metadata=PointMetadata(unit="kW")),
    ReadPoint(name="q_actual", address=6, data_type=Float32(), metadata=PointMetadata(unit="kVar")),
    ReadPoint(name="soc", address=8, data_type=Float32(), metadata=PointMetadata(unit="%")),
    ReadPoint(name="operating_mode", address=10, data_type=UInt16()),
]

pcs_write_points = [
    WritePoint(
        name="p_setpoint",
        address=0,
        data_type=Float32(),
        validator=RangeValidator(min_value=-200.0, max_value=200.0),
    ),
]

# PCS 告警定義
pcs_alarm_evaluators = [
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
                    code="SOC_CRITICAL",
                    name="SOC 嚴重過低",
                    level=AlarmLevel.ALARM,
                    description="SOC 低於 5%",
                ),
                operator=Operator.LT,
                value=5.0,
            ),
        ],
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
    print("  Example 05: Device Manager — 設備管理")
    print("=" * 60)

    # ========================================================
    # Step 1: 啟動模擬伺服器
    # ========================================================
    print("\n=== Step 1: 啟動模擬伺服器 ===")
    sim_server = create_sim()
    async with sim_server:
        print(f"  模擬伺服器已啟動：{SIM_HOST}:{SIM_PORT}")

        # ====================================================
        # Step 2: 建立記憶體內的上傳器和告警 Repository
        # ====================================================
        print("\n=== Step 2: 建立 InMemory 上傳器與告警 Repository ===")
        batch_uploader = InMemoryBatchUploader()
        alarm_repository = InMemoryAlarmRepository()
        print("  InMemoryBatchUploader: 將設備資料儲存在記憶體中（取代 MongoDB）")
        print("  InMemoryAlarmRepository: 將告警記錄儲存在記憶體中")

        # ====================================================
        # Step 3: 建立 UnifiedConfig
        # ====================================================
        print("\n=== Step 3: 建立 UnifiedConfig ===")
        unified_config = UnifiedConfig(
            alarm_repository=alarm_repository,
            mongo_uploader=batch_uploader,
        )
        print(f"  alarm_repository: {type(alarm_repository).__name__}")
        print(f"  mongo_uploader: {type(batch_uploader).__name__}")
        print("  (redis_client、notification_dispatcher 未配置 — 會自動跳過)")

        # ====================================================
        # Step 4: 建立 UnifiedDeviceManager
        # ====================================================
        print("\n=== Step 4: 建立 UnifiedDeviceManager ===")
        manager = UnifiedDeviceManager(unified_config)
        print(f"  {manager}")

        # ====================================================
        # Step 5: 建立設備並註冊到管理器
        # ====================================================
        print("\n=== Step 5: 建立設備並註冊 ===")

        pcs_client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
        pcs_device = AsyncModbusDevice(
            config=DeviceConfig(device_id="pcs_01", unit_id=10, read_interval=1.0),
            client=pcs_client,
            always_points=pcs_read_points,
            write_points=pcs_write_points,
            alarm_evaluators=pcs_alarm_evaluators,
        )

        meter_client = PymodbusTcpClient(ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT))
        meter_device = AsyncModbusDevice(
            config=DeviceConfig(device_id="meter_01", unit_id=1, read_interval=1.0),
            client=meter_client,
            always_points=meter_read_points,
        )

        # 註冊設備到管理器（指定 collection_name 用於資料上傳）
        manager.register(pcs_device, collection_name="pcs_data")
        manager.register(meter_device, collection_name="meter_data")
        print("  已註冊 PCS 設備: pcs_01 (collection=pcs_data)")
        print("  已註冊電表設備: meter_01 (collection=meter_data)")

        # ====================================================
        # Step 6: 啟動管理器，觀察資料自動上傳
        # ====================================================
        print("\n=== Step 6: 啟動管理器 ===")

        async with manager:
            print("  UnifiedDeviceManager 已啟動")
            print("  設備讀取循環已運行...")

            # 等待資料累積
            print("\n=== Step 7: 等待資料累積（5 秒）===")
            for i in range(5):
                await asyncio.sleep(1.0)
                pcs_docs = batch_uploader.get_documents("pcs_data")
                meter_docs = batch_uploader.get_documents("meter_data")
                print(f"  第 {i + 1} 秒 — PCS 資料: {len(pcs_docs)} 筆, 電表資料: {len(meter_docs)} 筆")

            # ================================================
            # Step 8: 查看上傳的資料
            # ================================================
            print("\n=== Step 8: 查看上傳的資料 ===")
            all_docs = batch_uploader.get_all_documents()
            for collection, docs in all_docs.items():
                print(f"\n  Collection '{collection}': {len(docs)} 筆")
                if docs:
                    # 印出最後一筆資料的 key
                    last_doc = docs[-1]
                    print(f"    最新一筆 keys: {list(last_doc.keys())}")
                    # 印出部分值
                    for key, val in list(last_doc.items())[:5]:
                        if isinstance(val, float):
                            print(f"      {key}: {val:.2f}")
                        else:
                            print(f"      {key}: {val}")

            # ================================================
            # Step 9: 觸發告警並查看持久化
            # ================================================
            print("\n=== Step 9: 觸發告警（設定 SOC=15%）===")
            pcs_sim = sim_server.simulators[10]
            pcs_sim.set_value("soc", 15.0)
            print("  已將模擬器 SOC 設為 15%")

            # 等待告警觸發與持久化
            await asyncio.sleep(3.0)

            # 查詢告警記錄
            active_alarms = await alarm_repository.get_active_alarms()
            all_records = alarm_repository.get_all_records()
            print(f"\n  活躍告警數量: {len(active_alarms)}")
            for record in active_alarms:
                print(
                    f"    [{record.alarm_type.value}] {record.alarm_code}: "
                    f"device={record.device_id}, level={record.level.name}"
                )

            print(f"  告警記錄總數: {len(all_records)}")

            # ================================================
            # Step 10: 恢復 SOC，觀察告警解除
            # ================================================
            print("\n=== Step 10: 恢復 SOC=50%，觀察告警解除 ===")
            pcs_sim.set_value("soc", 50.0)
            await asyncio.sleep(3.0)

            active_alarms = await alarm_repository.get_active_alarms()
            print(f"  活躍告警數量: {len(active_alarms)}")

            all_records = alarm_repository.get_all_records()
            for _key, record in all_records.items():
                print(f"    {record.alarm_code}: status={record.status}")

        # ====================================================
        # 清理
        # ====================================================
        print("\n=== Step 11: 清理 ===")
        # manager 的 async with 會自動斷線，不需手動 disconnect
        print("  設備已斷線，管理器已停止")

    # ============================================================
    # 摘要
    # ============================================================
    print("\n" + "=" * 60)
    print("  學到了什麼：")
    print("  1. UnifiedDeviceManager：統一管理設備讀取、告警、上傳")
    print("  2. InMemoryBatchUploader：記憶體內資料上傳（不需 MongoDB）")
    print("  3. InMemoryAlarmRepository：記憶體內告警持久化")
    print("  4. UnifiedConfig：可選配置各子管理器（未設定的自動跳過）")
    print("  5. manager.register()：自動訂閱設備事件到所有子管理器")
    print("  6. async with manager：管理器控制設備讀取循環的啟停")
    print("  7. 告警自動持久化：設備告警觸發/解除自動寫入 Repository")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
