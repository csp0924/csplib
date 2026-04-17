---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/device/base.py
updated: 2026-04-17
version: ">=0.8.0"
---

# AsyncModbusDevice

> 核心設備類別

`AsyncModbusDevice` 是 csp_lib 程式庫的**核心類別**，提供完整的非同步 Modbus 設備抽象。整合讀寫操作、告警管理、事件驅動通知、動態點位排程，以及執行期動態重新配置能力。

---

## 建構參數

```python
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig

device = AsyncModbusDevice(
    config=DeviceConfig(
        device_id="inverter_001",
        unit_id=1,
        address_offset=0,        # PLC 1-based: set to 1
        read_interval=1.0,       # 讀取間隔（秒）
        reconnect_interval=5.0,  # 重連間隔（秒）
        disconnect_threshold=5,  # 連續失敗次數閾值
        max_concurrent_reads=1,  # 最大並行讀取數（0=不限制）
    ),
    client=client,
    always_points=read_points,
    rotating_points=[group_a, group_b],
    write_points=write_points,
    alarm_evaluators=[bitmask, threshold],
)
```

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | `DeviceConfig` | 設備設定（詳見 [[DeviceConfig]]） |
| `client` | `AsyncModbusClientBase` | Modbus 客戶端 |
| `always_points` | `Sequence[ReadPoint]` | 每次都讀取的點位 |
| `rotating_points` | `Sequence[Sequence[ReadPoint]]` | 輪替讀取的點位群組 |
| `write_points` | `Sequence[WritePoint]` | 寫入點位 |
| `alarm_evaluators` | `Sequence[AlarmEvaluator]` | 告警評估器 |
| `aggregator_pipeline` | `AggregatorPipeline \| None` | 聚合器管線 |
| `capability_bindings` | `Sequence[CapabilityBinding]` | 能力綁定（預設空） |

---

## 生命週期

### Context Manager（推薦）

```python
async with device:
    ...  # auto connect + start, auto stop + disconnect
```

### 手動管理

```python
await device.connect()
await device.start()
...
await device.stop()
await device.disconnect()
```

生命週期方法：

| 方法 | 說明 |
|------|------|
| `connect()` | 連線設備，啟動事件 worker |
| `disconnect()` | 斷線設備，停止事件 worker |
| `start()` | 啟動定期讀取循環 |
| `stop()` | 停止定期讀取循環 |
| `restart()` | 重啟讀取迴圈（stop + start），發出 `restarted` 事件 |
| `read_once()` | 執行一次完整讀取流程（含自動重連、告警評估） |

---

## 狀態屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `is_connected` | `bool` | Socket 層級連線狀態 |
| `is_responsive` | `bool` | 設備通訊回應狀態 |
| `is_healthy` | `bool` | 健康（connected + responsive + 無保護告警） |
| `is_protected` | `bool` | 是否有保護告警 |
| `is_running` | `bool` | 讀取循環是否運行中 |
| `latest_values` | `dict` | 最新讀取值字典 |
| `active_alarms` | `list` | 目前啟用的告警列表 |
| `device_id` | `str` | 設備 ID |

---

## 讀寫操作

### 讀取

```python
# 執行一次完整讀取（含自動重連、告警評估）
values = await device.read_once()
# -> {"voltage": 220.5, "temperature": 25.3}
```

### 寫入

```python
from csp_lib.equipment.transport import WriteStatus

result = await device.write("power_limit", 5000, verify=True)
if result.status == WriteStatus.SUCCESS:
    print("Success")
elif result.status == WriteStatus.VERIFICATION_FAILED:
    print(f"Readback mismatch: {result.error_message}")
```

> [!note] 停用點位保護
> 對已停用（`disable_point()`）的點位執行寫入操作將被拒絕，`WriteStatus` 會回傳 `VALIDATION_FAILED`。

### NaN/Inf 拒絕（reject_non_finite，v0.8.0）

`ReadPoint.reject_non_finite = True` 時，`AsyncModbusDevice` 在讀到非有限 float（NaN / +Inf / -Inf）時：

