"""
Example 17: Multi-UnitID Device — 單一設備對應多個 Modbus slave

學習目標：
  - Point-level `unit_id` 覆寫 DeviceConfig.unit_id
  - PointGrouper 依 (function_code, unit_id) 自動分桶
  - AsyncModbusDevice.used_unit_ids 快速查詢觸及的 slave 集合

使用時機：
  某些工業設備會把不同功能暴露在「相同 TCP endpoint、不同 Modbus unit_id」上
  （例如整合型電力轉換裝置、多回路電錶、共用匯流排的多伺服器）。此時把多台
  slave 抽象成同一個 `AsyncModbusDevice` 比拆成多個 device 更貼近物理現實：
    - 共用生命週期（一次 connect / disconnect）
    - 共用事件流（value_change / alarm_triggered）
    - 共用告警評估 context

本範例為純配置展示，不需要真實硬體或模擬伺服器。
展示 `used_unit_ids` property 與 PointGrouper 分桶結果，讓使用者立刻看見
「一個 device 如何觸及多個 slave」的靜態資訊。

Run:
  uv run python examples/17_multi_unit_device.py
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.equipment.transport import PointGrouper
from csp_lib.modbus import Float32, UInt16

# ============================================================
# 點位定義：同一個 device 對應三個 unit_id
# ============================================================
# DeviceConfig.unit_id=1 作為 fallback default。
# 具體點位 unit_id 可覆寫：unit_id=None 沿用 default，明確指定則覆寫。

READ_POINTS = [
    # 主控模組（使用 device default unit_id=1）
    ReadPoint(name="system_status", address=0, data_type=UInt16()),
    ReadPoint(name="alarm_flags", address=2, data_type=UInt16()),
    # 量測模組 (unit_id=2)
    ReadPoint(name="module2_voltage", address=100, data_type=Float32(), unit_id=2),
    ReadPoint(name="module2_current", address=102, data_type=Float32(), unit_id=2),
    # 量測模組 (unit_id=3)
    ReadPoint(name="module3_voltage", address=100, data_type=Float32(), unit_id=3),
    ReadPoint(name="module3_current", address=102, data_type=Float32(), unit_id=3),
]

WRITE_POINTS = [
    # 主控寫入（default unit_id）
    WritePoint(name="power_cmd", address=200, data_type=UInt16()),
    # 各量測模組清零指令（per-module）
    WritePoint(name="module2_reset", address=300, data_type=UInt16(), unit_id=2),
    WritePoint(name="module3_reset", address=300, data_type=UInt16(), unit_id=3),
]


def main() -> None:
    config = DeviceConfig(device_id="multi_unit_dev", unit_id=1, read_interval=1.0)
    # 使用 AsyncMock 作為 client 佔位，避免真實網路 I/O；僅觀察靜態配置
    client = AsyncMock()

    device = AsyncModbusDevice(
        config=config,
        client=client,
        always_points=READ_POINTS,
        write_points=WRITE_POINTS,
    )

    # 1) 此設備實際觸及哪些 slave？
    print(f"此設備實際觸及的 unit_id = {sorted(device.used_unit_ids)}")
    # -> [1, 2, 3]

    # 2) PointGrouper 如何分桶？
    #    key = (read_group, function_code, unit_id)，不同 unit_id 產生獨立 group
    grouper = PointGrouper()
    groups = grouper.group(READ_POINTS)
    print(f"\n讀取群組數: {len(groups)}")
    for g in groups:
        names = [p.name for p in g.points]
        print(f"  fc={g.function_code}, unit_id={g.unit_id}, addr={g.start_address}, count={g.count}, points={names}")

    # 執行期語義（免真實硬體，僅列為註解）：
    #   - GroupReader：同 unit_id 請求串列、跨 unit_id 可並行（受 max_concurrent_reads 限制）
    #   - ValidatedWriter：write 與 verify read-back 使用同一 resolved unit_id


if __name__ == "__main__":
    main()
