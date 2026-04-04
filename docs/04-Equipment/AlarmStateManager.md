---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/alarm/state.py
updated: 2026-04-04
version: ">=0.4.2"
---

# AlarmStateManager

> 告警狀態管理器

`AlarmStateManager` 管理所有告警的狀態，提供遲滯處理機制。由 [[AsyncModbusDevice]] 內部自動建立與使用，不需手動操作。

---

## 核心概念

- **遲滯處理**：透過 `HysteresisConfig` 的 `activate_threshold` 和 `clear_threshold` 避免邊緣觸發抖動
- **狀態保持**：讀取失敗時保持現有告警狀態，不會錯誤清除告警
- **事件通知**：狀態變化時回傳 `AlarmEvent`（`TRIGGERED` 或 `CLEARED`）

---

## 主要方法

| 方法 | 說明 |
|------|------|
| `register_alarm(alarm)` | 註冊單一告警定義 |
| `register_alarms(alarms)` | 批量註冊告警定義（重複代碼會拋出 `KeyError`） |
| `update(evaluations)` | 更新告警狀態，回傳狀態變化的 `AlarmEvent` 列表 |
| `clear_alarm(code)` | 強制清除指定告警 |
| `get_active_alarms()` | 取得所有啟用中的告警狀態列表 |
| `get_state(code)` | 取得特定告警的狀態 |
| `has_protection_alarm()` | 檢查是否存在 `ALARM` 等級的告警 |
| `reset()` | 重置所有告警狀態 |
| `export_states()` | 匯出所有告警狀態的 shallow copy（`dict[str, AlarmState]`） |
| `import_states(states)` | 匯入告警狀態，對已存在的告警代碼覆蓋其計數與時間欄位 |

### export_states() / import_states()

這兩個方法用於 `AsyncModbusDevice.reconfigure()` 的告警狀態遷移流程，確保替換告警評估器時，相同告警代碼的歷史狀態不會遺失。

```python
# 典型使用場景（由 reconfigure() 內部呼叫）
old_states = manager.export_states()

# 建立新的 AlarmStateManager 並註冊新的告警定義
new_manager = AlarmStateManager()
for evaluator in new_evaluators:
    new_manager.register_alarms(evaluator.get_alarms())

# 將舊狀態還原到新管理器（僅更新兩邊都有的告警代碼）
new_manager.import_states(old_states)
```

> [!note] import_states 行為
> - 僅對**已在新管理器中註冊**的告警代碼有效
> - 新增的告警代碼（舊管理器不存在）從零狀態開始
> - 舊管理器中存在但新管理器不再有的告警代碼，其狀態被丟棄

---

## AlarmState

每個已註冊的告警都有一個 `AlarmState` 物件追蹤其狀態：

| 屬性 | 型別 | 說明 |
|------|------|------|
| `definition` | `AlarmDefinition` | 告警定義 |
| `is_active` | `bool` | 是否啟用中 |
| `activate_count` | `int` | 連續觸發次數 |
| `clear_count` | `int` | 連續解除次數 |
| `activated_at` | `datetime \| None` | 告警啟用時間 |
| `cleared_at` | `datetime \| None` | 告警清除時間 |
| `duration` | `float \| None` | 告警持續時間（秒） |

---

## AlarmEvent

狀態變化時產生的事件：

| 屬性 | 型別 | 說明 |
|------|------|------|
| `event_type` | `AlarmEventType` | `TRIGGERED` 或 `CLEARED` |
| `alarm` | `AlarmDefinition` | 告警定義 |
| `timestamp` | `datetime` | 事件時間（UTC） |

---

## 相關頁面

- [[AlarmDefinition]] -- 告警定義與遲滯設定
- [[Alarm Evaluators]] -- 告警評估器
- [[AsyncModbusDevice]] -- 核心設備類別
- [[_MOC Equipment]] -- 設備模組總覽