1. **保留** `latest_values[point_name]` 舊值
2. **發 WARNING log**（含 device_id、point 名稱、非法值）
3. **不觸發** `value_change` 事件
4. **不送入** 告警評估，`read_once()` 回傳 `effective_values`（reject 的值替換為舊值）

> [!tip] 使用場景
> 設定在「物理量有界」的 point（SOC、電壓、電流），防止通訊瞬態的 NaN/Inf 污染保護邏輯。
> 電表 fault code 以 NaN 表達不同 fault 情況時，**不應啟用**此選項（NaN 是合法語義）。
> 
> 詳見 [[ReadPoint]] — `reject_non_finite` 欄位說明。

### ACTIONS 高階動作

```python
result = await device.execute_action("start", p=5000)
print(device.available_actions)  # ["start", "stop"]
```

### DO 動作

> [!info] v0.6.0 新增

透過 `WriteMixin` 整合結構化的 DO 動作控制，詳見 [[DOActions]]。

| 方法 / 屬性 | 說明 |
|------------|------|
| `configure_do_actions(configs)` | 配置 DO 動作列表 |
| `available_do_actions` | 取得已配置的 `DOActionConfig` 列表 |
| `execute_do_action(label, *, turn_off=False)` | 執行 DO 動作（`WriteResult`） |
| `cancel_pending_pulses()` | 取消所有 PULSE 任務（`stop()` 時自動呼叫） |

```python
from csp_lib.equipment.device.action import DOMode, DOActionConfig

device.configure_do_actions([
    DOActionConfig(point_name="do_trip", label="trip", mode=DOMode.PULSE, pulse_duration=0.3),
    DOActionConfig(point_name="do_contactor", label="contactor", mode=DOMode.SUSTAINED),
])
await device.execute_do_action("trip")
await device.execute_do_action("contactor", turn_off=True)
```

---

## 點位查詢 API

| 屬性 / 方法 | 型別 | 說明 |
|------------|------|------|
| `read_points` | `tuple[ReadPoint, ...]` | 所有固定讀取點位 |
| `rotating_read_points` | `tuple[tuple[ReadPoint, ...], ...]` | 所有輪替讀取點位群組 |
| `write_point_names` | `list[str]` | 所有寫入點位名稱 |
| `all_point_names` | `set[str]` | 所有點位名稱（讀 + 寫） |
| `disabled_points` | `frozenset[str]` | 目前被停用的點位名稱集合 |
| `get_point_info()` | `list[PointInfo]` | 所有點位的詳細資訊（含啟用狀態、方向等） |

### PointInfo

`get_point_info()` 回傳 `list[PointInfo]`，每個 `PointInfo` 是 frozen dataclass：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `name` | `str` | 點位名稱 |
| `address` | `int` | Modbus 暫存器地址 |
| `data_type` | `ModbusDataType` | 資料型別 |
| `direction` | `str` | `"read"` / `"write"` / `"read_write"` |
| `enabled` | `bool` | 是否啟用中 |
| `read_group` | `str` | 所屬讀取群組名稱（僅寫入點位為空字串） |
| `metadata` | `PointMetadata \| None` | 點位附加詮釋資料 |

```python
for info in device.get_point_info():
    status = "ON" if info.enabled else "OFF"
    print(f"{info.name} [{info.direction}] {status}")
```

---

## 點位開關

允許在不停止設備的情況下，動態停用或啟用個別點位。

| 方法 | 說明 |
|------|------|
| `enable_point(name)` | 啟用點位，發出 `point_toggled` 事件（`enabled=True`） |
| `disable_point(name)` | 停用點位，發出 `point_toggled` 事件（`enabled=False`） |
| `is_point_enabled(name)` | 回傳點位是否啟用（`bool`） |

> [!warning] 停用點位的行為
> - Modbus 暫存器仍照常讀取（節省重配置開銷）
> - `_process_values()` 跳過停用點位，`latest_values` 不更新
> - 告警評估跳過停用點位
> - 對停用點位的寫入被拒絕
> - `reconfigure()` 後，不再存在的停用點位自動清除

