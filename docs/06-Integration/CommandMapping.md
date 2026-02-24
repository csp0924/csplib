---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/schema.py
---

# CommandMapping

Command → 設備寫入的映射定義，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`CommandMapping` 是一個 frozen dataclass，用於宣告如何將策略輸出的 `Command` 欄位路由到設備寫入操作。支援兩種模式：

- **device_id 模式**：寫入單一指定設備（Unicast）
- **trait 模式**：廣播寫入所有匹配設備（Broadcast）

兩者必須恰好設定其一（互斥）。

## 欄位

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `command_field` | `str` | 必填 | Command 屬性名稱（`"p_target"` / `"q_target"`） |
| `point_name` | `str` | 必填 | 目標設備寫入點位名稱 |
| `device_id` | `str \| None` | `None` | 指定單一設備 ID（與 `trait` 擇一） |
| `trait` | `str \| None` | `None` | 指定 trait 標籤，廣播寫入所有匹配設備（與 `device_id` 擇一） |
| `transform` | `Callable[[float], Any] \| None` | `None` | 值轉換函式，寫入前套用（例如均分功率） |

## 使用範例

```python
from csp_lib.integration import CommandMapping

CommandMapping(
    command_field="p_target",
    point_name="p_setpoint",
    trait="pcs",
    transform=lambda p: p / num_pcs,  # Split power evenly
)
```

## 相關頁面

- [[CommandRouter]] — 使用 CommandMapping 路由 Command 至設備
- [[ContextMapping]] — 設備值 → StrategyContext 映射
- [[DataFeedMapping]] — PV 資料餵入映射
