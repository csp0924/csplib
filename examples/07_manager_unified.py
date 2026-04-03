"""
csp_lib Example 07: Unified Device Manager

Demonstrates UnifiedDeviceManager with sub-manager integration.

架構：
  SimulationServer (Modbus TCP 模擬器)
       ↕ TCP
  AsyncModbusDevice × 2 (PCS + Meter)
       ↓ events
  UnifiedDeviceManager
    ├── DeviceManager       — 設備讀取生命週期管理
    ├── AlarmPersistenceManager  — 告警持久化（InMemory mock）
    └── WriteCommandManager — 寫入指令管理（InMemory mock）

  本範例使用 InMemory mock 取代 MongoDB/Redis，
  展示 UnifiedDeviceManager 如何整合所有子管理器。

Run: uv run python examples/07_manager_unified.py
"""

import asyncio
from datetime import datetime
from typing import Any

from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.equipment.device.events import EVENT_READ_COMPLETE, EVENT_VALUE_CHANGE, ReadCompletePayload
from csp_lib.manager.alarm.schema import AlarmRecord, AlarmStatus
from csp_lib.manager.command.schema import CommandRecord, CommandStatus, WriteCommand
from csp_lib.manager.unified import UnifiedConfig, UnifiedDeviceManager
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, PowerMeterSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import default_meter_config

# ============================================================
# 常量
# ============================================================

SIM_HOST = "127.0.0.1"
SIM_PORT = 5021  # 避免與其他範例衝突


# ============================================================
# 記憶體模擬儲存庫（InMemory Mock）
# ============================================================


class InMemoryAlarmRepository:
    """
    記憶體版 AlarmRepository（存放於 dict）。

    實作 AlarmRepository Protocol，將告警記錄存放於記憶體 dict。
    用於無 MongoDB 環境下的演示與測試。
    """

    def __init__(self) -> None:
        self._records: dict[str, AlarmRecord] = {}  # alarm_key -> AlarmRecord
        self._id_counter = 0

    async def upsert(self, record: AlarmRecord) -> tuple[str, bool]:
        """新增或更新告警記錄"""
        existing = self._records.get(record.alarm_key)
        if existing and existing.status == AlarmStatus.ACTIVE:
            return record.alarm_key, False

        self._id_counter += 1
        record_id = f"mem_{self._id_counter}"
        self._records[record.alarm_key] = record
        print(f"    [AlarmRepo] NEW alarm: {record.alarm_key} level={record.level.value}")
        return record_id, True

    async def resolve(self, alarm_key: str, resolved_at: datetime) -> bool:
        """解除告警"""
        record = self._records.get(alarm_key)
        if record and record.status == AlarmStatus.ACTIVE:
            # dataclass 非 frozen，可以直接修改
            self._records[alarm_key] = AlarmRecord(
                alarm_key=record.alarm_key,
                device_id=record.device_id,
                alarm_type=record.alarm_type,
                alarm_code=record.alarm_code,
                name=record.name,
                level=record.level,
                description=record.description,
                timestamp=record.timestamp,
                resolved_timestamp=resolved_at,
                status=AlarmStatus.RESOLVED,
            )
            print(f"    [AlarmRepo] RESOLVED alarm: {alarm_key}")
            return True
        return False

    async def get_active_alarms(self) -> list[AlarmRecord]:
        """取得所有進行中的告警"""
        return [r for r in self._records.values() if r.status == AlarmStatus.ACTIVE]

    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]:
        """取得指定設備的進行中告警"""
        return [r for r in self._records.values() if r.device_id == device_id and r.status == AlarmStatus.ACTIVE]


class InMemoryCommandRepository:
    """
    記憶體版 CommandRepository（存放於 dict）。

    實作 CommandRepository Protocol，將指令記錄存放於記憶體 dict。
    """

    def __init__(self) -> None:
        self._records: dict[str, CommandRecord] = {}

    async def create(self, record: CommandRecord) -> str:
        """建立指令記錄"""
        self._records[record.command_id] = record
        print(f"    [CmdRepo] CREATE command: {record.command_id[:8]}... -> {record.device_id}.{record.point_name}")
        return record.command_id

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """更新指令狀態"""
        record = self._records.get(command_id)
        if record:
            # 更新狀態（CommandRecord 非 frozen）
            record.status = status
            if result is not None:
                record.result = result
            if error_message is not None:
                record.error_message = error_message
            print(f"    [CmdRepo] UPDATE command: {command_id[:8]}... -> status={status.value}")
            return True
        return False

    async def get(self, command_id: str) -> CommandRecord | None:
        """取得指令記錄"""
        return self._records.get(command_id)

    async def list_by_device(self, device_id: str, limit: int = 100) -> list[CommandRecord]:
        """取得設備的指令記錄"""
        records = [r for r in self._records.values() if r.device_id == device_id]
        return sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]


