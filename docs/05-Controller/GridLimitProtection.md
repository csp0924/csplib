---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/dynamic_protection.py
updated: 2026-04-16
version: ">=0.7.2"
---

# GridLimitProtection

外部功率限制保護，從 [[RuntimeParameters]] 讀取功率限制百分比。

> [!info] v0.5.0 新增

> [!info] 回到 [[_MOC Controller]]

## 概述

讀取 [[RuntimeParameters]] 中的功率限制百分比，計算功率上限並 clamp 命令。適用於電力公司要求的功率限制或排程限制。

```
max_p = total_rated_kw × limit_pct / 100
```

正負 P 均受限制，clamp 至 `[-max_p, +max_p]`。

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `params` | `RuntimeParameters` | — | RuntimeParameters 實例 |
| `total_rated_kw` | `float` | — | 系統額定功率 (kW) |
| `limit_key` | `str` | `"grid_limit_pct"` | limit_pct 在 params 中的 key |

## 保護邏輯

| 條件 | 動作 |
|------|------|
| `P > max_p` | 限制放電：`P = max_p` |
| `P < -max_p` | 限制充電：`P = -max_p` |
| 其他 | 不介入 |

## RuntimeParameters Keys

| 鍵 | 型別 | 預設值 | 說明 |
|----|------|--------|------|
| `grid_limit_pct`（可自訂） | `float` | `100` | 功率限制百分比，自動 clamp 至 `[0, 100]`，100 = 無限制 |

> [!note] v0.7.2 值域與 NaN 防護
> - **值域 clamp（SEC-004）**：`evaluate()` 對 `grid_limit_pct` clamp 至 `[0, 100]`，防止 EMS 寫入超出範圍的值（如 `grid_limit_pct=200`）導致功率限制保護永不觸發
> - **NaN/Inf fail-safe（SEC-013a）**：context 的功率量測為非有限 float 時，passthrough 沿用上次的 `_is_triggered`，不強制觸發也不重置

## Quick Example

```python
from csp_lib.controller.system.dynamic_protection import GridLimitProtection
from csp_lib.core import RuntimeParameters

params = RuntimeParameters({"grid_limit_pct": 80})  # 限制 80%
grid_limit = GridLimitProtection(
    params=params,
    total_rated_kw=2000.0,
)

# 註冊至 ProtectionGuard
guard = ProtectionGuard(rules=[grid_limit])

# 後續由 EMS/Modbus 即時更新限制
params.set("grid_limit_pct", 50)  # 降至 50%
```

## 相關連結

- [[ProtectionGuard]] — 保護規則鏈
- [[RuntimeParameters]] — 動態參數來源
- [[DynamicSOCProtection]] — 同檔案的另一個動態保護規則
- [[Command]] — 被修改的命令物件
