---
tags: [type/class, layer/core, status/complete]
source: csp_lib/core/runtime_params.py
updated: 2026-04-04
version: v0.5.0
---
# RuntimeParameters

> Thread-safe 即時參數容器

> [!info] v0.5.0 新增

回到 [[_MOC Core]]

## 概述

`RuntimeParameters` 提供跨執行緒 / 跨 asyncio task 安全的參數讀寫容器。內部使用 `threading.Lock` 保護所有讀寫操作，確保 Modbus hook thread 與 asyncio event loop 之間的安全存取。

典型使用場景：
- [[ProtectionGuard]] 讀取動態 SOC 上下限、功率限制
- [[ModbusGatewayServer]] WriteHook 寫入 EMS 指令
- [[ContextBuilder]] 注入 `context.extra`
- 任何需要從外部系統即時更新的參數

```python
from csp_lib.core import RuntimeParameters
```

## 類別介面

```python
class RuntimeParameters:
    __slots__ = ("_values", "_lock", "_observers")

    def __init__(self, **initial_values: Any) -> None
```

### 讀取方法

| 方法 | 回傳型別 | 說明 |
|------|---------|------|
| `get(key, default=None)` | `Any` | 取得參數值，不存在時回傳 `default` |
| `snapshot()` | `dict[str, Any]` | 回傳所有參數的原子性淺拷貝 |
| `keys()` | `list[str]` | 回傳所有參數 key |
| `__contains__(key)` | `bool` | 支援 `key in params` 語法 |
| `__len__()` | `int` | 支援 `len(params)` 語法 |

### 寫入方法

| 方法 | 說明 |
|------|------|
| `set(key, value)` | 設定單一參數值，值變更時觸發 observers |
| `update(mapping)` | 批次更新多個參數，值變更時觸發 observers |
| `setdefault(key, default)` | 若 key 不存在則設定為 `default` 並回傳，存在則直接回傳 |
| `delete(key)` | 刪除參數，不存在時靜默忽略 |

### 觀察者方法

| 方法 | 說明 |
|------|------|
| `on_change(callback)` | 註冊變更通知回呼 |
| `remove_observer(callback)` | 移除已註冊的變更通知回呼 |

回呼簽名：`callback(key: str, old_value: Any, new_value: Any) -> None`

回呼在 `set`/`update`/`delete` 時**同步呼叫（在鎖外）**。若需要 async 操作，請在回呼內使用 `loop.call_soon_threadsafe()`。

## 型別別名

| 名稱 | 定義 | 說明 |
|------|------|------|
| `ChangeCallback` | `Callable[[str, Any, Any], None]` | 觀察者回呼簽名 |

## Quick Example

```python
from csp_lib.core import RuntimeParameters

# 建立參數容器
params = RuntimeParameters(
    soc_max=95.0,
    soc_min=5.0,
    grid_limit_pct=100,
)

# 讀取
soc_max = params.get("soc_max")       # 95.0
snap = params.snapshot()               # {"soc_max": 95.0, "soc_min": 5.0, ...}
print("soc_max" in params)             # True
print(len(params))                     # 3

# 寫入（觸發 observers）
params.set("soc_max", 90.0)

# 批次更新
params.update({"soc_max": 90.0, "soc_min": 10.0})

# 變更通知
def on_param_change(key: str, old: object, new: object) -> None:
    print(f"{key}: {old} -> {new}")

params.on_change(on_param_change)
params.set("soc_max", 85.0)  # 印出: soc_max: 90.0 -> 85.0
```

## 執行緒安全設計

- 所有讀寫操作透過 `threading.Lock` 保護
- Observer 回呼在鎖外執行，避免死鎖
- 單一 observer 例外不影響其他 observer
- `snapshot()` 回傳淺拷貝，保證原子性

## 相關頁面

- [[_MOC Core]] — Core 模組總覽
- [[ContextBuilder]] — 將 RuntimeParameters 注入 StrategyContext
- [[ModbusGatewayServer]] — WriteHook 透過 RuntimeParameters 傳遞 EMS 指令
