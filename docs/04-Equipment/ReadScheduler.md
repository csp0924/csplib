---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/transport/scheduler.py
updated: 2026-04-04
version: ">=0.4.2"
---

# ReadScheduler

> 讀取排程器

`ReadScheduler` 支援「固定讀取」與「輪替讀取」兩種模式，解決大量點位讀取的效能問題。直接接收 [[PointGrouper]] 預計算的 `ReadGroup`，每次呼叫 `get_next_groups()` 回傳下一批要讀取的群組。

---

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `always_groups` | `Sequence[ReadGroup] \| None` | `None` | 每次都讀取的分組 |
| `rotating_groups` | `Sequence[Sequence[ReadGroup]] \| None` | `None` | 輪替讀取的分組列表 |

---

## 排程邏輯

```
第 1 次: always_groups + rotating_groups[0]
第 2 次: always_groups + rotating_groups[1]
第 3 次: always_groups + rotating_groups[2]
第 4 次: always_groups + rotating_groups[0]  (循環)
...
```

---

## 主要方法

| 方法 | 說明 |
|------|------|
| `get_next_groups()` | 取得下一批讀取群組（推進輪替索引） |
| `peek_next_groups()` | 預覽下一批讀取群組（不推進索引） |
| `reset()` | 重置輪替索引為 0 |
| `update_groups(always_groups, rotating_groups)` | 動態更新分組，`None` 表示保持不變 |

### 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `current_rotating_index` | `int` | 當前輪替索引 |
| `rotating_count` | `int` | 輪替群組數量 |
| `has_rotating` | `bool` | 是否有輪替群組 |

### update_groups()

`update_groups()` 允許在設備運行期間動態替換讀取分組，由 `AsyncModbusDevice.reconfigure()` 內部呼叫。

```python
# 動態更新固定分組（保留輪替分組不變）
scheduler.update_groups(always_groups=grouper.group(new_core_points))

# 同時更新固定與輪替分組
scheduler.update_groups(
    always_groups=grouper.group(new_always_points),
    rotating_groups=[
        grouper.group(new_group_a),
        grouper.group(new_group_b),
    ],
)
```

> [!note] 輪替索引重置
> 更新 `rotating_groups` 時，`_rotating_index` 自動重置為 0，確保從第一組開始輪替。更新 `always_groups` 不影響輪替索引。

---

## 程式碼範例

```python
from csp_lib.equipment.transport import PointGrouper, ReadScheduler

grouper = PointGrouper()

scheduler = ReadScheduler(
    always_groups=grouper.group(core_points),
    rotating_groups=[
        grouper.group(sbms1_points),
        grouper.group(sbms2_points),
    ],
)

# Cycle 1: always + rotating[0]
# Cycle 2: always + rotating[1]
# Cycle 3: always + rotating[0] ...
groups = scheduler.get_next_groups()
```

---

## 相關頁面

- [[PointGrouper]] -- 點位分組器
- [[GroupReader]] -- 群組讀取器
- [[_MOC Equipment]] -- 設備模組總覽
