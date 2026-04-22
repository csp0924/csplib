---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/data_feed.py
updated: 2026-04-23
version: ">=0.10.0"
---

# DeviceDataFeed

設備事件 → [[HistoryBuffer]] 資料餵入，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`DeviceDataFeed` 訂閱設備的 `read_complete` 事件，將指定點位的值餵入 [[HistoryBuffer]]。透過 [[DataFeedMapping]] 指定目標設備。

> [!note] v0.10.0 多來源 API（PR #108）
> 新增 `mappings` / `history_buffers` keyword-only 參數，可同時維護多個獨立的資料流。
> 舊 API（`mapping` + `pv_service`）仍可用，內部正規化為 `{"pv_power": ...}` 的 dict 表達；
> `pv_service` 參數接受 `PVDataService`（`HistoryBuffer` 子類）。

### 設備解析模式

- **device_id 模式**：訂閱指定設備，直接餵入該設備的點位值
- **trait 模式**：訂閱所有匹配設備，任一設備觸發 `read_complete` 時聚合所有 responsive 設備的值

### 設計備註

實作與 [[DeviceEventSubscriber]] 相同的 subscribe/unsubscribe 模式，但不繼承該類別以避免 import `csp_lib.manager`（其 `__init__` 會載入可選依賴 motor）。

---

## 建構參數

### v0.10.0+ 多來源 API（推薦）

| 參數 | 型別 | 說明 |
|------|------|------|
| `registry` | [[DeviceRegistry]] | 設備查詢索引（必填） |
| `mappings` | `Mapping[str, DataFeedMapping] \| None` | （keyword-only）多來源映射字典 `{key: DataFeedMapping}` |
| `history_buffers` | `Mapping[str, HistoryBuffer] \| None` | （keyword-only）多來源緩衝字典 `{key: HistoryBuffer}` |

### Legacy API（向後相容）

| 參數 | 型別 | 說明 |
|------|------|------|
| `registry` | [[DeviceRegistry]] | 設備查詢索引（必填） |
| `mapping` | `DataFeedMapping \| None` | PV 資料來源映射（需與 `pv_service` 成對提供） |
| `pv_service` | `PVDataService \| HistoryBuffer \| None` | PV 資料服務（需與 `mapping` 成對提供） |

> [!warning] 新舊 API 不可混用
> 同時傳入 `mapping`/`pv_service` 與 `mappings`/`history_buffers` 會 raise `ValueError`。

---

## API

| 方法 / 屬性 | 說明 |
|------------|------|
| `attach()` | 解析目標設備並訂閱 `read_complete` 事件；部分失敗自動回滾所有訂閱 |
| `detach()` | 取消訂閱所有設備的事件 |
| `get_buffer(key)` | 依 key 取得 `HistoryBuffer`；不存在回 `None` |
| `buffers` | 所有 buffers 的不可變視圖（`MappingProxyType`） |
| `pv_service` | **Deprecated**：取得 legacy `"pv_power"` buffer；改用 `get_buffer("pv_power")` |

---

## 值處理規則

- 數值型（`int` / `float`）→ `buffer.append(float(value))`
- 非數值或缺失 → `buffer.append(None)`
- trait 模式：從所有 responsive 設備收集值，套用 `mapping.aggregate`（預設 `FIRST`）後餵入

---

## Quick Example

### v0.10.0+ 多來源（推薦）

```python
from csp_lib.integration import DeviceDataFeed, DeviceRegistry
from csp_lib.integration.schema import DataFeedMapping, AggregateFunc
from csp_lib.controller.services import HistoryBuffer

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
# ... 控制迴圈中取值
pv_avg = pv_buf.get_average()
feed.detach()
```

### Legacy API（舊程式碼相容）

```python
from csp_lib.integration import DeviceDataFeed, DeviceRegistry
from csp_lib.integration.schema import DataFeedMapping
from csp_lib.controller.services import PVDataService

pv_service = PVDataService(max_history=300)  # PVDataService 是 HistoryBuffer 子類
feed = DeviceDataFeed(
    registry=registry,
    mapping=DataFeedMapping(point_name="pv_power", trait="solar"),
    pv_service=pv_service,
)

feed.attach()
feed.detach()
```

---

## 相關頁面

- [[HistoryBuffer]] — 資料緩衝區（v0.10.0 取代 PVDataService 綁定語義）
- [[PVDataService]] — Deprecated，`HistoryBuffer` 子類
- [[DataFeedMapping]] — 映射定義
- [[DeviceRegistry]] — 設備查詢索引
- [[GridControlLoop]] — 自動管理 DeviceDataFeed 的 attach/detach
- [[SystemController]] — 自動管理 DeviceDataFeed 的 attach/detach
