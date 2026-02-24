---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/alarm/evaluator.py
---

# Alarm Evaluators

> 告警評估器

告警評估器繼承自 `AlarmEvaluator` 抽象基底類別，根據點位值評估是否觸發告警。每個評估器關聯一個 `point_name`，並回傳 `{告警代碼: 是否觸發}` 字典。

---

## 抽象介面

```python
class AlarmEvaluator(ABC):
    point_name: str

    @abstractmethod
    def evaluate(self, value: Any) -> dict[str, bool]:
        """評估告警狀態，回傳 {告警代碼: 是否觸發}"""

    @abstractmethod
    def get_alarms(self) -> list[AlarmDefinition]:
        """取得所有告警定義"""
```

---

## BitMaskAlarmEvaluator

位元遮罩告警評估器。檢查暫存器值的特定位元是否為 1，每個位元對應一個 [[AlarmDefinition]]。

| 參數 | 型別 | 說明 |
|------|------|------|
| `point_name` | `str` | 關聯的點位名稱 |
| `bit_alarms` | `dict[int, AlarmDefinition]` | `{位元位置: 告警定義}` 字典 |

```python
from csp_lib.equipment.alarm import (
    BitMaskAlarmEvaluator,
    AlarmDefinition,
)

bitmask = BitMaskAlarmEvaluator(
    point_name="fault_code",
    bit_alarms={
        0: AlarmDefinition("OV", "Over Voltage"),
        1: AlarmDefinition("UV", "Under Voltage"),
    },
)
```

---

## ThresholdAlarmEvaluator

閾值告警評估器。根據數值與閾值比較判斷告警，支援 `>`, `>=`, `<`, `<=`, `==`, `!=` 六種運算子。

| 參數 | 型別 | 說明 |
|------|------|------|
| `point_name` | `str` | 關聯的點位名稱 |
| `conditions` | `list[ThresholdCondition]` | 閾值條件列表 |

### ThresholdCondition

| 參數 | 型別 | 說明 |
|------|------|------|
| `alarm` | `AlarmDefinition` | 告警定義 |
| `operator` | `Operator` | 比較運算子 |
| `value` | `float` | 閾值 |

### Operator 列舉

| 值 | 說明 |
|-----|------|
| `GT` | `>` |
| `GE` | `>=` |
| `LT` | `<` |
| `LE` | `<=` |
| `EQ` | `==` |
| `NE` | `!=` |

```python
from csp_lib.equipment.alarm import (
    ThresholdAlarmEvaluator,
    ThresholdCondition,
    Operator,
    AlarmDefinition,
)

threshold = ThresholdAlarmEvaluator(
    point_name="temperature",
    conditions=[
        ThresholdCondition(
            alarm=AlarmDefinition("HIGH_TEMP", "High Temperature"),
            operator=Operator.GT,
            value=45.0,
        ),
    ],
)
```

---

## TableAlarmEvaluator

查表告警評估器。根據值精確匹配查表判斷告警。

| 參數 | 型別 | 說明 |
|------|------|------|
| `point_name` | `str` | 關聯的點位名稱 |
| `table` | `dict[int, AlarmDefinition]` | `{值: 告警定義}` 字典 |

```python
from csp_lib.equipment.alarm import (
    TableAlarmEvaluator,
    AlarmDefinition,
)

table = TableAlarmEvaluator(
    point_name="status",
    table={
        3: AlarmDefinition("FAULT", "Device Fault"),
        4: AlarmDefinition("EMERGENCY", "Emergency Stop"),
    },
)
```

---

## 相關頁面

- [[AlarmDefinition]] -- 告警定義與等級
- [[AlarmStateManager]] -- 告警狀態管理
- [[_MOC Equipment]] -- 設備模組總覽