# ============================================================
# SimulationServer 建立
# ============================================================


def create_simulation_server() -> SimulationServer:
    """建立包含 PCS 和電表的模擬伺服器"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    # PCS 模擬器 — unit_id=10, 初始 SOC=70%
    pcs_config = default_pcs_config(device_id="pcs_01", unit_id=10)
    pcs_sim = PCSSimulator(config=pcs_config, capacity_kwh=200.0, p_ramp_rate=50.0)
    pcs_sim.set_value("soc", 70.0)
    pcs_sim.set_value("operating_mode", 1)
    pcs_sim._running = True

    # 電表模擬器 — unit_id=1
    meter_config = default_meter_config(device_id="meter_01", unit_id=1)
    meter_sim = PowerMeterSimulator(config=meter_config, voltage_noise=1.5, frequency_noise=0.01)
    meter_sim.set_system_reading(v=380.0, f=60.0, p=20.0, q=5.0)

    server.add_simulator(pcs_sim)
    server.add_simulator(meter_sim)

    return server


# ============================================================
# AsyncModbusDevice 建立
# ============================================================


def create_devices() -> tuple[AsyncModbusDevice, AsyncModbusDevice]:
    """建立 PCS 和電表的 AsyncModbusDevice"""
    tcp_config = ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT, timeout=2.0)
    f32 = Float32()
    u16 = UInt16()

    # --- PCS 設備 ---
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
# 事件處理器（用於 console 輸出）
# ============================================================


async def on_value_change(payload) -> None:
    """設備值變更事件 — 只印出關鍵點位"""
    if payload.point_name in ("p_actual", "soc", "active_power"):
        old = f"{payload.old_value:.2f}" if isinstance(payload.old_value, float) else str(payload.old_value)
        new = f"{payload.new_value:.2f}" if isinstance(payload.new_value, float) else str(payload.new_value)
        print(f"  [value_change] {payload.device_id}.{payload.point_name}: {old} -> {new}")


async def on_read_complete(payload: ReadCompletePayload) -> None:
    """讀取完成事件 — 印出設備讀取摘要"""
    vals = payload.values
    device_id = payload.device_id
    if device_id == "pcs_01":
        p = vals.get("p_actual", "N/A")
        soc = vals.get("soc", "N/A")
        p_str = f"{p:.1f}" if isinstance(p, float) else str(p)
        soc_str = f"{soc:.1f}" if isinstance(soc, float) else str(soc)
        print(f"  [read_complete] PCS:   P_actual={p_str} kW, SOC={soc_str}%")
    elif device_id == "meter_01":
        p = vals.get("active_power", "N/A")
        v = vals.get("voltage", "N/A")
        p_str = f"{p:.1f}" if isinstance(p, float) else str(p)
        v_str = f"{v:.1f}" if isinstance(v, float) else str(v)
        print(f"  [read_complete] Meter: P={p_str} kW, V={v_str} V")


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    print("=" * 65)
    print("csp_lib Example 07: Unified Device Manager")
    print("UnifiedDeviceManager + AlarmPersistence + WriteCommand")
    print("=" * 65)

    # --- 1. 建立 mock repositories ---
    print("\n[1/6] Creating in-memory repositories (no MongoDB/Redis needed)...")
    alarm_repo = InMemoryAlarmRepository()
    command_repo = InMemoryCommandRepository()
    print("  InMemoryAlarmRepository  -> ready")
    print("  InMemoryCommandRepository -> ready")

    # --- 2. 啟動模擬伺服器 ---
    print(f"\n[2/6] Starting SimulationServer on {SIM_HOST}:{SIM_PORT}...")
    server = create_simulation_server()

    async with server:
        print(f"  Simulators: {list(server.simulators.keys())}")
        await asyncio.sleep(0.5)

        # --- 3. 建立設備 ---
        print("\n[3/6] Creating AsyncModbusDevice (PCS + Meter)...")
        pcs_device, meter_device = create_devices()

        # 註冊 console 事件（用於觀察值變化）
        cancel_pcs_vc = pcs_device.on(EVENT_VALUE_CHANGE, on_value_change)
        cancel_meter_vc = meter_device.on(EVENT_VALUE_CHANGE, on_value_change)
        cancel_pcs_rc = pcs_device.on(EVENT_READ_COMPLETE, on_read_complete)
        cancel_meter_rc = meter_device.on(EVENT_READ_COMPLETE, on_read_complete)

        # --- 4. 配置 UnifiedDeviceManager ---
        print("\n[4/6] Configuring UnifiedDeviceManager...")
        config = UnifiedConfig(
            alarm_repository=alarm_repo,
            command_repository=command_repo,
            # 不需要 MongoDB/Redis:
            mongo_uploader=None,
            redis_client=None,
            notification_dispatcher=None,
            statistics_config=None,
            device_registry=None,
        )

        manager = UnifiedDeviceManager(config)

        # 註冊設備
        manager.register(pcs_device, collection_name="pcs_data")
        manager.register(meter_device, collection_name="meter_data")

        print(f"  {manager!r}")
        print(f"  alarm_manager  enabled: {manager.alarm_manager is not None}")
        print(f"  command_manager enabled: {manager.command_manager is not None}")
        print(f"  data_manager   enabled: {manager.data_manager is not None}")
        print(f"  state_manager  enabled: {manager.state_manager is not None}")
        print(f"  stats_manager  enabled: {manager.statistics_manager is not None}")

        # --- 5. 啟動並運行 ---
        print("\n[5/6] Starting UnifiedDeviceManager (running for ~8 seconds)...")
        async with manager:
            print(f"  Manager running: {manager.is_running}")

            # 等待第一次讀取完成
            await asyncio.sleep(2.0)

            print(f"\n  PCS  latest_values: {pcs_device.latest_values}")
            print(f"  Meter latest_values: {meter_device.latest_values}")

            # 檢查告警狀態
            active_alarms = await alarm_repo.get_active_alarms()
            print(f"\n  Active alarms: {len(active_alarms)}")

            # --- 示範：透過 WriteCommandManager 發送寫入指令 ---
            print("\n  --- Demonstrating WriteCommandManager ---")

            if manager.command_manager is not None:
                # 指令 1: 設定 PCS 有功功率 -30kW（充電）
                cmd1 = WriteCommand(
                    device_id="pcs_01",
                    point_name="p_set",
                    value=-30.0,
                )
                print("\n  Sending command: PCS p_set = -30.0 kW (charging)")
                result1 = await manager.command_manager.execute(cmd1)
                print(f"  Result: status={result1.status.value}, point={result1.point_name}, value={result1.value}")

                # 等待 PCS 功率追蹤 setpoint
                await asyncio.sleep(2.0)
                print(f"\n  PCS values after charge cmd: {pcs_device.latest_values}")

                # 指令 2: 設定 PCS 無功功率 10kVar
                cmd2 = WriteCommand(
                    device_id="pcs_01",
                    point_name="q_set",
                    value=10.0,
                )
                print("\n  Sending command: PCS q_set = 10.0 kVar")
                result2 = await manager.command_manager.execute(cmd2)
                print(f"  Result: status={result2.status.value}, point={result2.point_name}, value={result2.value}")

                await asyncio.sleep(2.0)

                # 指令 3: 嘗試寫入不存在的設備
                cmd3 = WriteCommand(
                    device_id="unknown_device",
                    point_name="p_set",
                    value=50.0,
                )
                print("\n  Sending command to unknown device...")
                result3 = await manager.command_manager.execute(cmd3)
                error_msg = result3.error_message or ""
                print(f"  Result: status={result3.status.value}, error={error_msg.encode('ascii', 'replace').decode()}")

                # 查詢指令歷史
                pcs_commands = await command_repo.list_by_device("pcs_01")
                print(f"\n  Command history for pcs_01: {len(pcs_commands)} records")
                for rec in pcs_commands:
                    print(f"    - {rec.point_name}={rec.value} status={rec.status.value}")

            # 繼續讀取幾個週期
            await asyncio.sleep(2.0)

            # 最終狀態
            print("\n  --- Final Status ---")
            print(f"  PCS  latest_values: {pcs_device.latest_values}")
            print(f"  Meter latest_values: {meter_device.latest_values}")

            active_alarms = await alarm_repo.get_active_alarms()
            print(f"  Active alarms: {len(active_alarms)}")
            for alarm in active_alarms:
                print(f"    - {alarm.alarm_key}: {alarm.name} ({alarm.level.value})")

        # --- 6. 清理 ---
        print("\n[6/6] Cleanup...")
        cancel_pcs_vc()
        cancel_meter_vc()
        cancel_pcs_rc()
        cancel_meter_rc()
        print("  Event handlers cancelled.")

    print("  SimulationServer stopped.")
    print("\n" + "=" * 65)
    print("Demo complete!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
