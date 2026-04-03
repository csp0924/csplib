"""
csp_lib Example 08: 告警管理與通知

展示完整的告警生命週期，包含持久化與通知功能：
  1. SimulationServer 提供一個帶有 SOC 暫存器的 PCS 模擬設備
  2. AsyncModbusDevice 讀取 SOC 並評估門檻告警
  3. AlarmPersistenceManager 透過記憶體儲存庫持久化告警記錄
  4. NotificationDispatcher 將通知分發到終端通道
  5. 模擬操作 SOC 以觸發和解除告警

告警生命週期：
  觸發 -> 持久化 -> 通知 -> 解除 -> 持久化 -> 通知

Run: uv run python examples/08_alarm_notification.py
"""

import asyncio
from datetime import datetime

from csp_lib.equipment.alarm import (
    AlarmDefinition,
    AlarmLevel,
    Operator,
    ThresholdAlarmEvaluator,
    ThresholdCondition,
)
from csp_lib.equipment.core import ReadPoint
from csp_lib.equipment.core.point import PointMetadata
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.manager.alarm import (
    AlarmPersistenceManager,
    AlarmRecord,
    AlarmStatus,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import (
    PCSSimulator,
    ServerConfig,
    SimulationServer,
)
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.notification import (
    Notification,
    NotificationChannel,
    NotificationDispatcher,
)

# ============================================================
# 常量
# ============================================================

SIM_HOST = "127.0.0.1"
SIM_PORT = 5021  # 使用不同 port 避免與 demo_full_system 衝突


# ============================================================
# 記憶體告警儲存庫（mock — 不需要 MongoDB）
# ============================================================


class InMemoryAlarmRepository:
    """
    記憶體版 AlarmRepository 實作，用於演示。

    以 alarm_key 為鍵將告警記錄存放於 dict 中。
    滿足 AlarmRepository Protocol。
    """

    def __init__(self) -> None:
        self._records: dict[str, AlarmRecord] = {}
        self._counter: int = 0

    async def upsert(self, record: AlarmRecord) -> tuple[str, bool]:
        """若同 key 無進行中告警則新增，否則跳過。"""
        existing = self._records.get(record.alarm_key)
        if existing and existing.status == AlarmStatus.ACTIVE:
            return record.alarm_key, False

        self._counter += 1
        self._records[record.alarm_key] = record
        print(f"  [REPOSITORY] Stored alarm: {record.alarm_key} (level={record.level.name})")
        return record.alarm_key, True

    async def resolve(self, alarm_key: str, resolved_at: datetime) -> bool:
        """將進行中的告警標記為已解除。"""
        existing = self._records.get(alarm_key)
        if existing and existing.status == AlarmStatus.ACTIVE:
            # 直接修改（AlarmRecord 為非 frozen dataclass）
            existing.status = AlarmStatus.RESOLVED
            existing.resolved_timestamp = resolved_at
            print(f"  [REPOSITORY] Resolved alarm: {alarm_key}")
            return True
        return False

    async def get_active_alarms(self) -> list[AlarmRecord]:
        """取得所有進行中的告警。"""
        return [r for r in self._records.values() if r.status == AlarmStatus.ACTIVE]

    async def get_active_by_device(self, device_id: str) -> list[AlarmRecord]:
        """取得指定設備的進行中告警。"""
        return [r for r in self._records.values() if r.device_id == device_id and r.status == AlarmStatus.ACTIVE]

    def dump_all(self) -> list[AlarmRecord]:
        """取得所有記錄（供演示檢視）。"""
        return list(self._records.values())


# ============================================================
# 終端通知通道
# ============================================================


class ConsoleNotificationChannel(NotificationChannel):
    """將通知印出到終端，用於演示。"""

    @property
    def name(self) -> str:
        return "console"

    async def send(self, notification: Notification) -> None:
        level_icon = {
            AlarmLevel.INFO: "INFO",
            AlarmLevel.WARNING: "WARN",
            AlarmLevel.ALARM: "ALARM",
        }
        icon = level_icon.get(notification.level, "???")
        print(f"  [NOTIFICATION] [{icon}] {notification.title}")
        print(f"                 Body: {notification.body}")
        print(f"                 Event: {notification.event.value} | Device: {notification.device_id}")


# ============================================================
# 模擬伺服器建立
# ============================================================


def create_simulation_server() -> tuple[SimulationServer, PCSSimulator]:
    """建立帶有可控 SOC 的 PCS 模擬伺服器。"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    # PCS 模擬器 — unit_id=10, 初始 SOC=50%（正常範圍）
    pcs_config = default_pcs_config(device_id="pcs_01", unit_id=10)
    pcs_sim = PCSSimulator(config=pcs_config, capacity_kwh=200.0, p_ramp_rate=50.0)
    pcs_sim.set_value("soc", 50.0)
    pcs_sim.set_value("operating_mode", 1)
    pcs_sim._running = True

    server.add_simulator(pcs_sim)
    return server, pcs_sim


# ============================================================
# 設備建立 — 包含 SOC 門檻告警評估器
# ============================================================


def create_pcs_device() -> AsyncModbusDevice:
    """
    建立帶有門檻告警的 PCS AsyncModbusDevice：
      - SOC_HIGH:  SOC > 90%  (WARNING 警告)
      - SOC_LOW:   SOC < 10%  (ALARM 告警)
    """
    tcp_config = ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT, timeout=2.0)
    f32 = Float32()
    u16 = UInt16()

    read_points = [
        ReadPoint(
            name="soc",
            address=8,
            data_type=f32,
            metadata=PointMetadata(unit="%", description="電池 SOC"),
        ),
        ReadPoint(
            name="p_actual",
            address=4,
            data_type=f32,
            metadata=PointMetadata(unit="kW", description="實際有功功率"),
        ),
        ReadPoint(
            name="operating_mode",
            address=10,
            data_type=u16,
            metadata=PointMetadata(description="運行模式"),
        ),
    ]

    # SOC 門檻告警評估器
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

    client = PymodbusTcpClient(tcp_config)
    device = AsyncModbusDevice(
        config=DeviceConfig(
            device_id="pcs_01",
            unit_id=10,
            read_interval=1.0,
            disconnect_threshold=5,
        ),
        client=client,
        always_points=read_points,
        alarm_evaluators=[soc_alarms],
    )
    return device


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    print("=" * 70)
    print("csp_lib Example 08: Alarm Management & Notification")
    print("Demonstrates: threshold alarm -> persist -> notify -> clear -> notify")
    print("=" * 70)

    # --- 1. 啟動模擬伺服器 ---
    print("\n[1/6] Starting SimulationServer...")
    server, pcs_sim = create_simulation_server()

    async with server:
        print(f"  SimulationServer running on {SIM_HOST}:{SIM_PORT}")
        await asyncio.sleep(0.5)

        # --- 2. 建立通知基礎設施 ---
        print("\n[2/6] Setting up notification channel...")
        console_channel = ConsoleNotificationChannel()
        dispatcher = NotificationDispatcher([console_channel])
        print("  ConsoleNotificationChannel registered with NotificationDispatcher")

        # --- 3. 建立告警持久化管理器 ---
        print("\n[3/6] Creating AlarmPersistenceManager with in-memory repository...")
        repository = InMemoryAlarmRepository()
        alarm_manager = AlarmPersistenceManager(
            repository=repository,
            dispatcher=dispatcher,
        )
        print("  AlarmPersistenceManager ready (repository + dispatcher wired)")

        # --- 4. 連接設備並訂閱 ---
        print("\n[4/6] Connecting PCS device with SOC threshold alarms...")
        device = create_pcs_device()

        async with device:
            # 將設備訂閱到告警持久化管理器
            alarm_manager.subscribe(device)
            print(f"  PCS device subscribed (connected={device.is_connected})")
            print("  Alarm thresholds: SOC > 90% (WARNING), SOC < 10% (ALARM)")

            # 等待第一次讀取完成
            await asyncio.sleep(1.5)
            print(f"  Initial SOC reading: {device.latest_values.get('soc', 'N/A')}")

            # --- 5. 操作 SOC 以觸發/解除告警 ---
            print("\n[5/6] Manipulating simulation to trigger/clear alarms...\n")

            # 階段 A: 正常運行 (SOC = 50%)
            print("--- Phase A: Normal operation (SOC=50%) ---")
            await asyncio.sleep(2.0)
            soc_val = device.latest_values.get("soc", "N/A")
            print(f"  SOC = {soc_val} -> No alarms expected")
            active = await repository.get_active_alarms()
            print(f"  Active alarms in repository: {len(active)}\n")

            # 階段 B: SOC 升至 90% 以上 -> 觸發 SOC_HIGH
            print("--- Phase B: SOC rises to 95% (trigger SOC_HIGH WARNING) ---")
            pcs_sim.set_value("soc", 95.0)
            # 等待設備讀取新值並評估告警
            await asyncio.sleep(2.0)
            soc_val = device.latest_values.get("soc", "N/A")
            print(f"  SOC = {soc_val}")
            active = await repository.get_active_alarms()
            print(f"  Active alarms in repository: {len(active)}")
            for alarm in active:
                print(f"    - {alarm.alarm_key} [{alarm.level.name}] {alarm.name}\n")

            # 階段 C: SOC 恢復正常 -> 解除 SOC_HIGH
            print("--- Phase C: SOC returns to 50% (clear SOC_HIGH) ---")
            pcs_sim.set_value("soc", 50.0)
            await asyncio.sleep(2.0)
            soc_val = device.latest_values.get("soc", "N/A")
            print(f"  SOC = {soc_val}")
            active = await repository.get_active_alarms()
            print(f"  Active alarms in repository: {len(active)}\n")

            # 階段 D: SOC 降至 10% 以下 -> 觸發 SOC_LOW
            print("--- Phase D: SOC drops to 5% (trigger SOC_LOW ALARM) ---")
            pcs_sim.set_value("soc", 5.0)
            await asyncio.sleep(2.0)
            soc_val = device.latest_values.get("soc", "N/A")
            print(f"  SOC = {soc_val}")
            active = await repository.get_active_alarms()
            print(f"  Active alarms in repository: {len(active)}")
            for alarm in active:
                print(f"    - {alarm.alarm_key} [{alarm.level.name}] {alarm.name}\n")

            # 階段 E: SOC 恢復 -> 解除 SOC_LOW
            print("--- Phase E: SOC recovers to 40% (clear SOC_LOW) ---")
            pcs_sim.set_value("soc", 40.0)
            await asyncio.sleep(2.0)
            soc_val = device.latest_values.get("soc", "N/A")
            print(f"  SOC = {soc_val}")
            active = await repository.get_active_alarms()
            print(f"  Active alarms in repository: {len(active)}\n")

            # --- 6. 摘要 ---
            print("\n[6/6] Alarm History Summary")
            print("-" * 70)
            all_records = repository.dump_all()
            for record in all_records:
                occurred = record.timestamp.strftime("%H:%M:%S") if record.timestamp else "N/A"
                resolved = (
                    record.resolved_timestamp.strftime("%H:%M:%S") if record.resolved_timestamp else "still active"
                )
                print(
                    f"  {record.alarm_key:<40} "
                    f"[{record.level.name:<7}] "
                    f"{record.status.value:<8} "
                    f"occurred={occurred} resolved={resolved}"
                )
            print("-" * 70)

            # 設備清理前取消訂閱
            alarm_manager.unsubscribe(device)
            print("\n  AlarmPersistenceManager unsubscribed from PCS device.")

        print("  PCS device disconnected.")
    print("  SimulationServer stopped.")

    print("\n" + "=" * 70)
    print("Demo complete! The alarm lifecycle was demonstrated:")
    print("  trigger -> persist (repository) -> notify (console)")
    print("  clear   -> persist (repository) -> notify (console)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
