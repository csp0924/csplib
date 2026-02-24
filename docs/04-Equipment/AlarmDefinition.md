---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/alarm/definition.py
---

# AlarmDefinition

> 告警定義

`AlarmDefinition` 是不可變的 frozen dataclass，定義一個告警的代碼、名稱、等級與遲滯設定。告警代碼 (`code`) 作為唯一識別，用於 hash 計算。

---

## 參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `code` | `str` | (必填) | 告警代碼（唯一識別） |
| `name` | `str` | (必填) | 告警名稱 |
| `level` | `AlarmLevel` | `AlarmLevel.ALARM` | 告警等級 |
| `hysteresis` | `HysteresisConfig` | `NO_HYSTERESIS` | 遲滯設定 |
| `description` | `str` | `""` | 詳細描述 |

---

## AlarmLevel 列舉

| 等級 | 值 | 說明 |
|------|-----|------|
| `INFO` | 1 | 資訊告警 |
| `WARNING` | 2 | 警告告警（不影響系統運作） |
| `ALARM` | 3 | 重大告警（影響系統運作） |

---

## HysteresisConfig

遲滯設定用於避免邊緣觸發的抖動問題：

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `activate_threshold` | `int` | `1` | 連續 N 次觸發才啟用告警 |
| `clear_threshold` | `int` | `1` | 連續 N 次解除才清除告警 |

預設常數 `NO_HYSTERESIS = HysteresisConfig(1, 1)` 表示無遲滯。

---

## 程式碼範例

```python
from csp_lib.equipment.alarm import AlarmDefinition, AlarmLevel, HysteresisConfig

alarm = AlarmDefinition(
    code="OVER_TEMP",
    name="Temperature too high",
    level=AlarmLevel.WARNING,
    hysteresis=HysteresisConfig(
        activate_threshold=3,  # 連續 3 次觸發才啟用
        clear_threshold=5,     # 連續 5 次解除才清除
    ),
)
```

---

## 相關頁面

- [[Alarm Evaluators]] -- 告警評估器
- [[AlarmStateManager]] -- 告警狀態管理
- [[_MOC Equipment]] -- 設備模組總覽
