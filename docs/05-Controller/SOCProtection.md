---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/system/protection.py
created: 2026-02-17
---

# SOCProtection

SOC 保護規則，提供高低限保護與警戒區漸進限制。

> [!info] 回到 [[_MOC Controller]]

## 概述

根據儲能系統的 SOC (State of Charge) 狀態限制充放電功率：
- SOC >= soc_high: 禁止充電 (clamp P >= 0)
- SOC <= soc_low: 禁止放電 (clamp P <= 0)
- 警戒區: 漸進限制功率

> [!note] 功率正負號定義：P > 0 = 放電，P < 0 = 充電。SOC 為 None 時不介入。

## SOCProtectionConfig

`@dataclass(frozen=True)` 的保護配置。

| 屬性 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `soc_high` | `float` | `95.0` | SOC 上限 (%)，達到時禁止充電 |
| `soc_low` | `float` | `5.0` | SOC 下限 (%)，達到時禁止放電 |
| `warning_band` | `float` | `5.0` | 警戒區寬度 (%) |

## 保護邏輯

### 禁止區

- `soc >= soc_high` 且 `P < 0` (充電) -> `P = 0`
- `soc <= soc_low` 且 `P > 0` (放電) -> `P = 0`

### 警戒區 (漸進限制)

```
高側警戒區: soc_high - warning_band <= soc < soc_high
  ratio = (soc_high - soc) / warning_band  // 1.0 -> 0.0
  limited_p = p * ratio

低側警戒區: soc_low < soc <= soc_low + warning_band
  ratio = (soc - soc_low) / warning_band   // 0.0 -> 1.0
  limited_p = p * ratio
```

### SOC 區間圖

```
 0%   5%   10%          90%   95%  100%
  |    |    |            |     |    |
  | 禁放 | 漸進放電限制 |  正常  | 漸進充電限制 | 禁充 |
  |    |    |            |     |    |
       low  low+band     high-band  high
```

## 資料來源

| 鍵 | 來源 | 說明 |
|----|------|------|
| `context.soc` | [[StrategyContext]] | 儲能系統 SOC (%) |

## 相關連結

- [[ProtectionGuard]] — 保護規則鏈，管理此規則
- [[ReversePowerProtection]] — 另一個保護規則
- [[SystemAlarmProtection]] — 另一個保護規則
- [[Command]] — 被修改的命令物件
