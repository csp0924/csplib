---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/transport/base.py
updated: 2026-04-04
version: ">=0.4.2"
---

# PointGrouper

> 點位分組器

`PointGrouper` 將多個 [[ReadPoint]] 自動合併為 `ReadGroup`，以減少 Modbus 請求次數。相鄰的暫存器會被合併成單一讀取群組，大幅提升通訊效率。

---

## 分組邏輯

1. 按 `read_group`、`function_code`、`address` 排序
2. 相同 `read_group` 和 `function_code` 的點位嘗試合併
3. 合併後的群組不超過各功能碼的最大讀取長度

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
