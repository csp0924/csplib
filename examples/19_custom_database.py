"""
csp_lib Example 19: Custom Database — 使用 In-Memory Repository 替代 MongoDB

展示如何在零外部依賴（無 MongoDB、無 Redis）的環境下，
透過內建的 InMemory 實作運行完整的設備管理系統。

架構：
  SimulationServer (Modbus TCP 模擬器)
       ↕ TCP
  AsyncModbusDevice (PCS + 電表)
       ↓ events
  UnifiedDeviceManager
    ├── DeviceManager           — 設備讀取生命週期管理
    ├── AlarmPersistenceManager — 告警持久化（InMemoryAlarmRepository）
    ├── WriteCommandManager     — 寫入指令管理（InMemoryCommandRepository）
    └── DataUploadManager       — 資料上傳（InMemoryBatchUploader）

  本範例展示三種 InMemory Repository 取代 MongoDB 的用法：
    1. InMemoryBatchUploader   — 替代 MongoBatchUploader
    2. InMemoryAlarmRepository — 替代 MongoAlarmRepository
    3. InMemoryCommandRepository — 替代 MongoCommandRepository

Run: uv run python examples/19_custom_database.py
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
from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, ReadCompletePayload
from csp_lib.manager import (
    InMemoryAlarmRepository,
    InMemoryBatchUploader,
    InMemoryCommandRepository,
    UnifiedConfig,
    UnifiedDeviceManager,
    WriteCommand,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, PowerMeterSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import default_meter_config

# ============================================================
# 常量
# ============================================================

SIM_HOST = "127.0.0.1"
SIM_PORT = 5030  # 避免與其他範例衝突


# ============================================================
# SimulationServer 建立
# ============================================================


def create_simulation_server() -> tuple[SimulationServer, PCSSimulator]:
    """建立包含 PCS 和電表的模擬伺服器，回傳 server 與 PCS 模擬器（供後續操作 SOC）"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    # PCS 模擬器 — unit_id=10, 初始 SOC=50%（正常範圍）
    pcs_config = default_pcs_config(device_id="pcs_01", unit_id=10)
    pcs_sim = PCSSimulator(config=pcs_config, capacity_kwh=200.0, p_ramp_rate=50.0)
    pcs_sim.set_value("soc", 50.0)
    pcs_sim.set_value("operating_mode", 1)
    pcs_sim._running = True

    # 電表模擬器 — unit_id=1
    meter_config = default_meter_config(device_id="meter_01", unit_id=1)
    meter_sim = PowerMeterSimulator(config=meter_config, voltage_noise=1.5, frequency_noise=0.01)
    meter_sim.set_system_reading(v=380.0, f=60.0, p=20.0, q=5.0)

    server.add_simulator(pcs_sim)
    server.add_simulator(meter_sim)

    return server, pcs_sim


# ============================================================
# AsyncModbusDevice 建立（帶 SOC 門檻告警）
# ============================================================


def create_devices() -> tuple[AsyncModbusDevice, AsyncModbusDevice]:
    """建立 PCS（帶 SOC 告警）和電表的 AsyncModbusDevice"""
    tcp_config = ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT, timeout=2.0)
    f32 = Float32()
    u16 = UInt16()

    # --- PCS 設備（含告警評估器）---
    pcs_read_points = [
        ReadPoint(
            name="p_actual",
            address=4,
            data_type=f32,
            metadata=PointMetadata(unit="kW", description="實際有功功率"),
        ),
        ReadPoint(
            name="q_actual",
            address=6,
            data_type=f32,
            metadata=PointMetadata(unit="kVar", description="實際無功功率"),
        ),
        ReadPoint(
            name="soc",
            address=8,
            data_type=f32,
            metadata=PointMetadata(unit="%", description="電池 SOC"),
        ),
        ReadPoint(
            name="operating_mode",
            address=10,
            data_type=u16,
            metadata=PointMetadata(description="運行模式", value_map={0: "Standby", 1: "Running"}),
        ),
    ]

    pcs_write_points = [
        WritePoint(
            name="p_set",
            address=0,
            data_type=f32,
            validator=RangeValidator(min_value=-200.0, max_value=200.0),
            metadata=PointMetadata(unit="kW", description="有功功率設定點"),
        ),
        WritePoint(
            name="q_set",
            address=2,
            data_type=f32,
            validator=RangeValidator(min_value=-100.0, max_value=100.0),
            metadata=PointMetadata(unit="kVar", description="無功功率設定點"),
        ),
    ]

    # SOC 門檻告警：SOC > 90% (WARNING), SOC < 10% (ALARM)
    soc_alarms = ThresholdAlarmEvaluator(
        point_name="soc",
        conditions=[
            ThresholdCondition(
                alarm=AlarmDefinition(
                    code="SOC_HIGH",
                    name="SOC 過高",
                    level=AlarmLevel.WARNING,
                    description="電池 SOC 超過 90% — 有過充風險",
                ),
                operator=Operator.GT,
                value=90.0,
            ),
            ThresholdCondition(
                alarm=AlarmDefinition(
                    code="SOC_LOW",
                    name="SOC 過低",
                    level=AlarmLevel.ALARM,
                    description="電池 SOC 低於 10% — 有深度放電風險",
                ),
                operator=Operator.LT,
                value=10.0,
            ),
        ],
    )

    pcs_client = PymodbusTcpClient(tcp_config)
    pcs_device = AsyncModbusDevice(
        config=DeviceConfig(
            device_id="pcs_01",
            unit_id=10,
            read_interval=1.0,
            disconnect_threshold=5,
        ),
        client=pcs_client,
        always_points=pcs_read_points,
        write_points=pcs_write_points,
        alarm_evaluators=[soc_alarms],
    )

    # --- 電表設備 ---
    meter_read_points = [
        ReadPoint(
            name="voltage",
            address=0,
            data_type=f32,
            metadata=PointMetadata(unit="V", description="A 相電壓"),
        ),
        ReadPoint(
            name="active_power",
            address=12,
            data_type=f32,
            metadata=PointMetadata(unit="kW", description="有功功率"),
        ),
        ReadPoint(
            name="frequency",
            address=20,
            data_type=f32,
            metadata=PointMetadata(unit="Hz", description="電網頻率"),
        ),
    ]

    meter_client = PymodbusTcpClient(tcp_config)
    meter_device = AsyncModbusDevice(
        config=DeviceConfig(
            device_id="meter_01",
            unit_id=1,
            read_interval=1.0,
            disconnect_threshold=5,
        ),
        client=meter_client,
        always_points=meter_read_points,
    )

    return pcs_device, meter_device


