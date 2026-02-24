---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/schema.py
---

# DataFeedMapping

設備值 → PVDataService 的映射定義，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`DataFeedMapping` 是一個 frozen dataclass，用於指定哪台設備的哪個點位作為 PV 發電功率資料來源，餵入 `PVDataService`。支援兩種模式：

- **device_id 模式**：指定特定設備
- **trait 模式**：取第一台 responsive 設備

兩者必須恰好設定其一（互斥）。

## 欄位

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `point_name` | `str` | 必填 | PV 功率點位名稱 |
| `device_id` | `str \| None` | `None` | 指定單一設備 ID（與 `trait` 擇一） |
| `trait` | `str \| None` | `None` | 指定 trait 標籤，取第一台 responsive 設備（與 `device_id` 擇一） |

## 使用範例

```python
from csp_lib.integration import DataFeedMapping

DataFeedMapping(
    point_name="pv_power",
    trait="solar",
)
```

## 相關頁面

- [[DeviceDataFeed]] — 使用 DataFeedMapping 訂閱設備事件並餵入 PVDataService
- [[ContextMapping]] — 設備值 → StrategyContext 映射
- [[CommandMapping]] — Command 欄位映射
