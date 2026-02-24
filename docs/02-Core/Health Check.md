---
tags: [type/class, layer/core, status/complete]
source: csp_lib/core/health.py
---
# Health Check

> 健康狀態檢查

回到 [[_MOC Core]]

## 概述

`csp_lib.core.health` 提供統一的健康狀態報告介面，讓系統中的各元件可以回報自身的健康狀態。支援階層式健康報告（透過 `children` 欄位），方便組合多個子元件的狀態。

## 核心元件

### HealthStatus 列舉

| 值 | 說明 |
|----|------|
| `HEALTHY` | 正常運作 |
| `DEGRADED` | 部分降級（仍可運作但需注意） |
| `UNHEALTHY` | 異常（無法正常運作） |

### HealthReport 資料類別

`@dataclass(frozen=True)` — 不可變的健康報告。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | `HealthStatus` | 健康狀態 |
| `component` | `str` | 元件名稱 |
| `message` | `str` | 狀態訊息（預設為空字串） |
| `details` | `dict[str, Any]` | 額外詳細資訊（預設為空字典） |
| `children` | `list[HealthReport]` | 子元件的健康報告（預設為空列表） |

### HealthCheckable 協定

`@runtime_checkable` Protocol — 任何實作 `health()` 方法的類別皆可視為 `HealthCheckable`。

```python
class HealthCheckable(Protocol):
    def health(self) -> HealthReport: ...
```

## 使用範例

### 基本用法

```python
from csp_lib.core import HealthStatus, HealthReport, HealthCheckable

class MyComponent:
    def health(self) -> HealthReport:
        return HealthReport(
            status=HealthStatus.HEALTHY,
            component="my_component",
            message="All systems operational",
        )
```

### 階層式健康報告

```python
from csp_lib.core import HealthStatus, HealthReport

def system_health(components: list) -> HealthReport:
    children = [comp.health() for comp in components]

    # 若任一子元件異常，系統即為異常
    if any(c.status == HealthStatus.UNHEALTHY for c in children):
        status = HealthStatus.UNHEALTHY
    elif any(c.status == HealthStatus.DEGRADED for c in children):
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY

    return HealthReport(
        status=status,
        component="system",
        message=f"{len(children)} 個元件已檢查",
        children=children,
    )
```

### 型別檢查

```python
from csp_lib.core import HealthCheckable

component = MyComponent()
assert isinstance(component, HealthCheckable)  # runtime_checkable 支援
```

## 設計備註

- `HealthReport` 使用 `frozen=True` 確保報告建立後不可變更，避免狀態不一致
- `HealthCheckable` 使用 `@runtime_checkable` 裝飾器，支援 `isinstance()` 檢查
- `children` 欄位支援樹狀結構，適合由上層管理器彙整所有子元件的健康狀態
