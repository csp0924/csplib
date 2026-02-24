---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/device/base.py
---

# AsyncModbusDevice

> 核心設備類別

`AsyncModbusDevice` 是 csp_lib 程式庫的**核心類別**，提供完整的非同步 Modbus 設備抽象。整合讀寫操作、告警管理、事件驅動通知與動態點位排程。

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
# 讀取所有點位
values = await device.read_all()
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

---

## 事件系統

| 事件名稱 | Payload | 說明 |
|---------|---------|------|
| `connected` | `ConnectedPayload` | 連線成功/恢復 |
| `disconnected` | `DisconnectPayload` | 斷線 |
| `read_complete` | `ReadCompletePayload` | 讀取完成 |
| `read_error` | `ReadErrorPayload` | 讀取錯誤 |
| `value_change` | `ValueChangePayload` | 值變化 |
| `write_complete` | `WriteCompletePayload` | 寫入成功 |
| `write_error` | `WriteErrorPayload` | 寫入失敗 |
| `alarm_triggered` | `DeviceAlarmPayload` | 告警觸發 |
| `alarm_cleared` | `DeviceAlarmPayload` | 告警解除 |

### 註冊事件處理器

```python
# 註冊處理器
cancel = device.on("value_change", async_handler)
cancel()  # 取消訂閱
```

---

## 內部元件

`AsyncModbusDevice` 內部整合以下元件：

- [[PointGrouper]] -- 自動分組點位
- [[ReadScheduler]] -- 管理固定與輪替讀取排程
- [[GroupReader]] -- 執行批次讀取與解碼
- [[ValidatedWriter]] -- 執行驗證寫入
- [[AlarmStateManager]] -- 管理告警狀態

---

## ACTIONS 映射

子類別可覆寫 `ACTIONS` 類別屬性，定義動作名稱到方法名稱的映射：

```python
class MyInverter(AsyncModbusDevice):
    ACTIONS = {
        "start": "set_generator_on",
        "stop": "set_generator_off",
    }
```

---

## 相關頁面

- [[DeviceConfig]] -- 設備設定參數
- [[DeviceEventEmitter]] -- 事件發射器
- [[ReadScheduler]] -- 讀取排程器
- [[GroupReader]] -- 群組讀取器
- [[ValidatedWriter]] -- 驗證寫入器
- [[AlarmStateManager]] -- 告警狀態管理
- [[_MOC Equipment]] -- 設備模組總覽
