---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/core/point.py
---

# Validators

> 值驗證器

驗證器實作 `ValueValidator` Protocol，提供 `validate(value)` 和 `get_error_message(value)` 兩個方法。用於 [[WritePoint]] 的寫入前驗證。

---

## 內建驗證器

| 驗證器 | 參數 | 說明 |
|--------|------|------|
| `RangeValidator` | `min_value: float \| None`, `max_value: float \| None` | 範圍驗證，值必須在 `[min_value, max_value]` 之間 |
| `EnumValidator` | `allowed_values: tuple[Any, ...]` | 枚舉驗證，值必須在允許列表中 |
| `CompositeValidator` | `validators: tuple[ValueValidator, ...]` | 組合驗證器，所有子驗證器都通過才算通過 |

---

## ValueValidator Protocol

所有驗證器都實作以下介面：

```python
class ValueValidator(Protocol):
    def validate(self, value: Any) -> bool:
        """驗證值是否合法"""
        ...

    def get_error_message(self, value: Any) -> str:
        """取得錯誤訊息"""
        ...
```

---

## 程式碼範例

```python
from csp_lib.equipment.core import RangeValidator, EnumValidator, CompositeValidator

# 範圍驗證
range_v = RangeValidator(min_value=0, max_value=10000)
range_v.validate(5000)   # True
range_v.validate(20000)  # False

# 枚舉驗證
enum_v = EnumValidator(allowed_values=(0, 1, 2))
enum_v.validate(1)  # True
enum_v.validate(5)  # False

# 組合驗證
composite = CompositeValidator(validators=(
    RangeValidator(min_value=0, max_value=100),
    EnumValidator(allowed_values=(0, 25, 50, 75, 100)),
))
composite.validate(50)   # True
composite.validate(30)   # False (不在枚舉列表)
```

---

## 相關頁面

- [[WritePoint]] -- 使用驗證器的寫入點位
- [[_MOC Equipment]] -- 設備模組總覽
