---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/simulation/curve.py
---

# CurveRegistry

> 測試曲線註冊表

`CurveRegistry` 實作 `CurveProvider` Protocol，提供測試曲線的註冊、取得與管理功能。供 [[VirtualMeter]] 使用。

---

## CurveProvider Protocol

```python
class CurveProvider(Protocol):
    def get_curve(self, name: str) -> Iterator[CurvePoint] | None:
        """取得指定名稱的曲線迭代器"""

    def list_curves(self) -> list[str]:
        """列出所有可用曲線名稱"""
```

---

## CurvePoint

不可變的曲線點位定義：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `value` | `float` | 目標值（頻率 Hz 或電壓 V） |
| `duration` | `float` | 持續時間（秒） |
| `curve_type` | `CurveType` | 曲線類型（`FREQUENCY` 或 `VOLTAGE`） |

---

## 主要方法

| 方法 | 說明 |
|------|------|
| `register(name, factory)` | 註冊曲線工廠函式 |
| `unregister(name)` | 取消註冊曲線 |
| `get_curve(name)` | 取得曲線迭代器（每次呼叫產生新的迭代器） |
| `list_curves()` | 列出所有可用曲線名稱 |

---

## 內建曲線

系統提供 `DEFAULT_REGISTRY` 預設註冊表，包含以下內建曲線：

| 曲線名稱 | 函數 | 說明 |
|---------|------|------|
| `fp_step` | `curve_fp_step()` | FP 頻率階梯測試曲線（18 個頻率點，每點 3 秒） |
| `qv_step` | `curve_qv_step()` | QV 電壓階梯測試曲線（9 個電壓點，每點 3 秒） |

---

## 程式碼範例

```python
from csp_lib.equipment.simulation import CurveRegistry, VirtualMeter

# 使用預設曲線
meter = VirtualMeter()  # 自動使用 DEFAULT_REGISTRY
meter.start_test_curve("fp_step")

# 自定義曲線
registry = CurveRegistry()
registry.register("custom", my_curve_factory)

meter = VirtualMeter(curve_provider=registry)
meter.start_test_curve("custom")
```

---

## 相關頁面

- [[VirtualMeter]] -- 虛擬電表模擬器
- [[_MOC Equipment]] -- 設備模組總覽
