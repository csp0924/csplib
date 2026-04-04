---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/device/action.py
---

# DOActions

> DO 動作抽象

> [!info] v0.6.0 新增

`DOActions` 模組提供結構化的 Digital Output 動作控制，涵蓋三種動作模式：脈衝、持續、切換。透過 `DOActionConfig` 宣告動作配置，透過 `Actionable` Protocol 統一調用介面。

---

## DOMode 列舉

| 模式 | 值 | 說明 |
|------|-----|------|
| `PULSE` | `"pulse"` | 寫 on → 延遲 `pulse_duration` → 寫 off |
| `SUSTAINED` | `"sustained"` | 寫 on，直到手動呼叫 off |
| `TOGGLE` | `"toggle"` | 讀取當前值，寫反向 |

---

## DOActionConfig

不可變的 frozen dataclass，定義單一 DO 動作。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `point_name` | `str` | (必填) | 對應的 [[WritePoint]] 名稱 |
| `label` | `str` | (必填) | 動作語義標籤（如 `"trip"`, `"reset"`, `"contactor_on"`） |
| `mode` | `DOMode` | `DOMode.SUSTAINED` | 動作模式 |
| `pulse_duration` | `float` | `0.5` | PULSE 模式的持續時間（秒） |
| `on_value` | `int` | `1` | 啟動值 |
| `off_value` | `int` | `0` | 關閉值 |

> [!warning] PULSE 驗證
> 當 `mode=DOMode.PULSE` 時，`pulse_duration` 必須 > 0，否則 `__post_init__` 會拋出 `ValueError`。

---

## Actionable Protocol

`@runtime_checkable` Protocol，定義 DO 動作介面。GUI / API / SCADA 可透過 `available_do_actions` 發現可用動作，透過 `execute_do_action` 統一調用。

```python
@runtime_checkable
class Actionable(Protocol):
    @property
    def available_do_actions(self) -> list[DOActionConfig]: ...

    async def execute_do_action(self, label: str, *, turn_off: bool = False) -> WriteResult: ...
```

[[AsyncModbusDevice]] 透過 `WriteMixin` 實作此 Protocol。

---

## Quick Example

```python
from csp_lib.equipment.device.action import DOMode, DOActionConfig

# PULSE — 寫 on，0.3 秒後自動寫 off（例：跳脫命令）
trip = DOActionConfig(
    point_name="do_trip",
    label="trip",
    mode=DOMode.PULSE,
    pulse_duration=0.3,
)

# SUSTAINED — 手動控制 on/off（例：接觸器控制）
contactor = DOActionConfig(
    point_name="do_contactor",
    label="contactor_on",
    mode=DOMode.SUSTAINED,
)

# TOGGLE — 每次執行自動反轉（例：指示燈切換）
lamp = DOActionConfig(
    point_name="do_lamp",
    label="toggle_lamp",
    mode=DOMode.TOGGLE,
)

# 配置到設備
device.configure_do_actions([trip, contactor, lamp])

# 執行動作
await device.execute_do_action("trip")             # PULSE: on → 0.3s → off
await device.execute_do_action("contactor_on")     # SUSTAINED: 寫 on
await device.execute_do_action("contactor_on", turn_off=True)  # SUSTAINED: 寫 off
await device.execute_do_action("toggle_lamp")      # TOGGLE: 自動反轉
```

---

## 與 AsyncModbusDevice 整合

DO 動作透過 `WriteMixin` 整合到 [[AsyncModbusDevice]]：

| 方法 / 屬性 | 說明 |
|------------|------|
| `configure_do_actions(configs)` | 配置 DO 動作列表（重複 label 拋出 `ValueError`） |
| `available_do_actions` | 取得所有已配置的 `DOActionConfig` 列表 |
| `execute_do_action(label, *, turn_off=False)` | 執行指定動作（回傳 `WriteResult`） |
| `cancel_pending_pulses()` | 取消所有進行中的 PULSE 任務（`stop()` 時自動呼叫） |

---

## 相關頁面

- [[AsyncModbusDevice]] -- 整合 DO 動作的設備類別
- [[WritePoint]] -- DO 動作對應的寫入點位
- [[ValidatedWriter]] -- 底層寫入實作
- [[_MOC Equipment]] -- 設備模組總覽