# ============================================================
# 事件處理器
# ============================================================


async def on_read_complete(payload: ReadCompletePayload) -> None:
    """讀取完成事件 — 印出設備讀取摘要"""
    vals = payload.values
    device_id = payload.device_id
    if device_id == "pcs_01":
        p = vals.get("p_actual", "N/A")
        soc = vals.get("soc", "N/A")
        p_str = f"{p:.1f}" if isinstance(p, float) else str(p)
        soc_str = f"{soc:.1f}" if isinstance(soc, float) else str(soc)
        print(f"  [read] PCS:   P={p_str} kW, SOC={soc_str}%")
    elif device_id == "meter_01":
        p = vals.get("active_power", "N/A")
        v = vals.get("voltage", "N/A")
        p_str = f"{p:.1f}" if isinstance(p, float) else str(p)
        v_str = f"{v:.1f}" if isinstance(v, float) else str(v)
        print(f"  [read] Meter: P={p_str} kW, V={v_str} V")


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    print("=" * 70)
    print("csp_lib Example 19: Custom Database (In-Memory Repositories)")
    print("零外部依賴 — 不需要 MongoDB / Redis 即可運行完整系統")
    print("=" * 70)

    # ── 1. 建立 InMemory Repositories ──
    print("\n[1/7] 建立 In-Memory Repositories（取代 MongoDB）...")

    alarm_repo = InMemoryAlarmRepository()
    command_repo = InMemoryCommandRepository()
    batch_uploader = InMemoryBatchUploader()

    print("  InMemoryAlarmRepository    — 替代 MongoAlarmRepository")
    print("  InMemoryCommandRepository  — 替代 MongoCommandRepository")
    print("  InMemoryBatchUploader      — 替代 MongoBatchUploader")

    # ── 2. 啟動模擬伺服器 ──
    print(f"\n[2/7] 啟動 SimulationServer ({SIM_HOST}:{SIM_PORT})...")
    server, pcs_sim = create_simulation_server()

    async with server:
        print(f"  模擬器: {list(server.simulators.keys())}")
        await asyncio.sleep(0.5)

        # ── 3. 建立設備 ──
        print("\n[3/7] 建立 AsyncModbusDevice（PCS + 電表）...")
        pcs_device, meter_device = create_devices()

        # 註冊事件處理器
        cancel_pcs_rc = pcs_device.on(EVENT_READ_COMPLETE, on_read_complete)
        cancel_meter_rc = meter_device.on(EVENT_READ_COMPLETE, on_read_complete)

        # ── 4. 配置 UnifiedDeviceManager ──
        print("\n[4/7] 配置 UnifiedDeviceManager（全部使用 InMemory 後端）...")
        config = UnifiedConfig(
            alarm_repository=alarm_repo,
            command_repository=command_repo,
            mongo_uploader=batch_uploader,  # InMemoryBatchUploader 替代 MongoBatchUploader
            redis_client=None,
            notification_dispatcher=None,
        )

        manager = UnifiedDeviceManager(config)
        manager.register(pcs_device, collection_name="pcs_data")
        manager.register(meter_device, collection_name="meter_data")

        print(f"  {manager!r}")
        print(f"  alarm_manager  : {'啟用' if manager.alarm_manager is not None else '停用'}")
        print(f"  command_manager: {'啟用' if manager.command_manager is not None else '停用'}")
        print(f"  data_manager   : {'啟用' if manager.data_manager is not None else '停用'}")

        # ── 5. 啟動並運行 ──
        print("\n[5/7] 啟動 UnifiedDeviceManager...")
        async with manager:
            print(f"  Manager 運行中: {manager.is_running}")

            # 等待數次讀取完成，讓 DataUploadManager 收集資料
            await asyncio.sleep(3.0)

            # ── 查詢 InMemoryBatchUploader 中的上傳資料 ──
            print("\n  --- InMemoryBatchUploader 資料檢視 ---")
            pcs_docs = batch_uploader.get_documents("pcs_data")
            meter_docs = batch_uploader.get_documents("meter_data")
            print(f"  pcs_data   文件數: {len(pcs_docs)}")
            print(f"  meter_data 文件數: {len(meter_docs)}")
            if pcs_docs:
                latest = pcs_docs[-1]
                print(f"  最新 PCS 文件: { {k: v for k, v in latest.items() if k != '_id'} }")

            # ── 6. 模擬告警觸發 ──
            print("\n[6/7] 模擬告警觸發...")

            # 階段 A: SOC 升至 95% → 觸發 SOC_HIGH (WARNING)
            print("\n  --- 階段 A: SOC → 95%（觸發 SOC_HIGH WARNING）---")
            pcs_sim.set_value("soc", 95.0)
            await asyncio.sleep(2.0)

            active_alarms = await alarm_repo.get_active_alarms()
            print(f"  進行中告警數: {len(active_alarms)}")
            for alarm in active_alarms:
                print(f"    - {alarm.alarm_key}: {alarm.name} [{alarm.level.name}]")

            # 階段 B: SOC 恢復正常 → 解除告警
            print("\n  --- 階段 B: SOC → 50%（解除告警）---")
            pcs_sim.set_value("soc", 50.0)
            await asyncio.sleep(2.0)

            active_alarms = await alarm_repo.get_active_alarms()
            print(f"  進行中告警數: {len(active_alarms)}")

            # 階段 C: SOC 降至 5% → 觸發 SOC_LOW (ALARM)
            print("\n  --- 階段 C: SOC → 5%（觸發 SOC_LOW ALARM）---")
            pcs_sim.set_value("soc", 5.0)
            await asyncio.sleep(2.0)

            active_alarms = await alarm_repo.get_active_alarms()
            print(f"  進行中告警數: {len(active_alarms)}")
            for alarm in active_alarms:
                print(f"    - {alarm.alarm_key}: {alarm.name} [{alarm.level.name}]")

            # 恢復正常
            pcs_sim.set_value("soc", 50.0)
            await asyncio.sleep(1.0)

            # ── 示範 WriteCommandManager ──
            if manager.command_manager is not None:
                print("\n  --- 示範 WriteCommandManager ---")
                cmd = WriteCommand(device_id="pcs_01", point_name="p_set", value=-25.0)
                print("  發送指令: PCS p_set = -25.0 kW (充電)")
                result = await manager.command_manager.execute(cmd)
                print(f"  結果: status={result.status.value}, point={result.point_name}")

                await asyncio.sleep(1.5)

            # ── 7. 查詢所有 InMemory 儲存的資料 ──
            print("\n[7/7] 查詢所有 InMemory 儲存的資料摘要...")

            # 告警記錄
            all_alarm_records = alarm_repo.get_all_records()
            print(f"\n  告警記錄總數: {len(all_alarm_records)}")
            for key, record in all_alarm_records.items():
                resolved = record.resolved_timestamp.strftime("%H:%M:%S") if record.resolved_timestamp else "仍在進行中"
                print(f"    {key:<40} [{record.level.name:<7}] {record.status.value:<8} resolved={resolved}")

            # 指令記錄
            all_cmd_records = command_repo.get_all_records()
            print(f"\n  指令記錄總數: {len(all_cmd_records)}")
            for _rid, record in all_cmd_records.items():
                print(f"    {record.device_id}.{record.point_name}={record.value} status={record.status.value}")

            # 上傳資料
            all_docs = batch_uploader.get_all_documents()
            print(f"\n  上傳資料 collection 數: {len(all_docs)}")
            for coll_name, docs in all_docs.items():
                print(f"    {coll_name}: {len(docs)} 筆文件")

        # ── 清理 ──
        print("\n  清理中...")
        cancel_pcs_rc()
        cancel_meter_rc()

    print("  SimulationServer 已停止")
    print("\n" + "=" * 70)
    print("範例完成！")
    print("展示了如何使用 InMemory Repository 取代 MongoDB，")
    print("在零外部依賴環境下運行完整的設備管理系統。")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
