---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/core/command.py
created: 2026-02-17
---

# ConfigMixin

Config 類別的共用 Mixin，提供統一的 `from_dict()` 方法。

> [!info] 回到 [[_MOC Controller]]

## 概述

所有 Config 類別（如 [[PQModeStrategy|PQModeConfig]]、[[PVSmoothStrategy|PVSmoothConfig]] 等）均繼承 `ConfigMixin`，搭配 `@dataclass` 使用。提供從字典建立實例的功能，自動過濾不存在的欄位，並支援 camelCase 到 snake_case 的自動轉換。

## 方法

| 方法 | 說明 |
|------|------|
| `from_dict(data)` | 類別方法，從字典建立 Config 實例 |
| `to_dict()` | 轉換為字典 |

### from_dict 特性

- 自動過濾不存在於 dataclass 欄位的 key
- 支援 camelCase -> snake_case 轉換（例如 `rampRate` -> `ramp_rate`）
- 必須與 `@dataclass` 搭配使用，否則拋出 `TypeError`

## 程式碼範例

```python
from csp_lib.controller import PQModeConfig

# 基本用法
config = PQModeConfig.from_dict({"p": 100, "q": 50, "extra": "ignored"})

# camelCase 自動轉換
config = PQModeConfig.from_dict({"rampRate": 10})  # -> ramp_rate=10
```

## 使用 ConfigMixin 的類別

- [[PQModeStrategy|PQModeConfig]]
- [[PVSmoothStrategy|PVSmoothConfig]]
- [[QVStrategy|QVConfig]]
- [[FPStrategy|FPConfig]]
- [[IslandModeStrategy|IslandModeConfig]]
- [[SystemBase]]

## 相關連結

- [[SystemBase]] — 繼承 ConfigMixin 的不可變基準值
- [[_MOC Controller]] — 回到模組總覽
