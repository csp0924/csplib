---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/group_controller.py
---

# GroupControllerManager

多群組控制器管理器，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`GroupControllerManager` 將多台設備分成獨立控制群組，為每個群組建立獨立的 [[SystemController]] 實例。各群組擁有獨立的 `ModeManager`、`ProtectionGuard`、`StrategyExecutor` 與子 `DeviceRegistry`，實現完全的策略隔離與告警隔離。

繼承 `AsyncLifecycleMixin`，支援 `async with` 使用。

### 核心能力

- **設備分群**：將 master [[DeviceRegistry]] 中的設備分配到多個群組
- **獨立控制**：每組擁有獨立的模式管理、保護機制與策略執行
- **告警隔離**：一組設備告警不影響其他群組
- **統一管理**：提供統一的生命週期管理與健康檢查聚合

### 架構圖

```
Master DeviceRegistry
    ├── Group1: Sub-Registry → SystemController
    │     └── ModeManager / ProtectionGuard / Executor
    └── Group2: Sub-Registry → SystemController
          └── ModeManager / ProtectionGuard / Executor
```

## GroupDefinition

群組定義（frozen dataclass）。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `group_id` | `str` | 群組唯一識別碼 |
| `device_ids` | `list[str]` | 群組內的設備 ID 列表 |
| `config` | `SystemControllerConfig` | 該群組的控制器配置 |

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `registry` | [[DeviceRegistry]] | Master 設備查詢索引 |
| `groups` | `list[GroupDefinition]` | 群組定義列表 |

### 驗證規則

建構時自動驗證，違反時拋出 `ValueError`：

- 至少一個群組
- 群組 ID 不可重複
- 群組不可為空（需包含至少一台設備）
- 設備不可跨群組重複（錯誤訊息包含兩個群組名稱）
- 所有設備必須存在於 master registry 中

## API

### 模式管理

所有方法以 `group_id` 為第一個參數，委派至對應群組的 [[SystemController]]。未知 `group_id` 拋出 `KeyError`。

| 方法 | 說明 |
|------|------|
| `register_mode(group_id, name, strategy, priority, description="")` | 為指定群組註冊模式 |
| `set_base_mode(group_id, name)` | 設定指定群組的基礎模式 |
| `add_base_mode(group_id, name)` | 為指定群組新增基礎模式 |
| `remove_base_mode(group_id, name)` | 移除指定群組的基礎模式 |
| `push_override(group_id, name)` | 為指定群組推入 override 模式 |
| `pop_override(group_id, name)` | 移除指定群組的 override 模式 |
| `trigger(group_id)` | 觸發指定群組的策略執行 |
| `trigger_all()` | 觸發所有群組的策略執行 |

### 查詢

| 方法/屬性 | 回傳型別 | 說明 |
|-----------|----------|------|
| `get_controller(group_id)` | `SystemController` | 取得指定群組的控制器（未知時拋出 `KeyError`） |
| `group_ids` | `list[str]` | 所有群組 ID（排序） |
| `controllers` | `dict[str, SystemController]` | 所有群組控制器（副本） |
| `is_running` | `bool` | 是否有任何控制器正在執行 |
| `effective_mode_name(group_id)` | `str \| None` | 指定群組當前生效的模式名稱 |
| `health()` | `HealthReport` | 聚合健康報告（含各群組子報告） |

### 容器協定

| 方法 | 說明 |
|------|------|
| `__len__` | 群組數量 |
| `__contains__` | 檢查群組 ID 是否存在 |
| `__iter__` | 迭代 `(group_id, controller)` 對（按 group_id 排序） |

## 使用範例

```python
from csp_lib.integration import (
    GroupControllerManager, GroupDefinition,
    SystemControllerConfig, DeviceRegistry,
)
from csp_lib.controller import ModePriority

# Master registry
registry = DeviceRegistry()
registry.register(pcs_1, traits=["pcs"])
registry.register(bess_1, traits=["bess"])
registry.register(pcs_2, traits=["pcs"])
registry.register(bess_2, traits=["bess"])

# Create manager
manager = GroupControllerManager(
    registry=registry,
    groups=[
        GroupDefinition(
            group_id="group1",
            device_ids=["pcs_1", "bess_1"],
            config=SystemControllerConfig(
                context_mappings=[...],
                command_mappings=[...],
                system_base=SystemBase(p_base=500),
            ),
        ),
        GroupDefinition(
            group_id="group2",
            device_ids=["pcs_2", "bess_2"],
            config=SystemControllerConfig(
                context_mappings=[...],
                command_mappings=[...],
                system_base=SystemBase(p_base=500),
            ),
        ),
    ],
)

# Register strategies per group
manager.register_mode("group1", "pq", pq_strategy, ModePriority.MANUAL)
manager.register_mode("group2", "pv_smooth", pv_strategy, ModePriority.MANUAL)
await manager.set_base_mode("group1", "pq")
await manager.set_base_mode("group2", "pv_smooth")

# Run
async with manager:
    await asyncio.Event().wait()
```

### 進階存取

可透過 `get_controller()` 取得個別群組的 [[SystemController]]，進行更細粒度的操作：

```python
ctrl1 = manager.get_controller("group1")
print(ctrl1.protection_status)
print(ctrl1.alarmed_device_ids)
```

## 相關頁面

- [[SystemController]] — 單一群組控制器（被 GroupControllerManager 包裝）
- [[DeviceRegistry]] — 設備查詢索引
- [[GridControlLoop]] — 基礎版控制迴圈
- [[Full System Integration]] — 完整系統整合指南
