---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/services/history_buffer.py
created: 2026-04-23
updated: 2026-04-23
version: ">=0.10.0"
---

# HistoryBuffer

通用時序資料緩衝區，供策略層跨 tick 存取歷史數值。

> [!info] 回到 [[_MOC Controller]]

## 概述

`HistoryBuffer` 收集並維護單一來源的歷史數值（`float`），使用 `collections.deque` 自動淘汰最舊資料。語義中性，不綁定特定物理量；命名由擁有者（如 `DeviceDataFeed` / `SystemController`）以 key 區分（如 `"pv_power"`, `"grid_power"`, `"battery_soc"`）。

> [!note] v0.10.0：取代 PVDataService 綁定語義（PR #108）
> `PVDataService` 已改為繼承 `HistoryBuffer`（向後相容）並發出 `DeprecationWarning`。
> 新程式碼應直接使用 `HistoryBuffer`；`DeviceDataFeed` 的 `history_buffers` 參數接受 `HistoryBuffer`。

---

## 建構參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `max_history` | `int` | `300` | 最大歷史筆數（超過後自動丟棄最舊資料）；必須 >= 1 |

**Raises：** `ValueError` — `max_history < 1`

---

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `max_history` | `int` | 最大歷史筆數（唯讀） |
| `count` | `int` | 目前資料筆數（含 `None` 佔位） |

---

## 方法

| 方法 | 回傳 | 說明 |
|------|------|------|
| `append(value)` | `None` | 新增一筆資料；`None` 代表讀取失敗佔位（仍佔 slot，但被過濾方法排除） |
| `get_history()` | `list[float]` | 取得有效歷史資料（過濾 `None`）；全為 `None` 回傳空 list |
| `get_latest()` | `float \| None` | 取得最新一筆有效值（跳過末端 `None`）；無有效值回 `None` |
| `get_average()` | `float \| None` | 計算有效值算術平均；無有效值回 `None` |
| `clear()` | `None` | 清空所有歷史資料 |
| `__len__()` | `int` | 有效資料筆數（不含 `None`） |
| `__str__()` | `str` | `HistoryBuffer(count=N, valid=M)` |

---

## Quick Example

### 基本使用

```python
from csp_lib.controller.services import HistoryBuffer

buf = HistoryBuffer(max_history=300)

# 餵入資料（None 代表讀取失敗）
buf.append(500.0)
buf.append(510.0)
buf.append(None)   # 讀取失敗佔位
buf.append(490.0)

print(buf.count)           # 4（含 None）
print(len(buf))            # 3（有效筆數）
print(buf.get_latest())    # 490.0
print(buf.get_average())   # (500 + 510 + 490) / 3 ≈ 500.0
print(buf.get_history())   # [500.0, 510.0, 490.0]
```

### 搭配 DeviceDataFeed 多來源

```python
import asyncio
from csp_lib.controller.services import HistoryBuffer
from csp_lib.integration import DeviceDataFeed
from csp_lib.integration.schema import DataFeedMapping, AggregateFunc

pv_buf = HistoryBuffer(max_history=300)
grid_buf = HistoryBuffer(max_history=60)

feed = DeviceDataFeed(
    registry=registry,
    mappings={
        "pv_power": DataFeedMapping(point_name="pv_power", trait="solar"),
        "grid_power": DataFeedMapping(
            point_name="grid_power", trait="meter",
            aggregate=AggregateFunc.SUM,
        ),
    },
    history_buffers={
        "pv_power": pv_buf,
        "grid_power": grid_buf,
    },
)

feed.attach()

# 控制迴圈中取得歷史資料
pv_avg = pv_buf.get_average()     # 近 300 筆 PV 功率平均
grid_latest = grid_buf.get_latest()  # 最新電網功率
```

### 在策略中使用

```python
from csp_lib.controller import Strategy, StrategyContext, Command
from csp_lib.controller.services import HistoryBuffer

class MyStrategy(Strategy):
    def __init__(self, pv_buf: HistoryBuffer, grid_buf: HistoryBuffer) -> None:
        self._pv_buf = pv_buf
        self._grid_buf = grid_buf

    async def execute(self, ctx: StrategyContext) -> Command:
        pv_avg = self._pv_buf.get_average() or 0.0
        grid = self._grid_buf.get_latest() or 0.0
        target_p = grid - pv_avg
        return Command(p_target=target_p, q_target=0.0)
```

---

## 設計備註

- **Thread safety**：非 thread-safe，預期由單一 asyncio event loop 存取。
- `deque(maxlen=max_history)` 自動移除最舊資料，O(1) append。
- `get_average()` 使用 `statistics.fmean`（比 `sum/len` 精度略高）。
- `__len__` 回傳有效筆數（不含 `None`），`count` 回傳全部筆數（含 `None`），語義不同。

---

## 相關頁面

- [[PVDataService]] — `HistoryBuffer` 的 deprecated 子類，向後相容
- [[DeviceDataFeed]] — 自動餵入多個 `HistoryBuffer`（`history_buffers=` kw-only）
- [[_MOC Controller]] — 回到模組總覽