```python
# 暫時停用某個感測器點位
device.disable_point("temp_sensor_2")

# 稍後重新啟用
device.enable_point("temp_sensor_2")

# 查詢所有停用點位
print(device.disabled_points)  # frozenset{"temp_sensor_2"}
```

---

## 動態重新配置

`reconfigure(spec)` 允許在執行期替換點位定義，無需重建設備物件。

### ReconfigureSpec

`ReconfigureSpec` 是 frozen dataclass，所有欄位預設為 `None`（保持不變）：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `always_points` | `Sequence[ReadPoint] \| None` | 新的固定讀取點位 |
| `rotating_points` | `Sequence[Sequence[ReadPoint]] \| None` | 新的輪替讀取點位群組 |
| `write_points` | `Sequence[WritePoint] \| None` | 新的寫入點位 |
| `alarm_evaluators` | `Sequence[AlarmEvaluator] \| None` | 新的告警評估器 |
| `capability_bindings` | `Sequence[CapabilityBinding] \| None` | 新的能力綁定 |

### reconfigure() 執行流程

```
1. 若讀取迴圈正在運行 → stop()
2. 替換 spec 中非 None 的組件
3. 若更新 alarm_evaluators → export_states() 保留告警狀態 → 重建管理器 → import_states()
4. 清理不再存在的 disabled_points
5. 若原本在運行 → start()
6. 發出 reconfigured 事件（含 changed_sections）
```

```python
from csp_lib.equipment.device import ReconfigureSpec

# 僅替換告警評估器，保留其他點位定義不變
spec = ReconfigureSpec(
    alarm_evaluators=[new_threshold_evaluator, new_bitmask_evaluator],
)
await device.reconfigure(spec)

# 完整重新配置（替換讀取點位 + 寫入點位）
full_spec = ReconfigureSpec(
    always_points=new_core_points,
    rotating_points=[new_group_a, new_group_b],
    write_points=new_write_points,
)
await device.reconfigure(full_spec)
```

> [!note] 告警狀態保留
> 替換 `alarm_evaluators` 時，透過 `AlarmStateManager.export_states()` / `import_states()` 保留相同 alarm code 的計數與時間狀態。新增的告警代碼從零開始；已移除的告警代碼狀態丟棄。

---

## 事件系統

| 事件名稱 | 常數 | Payload | 說明 |
|---------|------|---------|------|
| `connected` | `EVENT_CONNECTED` | `ConnectedPayload` | 連線成功/恢復 |
| `disconnected` | `EVENT_DISCONNECTED` | `DisconnectPayload` | 斷線 |
| `read_complete` | `EVENT_READ_COMPLETE` | `ReadCompletePayload` | 讀取完成 |
| `read_error` | `EVENT_READ_ERROR` | `ReadErrorPayload` | 讀取錯誤 |
| `value_change` | `EVENT_VALUE_CHANGE` | `ValueChangePayload` | 值變化 |
| `write_complete` | `EVENT_WRITE_COMPLETE` | `WriteCompletePayload` | 寫入成功 |
| `write_error` | `EVENT_WRITE_ERROR` | `WriteErrorPayload` | 寫入失敗 |
| `alarm_triggered` | `EVENT_ALARM_TRIGGERED` | `DeviceAlarmPayload` | 告警觸發 |
| `alarm_cleared` | `EVENT_ALARM_CLEARED` | `DeviceAlarmPayload` | 告警解除 |
| `reconfigured` | `EVENT_RECONFIGURED` | `ReconfiguredPayload` | 動態重新配置完成 |
| `restarted` | `EVENT_RESTARTED` | `RestartedPayload` | 讀取迴圈重啟 |
| `point_toggled` | `EVENT_POINT_TOGGLED` | `PointToggledPayload` | 點位啟用/停用 |

### 新增 Payload 類別（v0.4.2）

**ReconfiguredPayload**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `changed_sections` | `tuple[str, ...]` | 已變更的組件名稱列表 |
| `timestamp` | `datetime` | 事件時間（UTC） |

**RestartedPayload**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `timestamp` | `datetime` | 事件時間（UTC） |

