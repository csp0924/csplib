---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
updated: 2026-04-04
version: ">=0.4.2"
---

# 所有設備事件

[[AsyncModbusDevice]] 與 [[AsyncCANDevice]]（v0.4.2）透過 [[DeviceEventEmitter]] 發射的所有事件列表。兩種設備共用同一套事件系統。

## 事件總覽

| 事件名稱 | Payload 型別 | 說明 |
|---------|-------------|------|
| `connected` | `ConnectedPayload` | 連線成功或恢復 |
| `disconnected` | `DisconnectPayload` | 斷線 |
| `read_complete` | `ReadCompletePayload` | 讀取完成 |
| `read_error` | `ReadErrorPayload` | 讀取錯誤 |
| `value_change` | `ValueChangePayload` | 值變化 |
| `write_complete` | `WriteCompletePayload` | 寫入成功 |
| `write_error` | `WriteErrorPayload` | 寫入失敗 |
| `alarm_triggered` | `DeviceAlarmPayload` | 告警觸發 |
| `alarm_cleared` | `DeviceAlarmPayload` | 告警解除 |

---

## 事件用法

### 註冊事件處理器

```python
# 同步處理器
device.on("value_change", lambda p: print(f"{p.point_name}: {p.new_value}"))

# 非同步處理器
async def handler(payload):
    await process(payload)

device.on("read_complete", handler)
```

### 取消訂閱

```python
cancel = device.on("value_change", handler)
cancel()  # 呼叫返回值即可取消訂閱
```

---

## Payload 詳細說明

### ConnectedPayload

設備連線成功時觸發。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |

### DisconnectPayload

設備斷線時觸發。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `reason` | `str` | 斷線原因 |

### ReadCompletePayload

完成一次完整讀取週期時觸發。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `values` | `dict[str, Any]` | 所有點位的讀取值 |

### ReadErrorPayload

讀取發生錯誤時觸發。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `error` | `str` | 錯誤訊息 |

### ValueChangePayload

點位值發生變化時觸發。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `point_name` | `str` | 點位名稱 |
| `old_value` | `Any` | 舊值 |
| `new_value` | `Any` | 新值 |

### WriteCompletePayload

寫入成功時觸發。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `point_name` | `str` | 點位名稱 |
| `value` | `Any` | 寫入值 |

### WriteErrorPayload

寫入失敗時觸發。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `point_name` | `str` | 點位名稱 |
| `error` | `str` | 錯誤訊息 |

### DeviceAlarmPayload

告警觸發或解除時觸發。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `device_id` | `str` | 設備 ID |
| `alarm_code` | `str` | 告警代碼 |
| `alarm_name` | `str` | 告警名稱 |
| `level` | `AlarmLevel` | 告警等級 |

---

## CAN 設備事件補充（v0.4.2）

[[AsyncCANDevice]] 的事件含義與 AsyncModbusDevice 相同，但觸發時機略有差異：

| 事件 | AsyncModbusDevice 觸發時機 | AsyncCANDevice 觸發時機 |
|------|--------------------------|----------------------|
| `connected` | TCP/RTU 連線建立 | CAN Bus 連線建立 |
| `disconnected` | 連線中斷 | Bus 連線中斷 |
| `read_complete` | 週期讀取排程完成 | CAN RX 幀接收並解析 |
| `write_complete` | 暫存器寫入確認 | CAN TX 幀發送成功 |

---

## 相關頁面

- [[Device Setup]] - 設備設定指南
- [[AsyncModbusDevice]] - Modbus 設備類別
- [[AsyncCANDevice]] - CAN 設備類別（v0.4.2）
- [[DeviceEventEmitter]] - 事件發射器
- [[Event System]] - 事件系統架構說明
