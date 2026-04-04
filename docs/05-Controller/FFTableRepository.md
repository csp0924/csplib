---
tags:
  - type/protocol
  - layer/controller
  - status/complete
source: csp_lib/controller/compensator.py
updated: 2026-04-04
version: ">=0.5.0"
---

# FFTableRepository

FF Table 持久化介面，定義 [[PowerCompensator]] 存取 FF Table 的抽象層。

> [!info] v0.5.0 新增

> [!info] 回到 [[_MOC Controller]]

## 概述

`FFTableRepository` 是 `@runtime_checkable Protocol`，實作此 Protocol 即可支援任意儲存後端（JSON、MongoDB、Redis 等）。[[PowerCompensator]] 透過此介面存取 FF Table。

## Protocol 定義

```python
@runtime_checkable
class FFTableRepository(Protocol):
    def save(self, table: dict[int, float]) -> None: ...
    def load(self) -> dict[int, float] | None: ...
```

| 方法 | 說明 |
|------|------|
| `save(table)` | 儲存 FF Table（`{bin_index: ff_factor}`） |
| `load()` | 載入 FF Table，不存在時回傳 `None` |

## 內建實作

### JsonFFTableRepository

JSON 檔案持久化（預設實作）。支援不同 `power_bin_step_pct` 的 FF Table 自動遷移（線性插值）。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `path` | `str` | — | JSON 檔案路徑 |
| `power_bin_step_pct` | `int` | `5` | 當前 step 百分比（用於遷移偵測） |

```python
from csp_lib.controller.compensator import JsonFFTableRepository

repo = JsonFFTableRepository("ff_table.json", power_bin_step_pct=5)
repo.save({0: 1.0, 1: 1.02, -1: 0.98})
table = repo.load()  # {0: 1.0, 1: 1.02, -1: 0.98}
```

### MongoFFTableRepository

MongoDB 持久化，將 FF Table 存為單一 document。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `collection` | motor `AsyncIOMotorCollection` | — | MongoDB collection |
| `document_id` | `str` | `"ff_table"` | document 的 `_id` |

MongoDB document 格式：

```json
{
    "_id": "ff_table",
    "table": {"0": 1.0, "5": 1.02, "-5": 0.98},
    "updated_at": "2026-04-04T00:00:00Z"
}
```

> [!note] `MongoFFTableRepository.load()` 為同步 placeholder（回傳 None）。需在 event loop 啟動後呼叫 `async_load()` 載入資料。

```python
from csp_lib.controller.compensator import MongoFFTableRepository, PowerCompensator

repo = MongoFFTableRepository(collection, document_id="ff_table")
compensator = PowerCompensator(config, repository=repo)

# event loop 啟動後載入
table = await repo.async_load()
if table:
    compensator.load_ff_table(table)
```

## Quick Example

```python
from csp_lib.controller.compensator import (
    PowerCompensator,
    PowerCompensatorConfig,
    JsonFFTableRepository,
)

# 使用 JSON repository
repo = JsonFFTableRepository("data/ff_table.json")
compensator = PowerCompensator(
    config=PowerCompensatorConfig(rated_power=2000.0),
    repository=repo,
)

# 或直接透過 persist_path（自動建立 JsonFFTableRepository）
compensator = PowerCompensator(
    config=PowerCompensatorConfig(
        rated_power=2000.0,
        persist_path="data/ff_table.json",
    ),
)
```

## 相關連結

- [[PowerCompensator]] — 使用此 Protocol 的補償器
- [[FFCalibrationStrategy]] — 校準後透過此介面持久化結果
