---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/transport/base.py
updated: 2026-04-22
version: ">=0.9.0"
---

# PointGrouper

> 點位分組器

`PointGrouper` 將多個 [[ReadPoint]] 自動合併為 `ReadGroup`，以減少 Modbus 請求次數。相鄰的暫存器會被合併成單一讀取群組，大幅提升通訊效率。

---

## 分組邏輯

1. 先按 `unit_id`、`read_group`、`function_code`、`address` 排序；其中 `unit_id=None` 會以 `-1` 作為排序 sentinel
2. 分桶 key = `(unit_id, read_group, function_code)`：三者皆相同的點位才會嘗試合併
3. 合併後的群組不超過各功能碼的最大讀取長度

> **v0.9.0+**：分桶與排序皆納入 `unit_id` 維度，且優先於 `read_group` / `function_code`。
> 不同 `ReadPoint.unit_id` 會產生獨立 `ReadGroup`；`unit_id=None` 僅在排序時以 `-1`
> 參與比較，不代表實際送出的 Modbus unit_id。詳見 [[Multi-UnitID Device]]。

### 各功能碼最大讀取長度

| Function Code | 最大長度 |
|--------------|----------|
| 1 (Read Coils) | 2000 |
| 2 (Read Discrete Inputs) | 2000 |
| 3 (Read Holding Registers) | 125 |
| 4 (Read Input Registers) | 125 |

---

## ReadGroup

分組後的不可變結果：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `function_code` | `int` | Modbus 功能碼 |
| `start_address` | `int` | 起始位址 |
| `count` | `int` | 暫存器/線圈數量 |
| `points` | `tuple[ReadPoint, ...]` | 包含的點位 |
| `unit_id` | `int \| None` | v0.9.0+：該群組送往的 Modbus unit_id；`None` 時 [[GroupReader]] fallback 為 `DeviceConfig.unit_id` |

---

## PointGrouperConfig

自訂各功能碼的最大讀取長度：

```python
from csp_lib.equipment.transport import PointGrouper, PointGrouperConfig

config = PointGrouperConfig(fc_max_length={3: 100, 4: 100})
grouper = PointGrouper(config=config)
```

---

## Quick Example

```python
from csp_lib.equipment.transport import PointGrouper

grouper = PointGrouper()
groups = grouper.group(points)  # list[ReadGroup]
```

---

## 相關頁面

- [[GroupReader]] -- 使用 ReadGroup 進行批次讀取
- [[ReadScheduler]] -- 排程固定與輪替讀取
- [[_MOC Equipment]] -- 設備模組總覽
