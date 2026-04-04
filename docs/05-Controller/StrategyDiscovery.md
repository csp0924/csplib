---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/discovery.py
created: 2026-03-06
updated: 2026-04-04
version: ">=0.4.2"
---

# StrategyDiscovery

策略插件自動發現機制，基於 `importlib.metadata.entry_points` 標準。

> [!info] 回到 [[_MOC Controller]]

## 概述

`discover_strategies` 函式允許第三方套件透過 `pyproject.toml` 的 `entry_points` 機制向 csp_lib 註冊自訂策略，而無需修改框架核心程式碼。這實現了**開閉原則**（Open-Closed Principle）：框架對擴充開放，對修改封閉。

---

## ENTRY_POINT_GROUP

```python
from csp_lib.controller import ENTRY_POINT_GROUP

ENTRY_POINT_GROUP = "csp_lib.strategies"
```

第三方套件在 `pyproject.toml` 中使用此群組名稱註冊策略：

```toml
[project.entry-points."csp_lib.strategies"]
my_custom_pq = "my_package.strategies:CustomPQStrategy"
custom_island = "my_package.island:ExtendedIslandStrategy"
```

---

## StrategyDescriptor

策略描述的凍結資料類別，由 `discover_strategies` 返回。

```python
from csp_lib.controller import StrategyDescriptor

@dataclass(frozen=True, slots=True)
class StrategyDescriptor:
    name: str                   # entry point 名稱（pyproject.toml 中的 key）
    strategy_class: type[Strategy]  # 策略類別（已載入）
    module: str                 # 策略的完整模組路徑（entry point value）
    description: str            # 策略說明（來自 class docstring 第一行）
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `name` | `str` | entry point 名稱，如 `"my_custom_pq"` |
| `strategy_class` | `type[Strategy]` | 已載入的策略類別，可直接實例化 |
| `module` | `str` | 完整的模組路徑，如 `"my_package.strategies:CustomPQStrategy"` |
| `description` | `str` | 從 class docstring 第一行提取的說明 |

---

## discover_strategies

```python
from csp_lib.controller import discover_strategies, ENTRY_POINT_GROUP

def discover_strategies(group: str = ENTRY_POINT_GROUP) -> list[StrategyDescriptor]:
    ...
```

掃描指定 entry_points 群組中所有已註冊策略，載入並返回 `StrategyDescriptor` 列表。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `group` | `str` | `"csp_lib.strategies"` | entry point 群組名稱 |

**返回值**：`list[StrategyDescriptor]`，載入失敗的策略會被跳過並記錄 warning（不拋出例外）。

> [!note] 容錯設計
> 若某個插件因依賴問題或程式碼錯誤而無法載入，`discover_strategies` 會記錄 warning 並繼續處理其他插件，確保一個插件的失敗不會影響整個發現流程。

---

## 使用範例

### 掃描並列出所有已安裝的策略插件

```python
from csp_lib.controller import discover_strategies

descriptors = discover_strategies()

for desc in descriptors:
    print(f"策略: {desc.name}")
    print(f"  類別: {desc.strategy_class.__name__}")
    print(f"  模組: {desc.module}")
    print(f"  說明: {desc.description}")
```

### 動態載入並註冊發現的策略

```python
from csp_lib.controller import discover_strategies

descriptors = discover_strategies()

for desc in descriptors:
    # 根據配置實例化策略（假設策略接受 config 字典）
    strategy_instance = desc.strategy_class()  # 實際參數視策略而定
    controller.register_mode(
        desc.name,
        strategy_instance,
        priority=50,
        description=desc.description,
    )
```

### 第三方套件：在 pyproject.toml 中註冊策略

```toml
# 第三方套件的 pyproject.toml
[project.entry-points."csp_lib.strategies"]
solar_pv_smooth = "mylib.strategies:SolarPVSmoothStrategy"
demand_response = "mylib.strategies:DemandResponseStrategy"
```

安裝第三方套件後，`discover_strategies()` 即可自動發現上述策略。

---

## 相關連結

- [[Strategy]] — 策略抽象基礎類別
- [[ModeManager]] — 管理已發現策略的註冊與切換
- [[SystemController]] — 整合策略發現與模式管理的頂層元件
- [[_MOC Controller]] — 控制器模組總覽