**PointToggledPayload**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `point_name` | `str` | 被切換的點位名稱 |
| `enabled` | `bool` | 切換後的啟用狀態 |
| `timestamp` | `datetime` | 事件時間（UTC） |

### 註冊事件處理器

```python
# 監聽重新配置事件
async def on_reconfigured(payload: ReconfiguredPayload):
    print(f"設備 {payload.device_id} 已重新配置: {payload.changed_sections}")

cancel = device.on("reconfigured", on_reconfigured)
cancel()  # 取消訂閱
```

---

> [!note] v0.7.2 _read_loop 絕對時間錨定（WI-TD-103）
> `_read_loop` 改採 work-first 絕對時間錨定（`next_tick_delay()`），sleep delay 補償每次讀取的實際耗時，消除累積時序漂移。
> - Reconnect 成功後重設 anchor，避免重連瞬間 burst catch-up 壓垮設備
> - 落後超過一個 interval 時自動重設 anchor

## 內部元件

`AsyncModbusDevice` 內部整合以下元件：

- [[PointGrouper]] -- 自動分組點位
- [[ReadScheduler]] -- 管理固定與輪替讀取排程（支援動態更新）
- [[GroupReader]] -- 執行批次讀取與解碼
- [[ValidatedWriter]] -- 執行驗證寫入
- [[AlarmStateManager]] -- 管理告警狀態（支援匯出/匯入）

---

## ACTIONS 映射

子類別可覆寫 `ACTIONS` 類別屬性，定義動作名稱到方法名稱的映射：

```python
class MyInverter(AsyncModbusDevice):
    ACTIONS = {
        "start": "set_generator_on",
        "stop": "set_generator_off",
    }

# 透過 execute_action 呼叫
result = await inverter.execute_action("start")
```

---

## 能力系統

> [!info] v0.5.0 新增

透過 `Capability` + `CapabilityBinding` 實現語意插槽到實際點位的映射，讓 Controller 層不需關心具體點位名稱。

| 方法 / 屬性 | 說明 |
|------------|------|
| `capabilities` | 所有已綁定的能力（`dict[str, CapabilityBinding]`） |
| `has_capability(cap)` | 檢查是否具備指定能力 |
| `get_binding(cap)` | 取得能力綁定（不存在回傳 `None`） |
| `resolve_point(cap, slot)` | 解析語意插槽到實際點位名稱 |
| `add_capability(binding)` | 動態新增能力綁定 |
| `remove_capability(cap)` | 動態移除能力綁定 |

```python
from csp_lib.equipment.device.capability import ACTIVE_POWER_CONTROL, CapabilityBinding

binding = CapabilityBinding(ACTIVE_POWER_CONTROL, {"p_setpoint": "power_cmd", "p_measurement": "active_power"})
device.add_capability(binding)

point_name = device.resolve_point(ACTIVE_POWER_CONTROL, "p_setpoint")
# -> "power_cmd"
```

---

## 健康檢查

```python
report = device.health()
# HealthReport(status=HEALTHY, component="device:inverter_001", details={...})
```

| 狀態 | 條件 |
|------|------|
| `HEALTHY` | connected + responsive + 無保護告警 |
| `DEGRADED` | connected 但 unresponsive 或有保護告警 |
| `UNHEALTHY` | disconnected |

---

## 相關頁面

- [[DeviceProtocol]] -- 設備通用協定（Modbus / CAN 共用介面）
- [[AsyncCANDevice]] -- CAN Bus 設備（平行實作）
- [[DeviceConfig]] -- 設備設定參數
- [[DeviceEventEmitter]] -- 事件發射器（含 12 種事件類型）
- [[DOActions]] -- DO 動作抽象（v0.6.0）
- [[ReadScheduler]] -- 讀取排程器（含動態更新）
- [[GroupReader]] -- 群組讀取器
- [[ValidatedWriter]] -- 驗證寫入器
- [[AlarmStateManager]] -- 告警狀態管理（含匯出/匯入）
- [[_MOC Equipment]] -- 設備模組總覽
