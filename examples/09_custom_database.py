"""
csp_lib Example 09: 自定義資料庫 — BatchUploader Protocol + CSV 後端

學習目標：
  - BatchUploader Protocol — 批次上傳器介面定義
  - 自定義 CSVBatchUploader — 將設備資料寫入 CSV 檔案
  - InMemoryAlarmRepository — 記憶體內告警持久化
  - UnifiedConfig + UnifiedDeviceManager — 統一管理器整合
  - 自定義後端無需修改業務邏輯

架構：
  SimulationServer (PCS + 電表)
       ↕ TCP
  AsyncModbusDevice × 2
       ↓ events
  UnifiedDeviceManager
    ├── DeviceManager           — 設備讀取生命週期管理
    ├── AlarmPersistenceManager — 告警持久化（InMemoryAlarmRepository）
    └── DataUploadManager       — 資料上傳（CSVBatchUploader 自定義後端）

  重點：CSVBatchUploader 實作 BatchUploader Protocol，
  無需修改 DataUploadManager 或 UnifiedDeviceManager 的任何程式碼。

Run: uv run python examples/09_custom_database.py
"""

import asyncio
import csv
import io
import os
import sys
import tempfile
import threading
from collections import defaultdict
from typing import Any

# Windows 終端 UTF-8 支援
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from csp_lib.equipment.alarm import (
    AlarmDefinition,
    AlarmLevel,
    Operator,
    ThresholdAlarmEvaluator,
    ThresholdCondition,
)
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.manager import (
    InMemoryAlarmRepository,
    UnifiedConfig,
    UnifiedDeviceManager,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, PowerMeterSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import default_meter_config

# ============================================================
# 常量
# ============================================================

SIM_HOST = "127.0.0.1"
SIM_PORT = 5090  # 避免與其他範例衝突


# ============================================================
# Section 1: 自定義 CSVBatchUploader
# ============================================================


class CSVBatchUploader:
    """
    CSV 檔案批次上傳器

    實作 BatchUploader Protocol，將資料以 CSV 格式寫入檔案。
    每個 collection 對應一個 CSV 檔案。

    這個實作展示了 BatchUploader Protocol 的靈活性：
    只要實作 register_collection() 和 enqueue() 兩個方法，
    就可以將設備資料導向任何儲存後端。

    Attributes:
        _output_dir: CSV 檔案輸出目錄
        _writers: collection_name → csv.DictWriter 的映射
        _files: collection_name → 開啟的檔案物件
        _lock: 執行緒安全鎖
    """

    def __init__(self, output_dir: str) -> None:
        self._output_dir = output_dir
        self._lock = threading.Lock()
        self._files: dict[str, io.TextIOWrapper] = {}
        self._writers: dict[str, csv.DictWriter] = {}
        self._row_counts: dict[str, int] = defaultdict(int)
        os.makedirs(output_dir, exist_ok=True)

    def register_collection(self, collection_name: str) -> None:
        """
        註冊 collection — 建立對應的 CSV 檔案

        Args:
            collection_name: Collection 名稱（對應 CSV 檔名）
        """
        # CSV writer 在第一次 enqueue 時才建立（因為需要知道欄位名稱）
        with self._lock:
            if collection_name not in self._row_counts:
                self._row_counts[collection_name] = 0
                print(f"  [CSV] 已註冊 collection: {collection_name}")

    async def enqueue(self, collection_name: str, document: dict[str, Any]) -> None:
        """
        將文件寫入 CSV 檔案

        首次寫入時依據 document 的 key 自動建立 CSV header。

        Args:
            collection_name: 目標 collection 名稱
            document: 要寫入的資料
        """
        with self._lock:
            if collection_name not in self._writers:
                # 第一次寫入，建立 CSV writer
                filepath = os.path.join(self._output_dir, f"{collection_name}.csv")
                f = open(filepath, "w", newline="", encoding="utf-8")
                # 扁平化 nested dict 的 key
                flat_doc = self._flatten(document)
                writer = csv.DictWriter(f, fieldnames=list(flat_doc.keys()))
                writer.writeheader()
                self._files[collection_name] = f
                self._writers[collection_name] = writer

            writer = self._writers[collection_name]
            flat_doc = self._flatten(document)
            try:
                writer.writerow(flat_doc)
                self._files[collection_name].flush()
                self._row_counts[collection_name] += 1
            except ValueError:
                # 新欄位出現時忽略（簡化處理）
                pass

    def close(self) -> None:
        """關閉所有檔案"""
        with self._lock:
            for f in self._files.values():
                f.close()
            self._files.clear()
            self._writers.clear()

    def get_row_count(self, collection_name: str) -> int:
        """取得指定 collection 的已寫入行數"""
        with self._lock:
            return self._row_counts.get(collection_name, 0)

    @staticmethod
    def _flatten(d: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
        """將巢狀 dict 扁平化"""
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(CSVBatchUploader._flatten(v, new_key, sep).items())
            else:
                items.append((new_key, v))
        return dict(items)


# ============================================================
# Section 2: SimulationServer 建立
# ============================================================


def create_simulation_server() -> tuple[SimulationServer, PCSSimulator]:
    """建立模擬伺服器"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    pcs_config = default_pcs_config("pcs_01", unit_id=10)
    pcs_sim = PCSSimulator(config=pcs_config, capacity_kwh=200.0, p_ramp_rate=100.0)
    pcs_sim.set_value("soc", 50.0)
    pcs_sim.set_value("operating_mode", 1)
    pcs_sim._running = True

    meter_config = default_meter_config("meter_01", unit_id=1)
    meter_sim = PowerMeterSimulator(config=meter_config)
    meter_sim.set_system_reading(v=380.0, f=60.0, p=20.0, q=5.0)

    server.add_simulator(pcs_sim)
    server.add_simulator(meter_sim)
    return server, pcs_sim


# ============================================================
# Section 3: AsyncModbusDevice 建立
# ============================================================


def create_devices() -> tuple[AsyncModbusDevice, AsyncModbusDevice]:
    """建立 PCS（含 SOC 告警）和電表的 AsyncModbusDevice"""
    tcp_config = ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT, timeout=2.0)
    f32 = Float32()
    u16 = UInt16()

    # --- PCS 設備（含 SOC 門檻告警）---
    soc_alarm_evaluator = ThresholdAlarmEvaluator(
        point_name="soc",
        conditions=[
            ThresholdCondition(
                alarm=AlarmDefinition(
                    code="SOC_LOW",
                    name="SOC 過低",
                    level=AlarmLevel.WARNING,
                    description="SOC 低於 15%",
                ),
                operator=Operator.LT,
                value=15.0,
            ),
        ],
    )
    pcs_read_points = [
        ReadPoint(name="p_actual", address=4, data_type=f32, metadata=PointMetadata(unit="kW")),
        ReadPoint(name="q_actual", address=6, data_type=f32, metadata=PointMetadata(unit="kVar")),
        ReadPoint(name="soc", address=8, data_type=f32, metadata=PointMetadata(unit="%")),
        ReadPoint(name="operating_mode", address=10, data_type=u16),
    ]
    pcs_write_points = [
        WritePoint(name="p_setpoint", address=0, data_type=f32, metadata=PointMetadata(unit="kW")),
    ]
    pcs_client = PymodbusTcpClient(tcp_config)
    pcs_device = AsyncModbusDevice(
        config=DeviceConfig(device_id="pcs_01", unit_id=10, read_interval=0.5),
        client=pcs_client,
        always_points=pcs_read_points,
        write_points=pcs_write_points,
        alarm_evaluators=[soc_alarm_evaluator],
    )

    # --- 電表設備 ---
    meter_read_points = [
        ReadPoint(name="active_power", address=12, data_type=f32, metadata=PointMetadata(unit="kW")),
        ReadPoint(name="reactive_power", address=14, data_type=f32, metadata=PointMetadata(unit="kVar")),
        ReadPoint(name="frequency", address=20, data_type=f32, metadata=PointMetadata(unit="Hz")),
    ]
    meter_client = PymodbusTcpClient(tcp_config)
    meter_device = AsyncModbusDevice(
        config=DeviceConfig(device_id="meter_01", unit_id=1, read_interval=0.5),
        client=meter_client,
        always_points=meter_read_points,
    )

    return pcs_device, meter_device


# ============================================================
# Section 4: 完整展示
# ============================================================


async def main():
    print()
    print("csp_lib Example 09: 自定義資料庫 — CSV 後端 + InMemory 告警")
    print("==========================================================")

    # --- 展示 BatchUploader Protocol 的方法 ---
    print("\n" + "=" * 70)
    print("Section A: BatchUploader Protocol 介面")
    print("=" * 70)
    print("""
  BatchUploader Protocol 定義兩個方法：

  1. register_collection(collection_name: str) -> None
     註冊 collection 名稱（如 MongoDB collection 或 CSV 檔案名稱）

  2. async enqueue(collection_name: str, document: dict) -> None
     將文件加入上傳佇列（非同步，適用於 I/O 密集操作）

  任何實作這兩個方法的類別都可以作為 BatchUploader 使用，
  無需修改 DataUploadManager 或 UnifiedDeviceManager 的程式碼。
    """)

    # --- 建立 CSV 上傳器 ---
    csv_dir = os.path.join(tempfile.gettempdir(), "csp_lib_csv_demo")
    csv_uploader = CSVBatchUploader(csv_dir)
    print(f"  CSV 輸出目錄: {csv_dir}")

    # --- 建立 InMemory 告警 Repository ---
    alarm_repo = InMemoryAlarmRepository()
    print("  告警 Repository: InMemoryAlarmRepository (記憶體內)")

    # --- 建立統一管理器配置 ---
    unified_config = UnifiedConfig(
        alarm_repository=alarm_repo,
        mongo_uploader=csv_uploader,  # BatchUploader Protocol — 可以傳入任何實作
    )
    print("  UnifiedConfig: alarm_repository + csv_uploader (作為 batch_uploader)")

    # --- 啟動 SimulationServer ---
    print("\n" + "=" * 70)
    print("Section B: 完整系統運行")
    print("=" * 70)

    server, pcs_sim = create_simulation_server()
    pcs_device, meter_device = create_devices()

    async with server:
        print("\n[1] SimulationServer 啟動完成")
        await asyncio.sleep(0.5)

        async with pcs_device, meter_device:
            print("[2] PCS 和電表設備已連線")
            await asyncio.sleep(1.0)

            # --- 建立並啟動 UnifiedDeviceManager ---
            manager = UnifiedDeviceManager(unified_config)
            manager.register(pcs_device, collection_name="pcs_data")
            manager.register(meter_device, collection_name="meter_data")
            print("[3] UnifiedDeviceManager 已註冊設備\n")

            async with manager:
                print("--- 階段 1: 正常運行（收集 5 秒資料）---")
                await asyncio.sleep(5)

                pcs_rows = csv_uploader.get_row_count("pcs_data")
                meter_rows = csv_uploader.get_row_count("meter_data")
                print(f"  PCS 資料已寫入 CSV: {pcs_rows} 行")
                print(f"  電表資料已寫入 CSV: {meter_rows} 行")

                # 查看告警狀態
                active_alarms = await alarm_repo.get_active_alarms()
                print(f"  當前活躍告警數: {len(active_alarms)}")

                # --- 階段 2: 降低 SOC 觸發告警 ---
                print("\n--- 階段 2: 降低 SOC 至 10%（觸發 SOC_LOW 告警）---")
                pcs_sim.set_value("soc", 10.0)
                await asyncio.sleep(3)

                active_alarms = await alarm_repo.get_active_alarms()
                print(f"  當前活躍告警數: {len(active_alarms)}")
                for alarm in active_alarms:
                    print(f"    告警: {alarm.alarm_key}, 等級={alarm.level.value}, 狀態={alarm.status.value}")

                # --- 階段 3: 恢復 SOC，告警自動解除 ---
                print("\n--- 階段 3: 恢復 SOC 至 50%（告警自動解除）---")
                pcs_sim.set_value("soc", 50.0)
                await asyncio.sleep(3)

                active_alarms = await alarm_repo.get_active_alarms()
                print(f"  當前活躍告警數: {len(active_alarms)}")

                # --- 查看所有告警記錄 ---
                all_records = alarm_repo.get_all_records()
                print(f"\n  告警記錄總數: {len(all_records)}")
                for key, record in all_records.items():
                    resolved_str = "已解除" if record.resolved_timestamp else "進行中"
                    print(f"    {key}: {resolved_str}")

                # 繼續收集資料
                print("\n--- 階段 4: 繼續收集資料（3 秒）---")
                await asyncio.sleep(3)

                pcs_rows = csv_uploader.get_row_count("pcs_data")
                meter_rows = csv_uploader.get_row_count("meter_data")
                print(f"  PCS 資料 CSV 總行數: {pcs_rows}")
                print(f"  電表資料 CSV 總行數: {meter_rows}")

            print("\n[4] UnifiedDeviceManager 已停止")
        print("[5] 設備已斷線")

    # 關閉 CSV 檔案
    csv_uploader.close()
    print("[6] SimulationServer 已關閉")

    # --- 最終報告 ---
    print("\n" + "=" * 70)
    print("Section C: 最終報告")
    print("=" * 70)

    # 列出生成的 CSV 檔案
    print(f"\n  CSV 檔案目錄: {csv_dir}")
    for fname in os.listdir(csv_dir):
        fpath = os.path.join(csv_dir, fname)
        fsize = os.path.getsize(fpath)
        print(f"    {fname}: {fsize} bytes")

    # 讀取 CSV 檔案前幾行
    for collection in ["pcs_data", "meter_data"]:
        fpath = os.path.join(csv_dir, f"{collection}.csv")
        if os.path.exists(fpath):
            print(f"\n  --- {collection}.csv 前 3 行 ---")
            with open(fpath, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i >= 4:  # header + 3 資料行
                        break
                    if i == 0:
                        print(f"    Header: {', '.join(row[:5])}...")
                    else:
                        print(f"    Row {i}: {', '.join(str(v)[:10] for v in row[:5])}...")

    # 告警記錄
    all_records = alarm_repo.get_all_records()
    print(f"\n  InMemory 告警記錄總數: {len(all_records)}")

    print("\n" + "=" * 70)
    print("範例完成！")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
