---
tags:
  - type/guide
  - layer/equipment
  - status/complete
created: 2026-04-22
updated: 2026-04-22
version: ">=0.9.0"
---

# Multi-UnitID Device 指南

> 單一 `AsyncModbusDevice` 對應多個 Modbus `unit_id`（slave address）的設定與使用

## 使用時機

部分工業設備會把**不同功能**暴露在「**同一個 TCP endpoint**（或共用 RTU 匯流排）」上的**不同 unit_id**。典型場景：

- 整合型 PCS：主控邏輯在 `unit_id=1`，內部模組量測分散到 `unit_id=2, 3, 4...`
- 多回路電錶：同一實體機、每個回路一個 unit_id
- 共用 serial bus 的多個 sensor：實體上一台，協定上多個 slave

這種情況下，把它們抽象成**一個** `AsyncModbusDevice`（而不是多個）會更貼近使用者的心智模型：

- 共用 lifecycle（一次 `connect / disconnect`）
- 共用 event stream（`value_change` / `alarm_triggered`）
- 共用告警 / capability / ACTIONS 映射
- 告警規則可以跨 unit_id 評估（例如「module2 電壓過高 OR module3 電壓過高」）

---

## 快速開始

```python
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.modbus import Float32, UInt16

config = DeviceConfig(device_id="multi_unit_dev", unit_id=1)  # default slave

read_points = [
    ReadPoint(name="status", address=0, data_type=UInt16()),              # 用 default (unit_id=1)
    ReadPoint(name="m2_voltage", address=100, data_type=Float32(), unit_id=2),
    ReadPoint(name="m3_voltage", address=100, data_type=Float32(), unit_id=3),
]

write_points = [
    WritePoint(name="cmd", address=200, data_type=UInt16()),              # default
    WritePoint(name="m2_reset", address=300, data_type=UInt16(), unit_id=2),
]

device = AsyncModbusDevice(config=config, client=client,
                           always_points=read_points, write_points=write_points)

print(device.used_unit_ids)     # frozenset({1, 2, 3})
```

完整可執行範例：`examples/17_multi_unit_device.py`

---

## 核心語義

### Sentinel resolve

- [[ReadPoint]] / [[WritePoint]] 的 `unit_id` 欄位型別為 `int | None`
- `None`（預設） = sentinel：實際送出的請求採用 `DeviceConfig.unit_id`
- 明確指定 int = 覆寫：僅此點位走該 unit_id

### Grouping

[[PointGrouper]] 分桶 key 為 `(function_code, unit_id)`：

- 相同 `fc` + 不同 `unit_id` **不會**被合併到同一個 `ReadGroup`
- 每個 `ReadGroup` 帶上 `unit_id` 一起傳入 [[GroupReader]]
- 結果：至少產生 N 個獨立 Modbus 請求，N = 點位組合出的 distinct unit_id 數量

### Concurrency

[[GroupReader]] 對每個 unit_id 維護獨立 semaphore：

- **同 unit_id** 請求：串列（保護單一 slave，避免被自己的重疊請求打爆）
- **跨 unit_id** 請求：可並行（受 `max_concurrent_reads` 全域上限制）

[[ValidatedWriter]]：write 與 verify read-back 使用同一個 resolved unit_id，確保確認讀回的是剛寫入的 slave。

### used_unit_ids property

`AsyncModbusDevice.used_unit_ids` 回傳 `frozenset[int]`：

- 在 `__init__` 一次計算，快取
- 內容 = `{config.unit_id}` ∪ `{p.unit_id for p in 所有點位 if p.unit_id is not None}`
- `reconfigure()` 變更點位集合時自動重算
- 用途：診斷、GUI 顯示、per-slave 資源配置

---

## 設計取捨

### Q: 什麼時候應該拆成多個 device？

| 情境 | 建議 |
|------|------|
| 物理上就是獨立機、只是共用 TCP gateway | 拆多個 `AsyncModbusDevice`（每台獨立 config / client） |
| 物理上一台，協定上多 slave（整合型設備） | 單一 `AsyncModbusDevice` + multi-unit 點位 |
| 故障邊界：一個 slave 掛了，其他 slave 應繼續運作 | 拆多個（避免 health state 連動） |
| 告警需要跨 slave 聯合判斷 | 單一（共用告警 context） |

### Q: 為什麼不在 ReadPoint 本身綁 client？

保留**一 device = 一 client**的簡單模型：所有連線/重連/健康判定仍集中在 `AsyncModbusDevice` lifecycle，不需要多 client 協調。Multi-unit 只影響 Modbus 幀的 `unit_id` 欄位，不改變網路層。

### Q: 能不能混合 TCP + RTU？

不行。single client 的 transport 是固定的；如果需要跨 transport 聚合，請用上層（`DeviceManager` 或 `SystemController`）組合多個 device。

---

## 相關

- [[ReadPoint]] — `unit_id` 欄位定義
- [[WritePoint]] — `unit_id` 欄位定義
- [[PointGrouper]] — per-unit_id 分桶邏輯
- [[GroupReader]] — per-unit semaphore 並行模型
- [[ValidatedWriter]] — write + verify 的 unit_id 一致性
- [[AsyncModbusDevice]] — `used_unit_ids` property
