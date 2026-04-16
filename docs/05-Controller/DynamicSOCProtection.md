---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/dynamic_protection.py
updated: 2026-04-16
version: ">=0.7.2"
---

# DynamicSOCProtection

動態 SOC 保護規則，支援從 [[RuntimeParameters]] 即時讀取 SOC 上下限。

> [!info] v0.5.0 新增

> [!warning] Deprecated — 舊版 `SOCProtection`
> [[SOCProtection]] 使用 frozen dataclass 配置，無法即時更新參數。
> `DynamicSOCProtection` 取代其功能，同時支援 `RuntimeParameters`（動態）和 `SOCProtectionConfig`（靜態）兩種參數來源。

> [!info] 回到 [[_MOC Controller]]

## 概述

根據 SOC 狀態限制充放電功率，支援兩種參數來源：

1. **[[RuntimeParameters]]（動態）** — 每次 `evaluate()` 從 RuntimeParameters 讀取 `soc_max` / `soc_min`，支援即時更新（來自 EMS/Modbus/Redis）
2. **SOCProtectionConfig（靜態）** — 從 frozen dataclass 讀取固定的 `soc_high` / `soc_low` / `warning_band`

> [!note] 功率正負號定義：P > 0 = 放電，P < 0 = 充電。SOC 為 None 時不介入。

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `params` | `RuntimeParameters \| SOCProtectionConfig` | — | 參數來源 |
| `soc_max_key` | `str` | `"soc_max"` | soc_max 在 RuntimeParameters 中的 key |
| `soc_min_key` | `str` | `"soc_min"` | soc_min 在 RuntimeParameters 中的 key |
| `warning_band` | `float` | `0.0` | 警戒區寬度 (%)，0 = 不啟用漸進限制 |

## 保護邏輯

### 禁止區

- `soc >= soc_max` 且 `P < 0`（充電）-> `P = 0`
- `soc <= soc_min` 且 `P > 0`（放電）-> `P = 0`

### 警戒區（漸進限制）

```
高側警戒區: soc_max - warning_band <= soc < soc_max
  ratio = (soc_max - soc) / warning_band    // 1.0 -> 0.0
  limited_p = p × ratio

低側警戒區: soc_min < soc <= soc_min + warning_band
  ratio = (soc - soc_min) / warning_band    // 0.0 -> 1.0
  limited_p = p × ratio
```

## RuntimeParameters Keys

僅在 RuntimeParameters 模式下使用：

| 鍵 | 型別 | 預設值 | 說明 |
|----|------|--------|------|
| `soc_max`（可自訂） | `float` | `95.0` | SOC 上限 (%)，自動 clamp 至 `[0, 100]` |
| `soc_min`（可自訂） | `float` | `5.0` | SOC 下限 (%)，自動 clamp 至 `[0, 100]` |

> [!note] v0.7.2 值域保護
> `_resolve_limits()` 在使用前對 `soc_max` / `soc_min` 執行兩層防禦：
> 1. **NaN/Inf 過濾**（SEC-013a）：非有限值直接使用預設值，避免 `<` 比較永遠 False 而無聲繞過保護
> 2. **值域 clamp**（SEC-004）：clamp 至 `[0, 100]`，防止 EMS 寫入 `soc_max=200` 導致上限保護永不觸發

## Quick Example

```python
from csp_lib.controller.system.dynamic_protection import DynamicSOCProtection
from csp_lib.core import RuntimeParameters

# 動態模式：從 RuntimeParameters 讀取
params = RuntimeParameters({"soc_max": 95.0, "soc_min": 5.0})
soc_protection = DynamicSOCProtection(params, warning_band=5.0)

# 靜態模式：從 SOCProtectionConfig 讀取
from csp_lib.controller.system.protection import SOCProtectionConfig
config = SOCProtectionConfig(soc_high=95.0, soc_low=5.0, warning_band=5.0)
soc_protection = DynamicSOCProtection(config)

# 註冊至 ProtectionGuard
guard = ProtectionGuard(rules=[soc_protection])
```

> [!warning] v0.7.2 行為變更（BUG-003）
> `soc_max < soc_min` 的反轉配置現在會直接拋出 `ValueError`（原本靜默運作但會同時禁止充放電，導致 BESS 癱瘓）。請在系統啟動前確認 SOC 上下限配置正確。

> [!note] v0.7.2 NaN/Inf fail-safe（SEC-013a）
> context 中 SOC 值為非有限 float（NaN/Inf）時，保護規則不強制觸發，也不重置，而是 passthrough 沿用上次的 `_is_triggered` 狀態，避免感測器短暫異常導致誤停機。

## 相關連結

- [[SOCProtection]] — 舊版靜態 SOC 保護（建議改用本類別）
- [[ProtectionGuard]] — 保護規則鏈
- [[RuntimeParameters]] — 動態參數來源
- [[GridLimitProtection]] — 同檔案的另一個動態保護規則
- [[Command]] — 被修改的命令物件
