---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/core/point.py
created: 2026-02-17
updated: 2026-04-22
version: ">=0.9.0"
---

# ReadPoint

> 讀取點位定義

`ReadPoint` 繼承自 `PointDefinition`，是不可變的 frozen dataclass，用於定義 Modbus 設備的讀取點位。每個 ReadPoint 對應一個暫存器位址，並可附加資料處理管線。

---

## 參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `name` | `str` | (必填) | 點位名稱（唯一識別） |
| `address` | `int` | (必填) | Modbus 暫存器位址 |
| `data_type` | `ModbusDataType` | (必填) | 資料類型（來自 `csp_lib.modbus`） |
| `function_code` | `FunctionCode \| None` | `READ_HOLDING_REGISTERS` | Modbus 功能碼（`__post_init__` 自動補填） |
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 位元組順序 |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 暫存器順序 |
| `pipeline` | `ProcessingPipeline \| None` | `None` | 資料處理管線 |
| `read_group` | `str` | `""` | 讀取分組名稱（空字串參與自動合併） |
| `metadata` | `PointMetadata \| None` | `None` | 點位元資料（單位、描述） |
| `reject_non_finite` | `bool` | `False` | v0.8.0+：True 時 NaN/Inf 視為無效，保留舊值並 log WARNING |
| `unit_id` | `int \| None` | `None` | v0.9.0+：此點位送往的 Modbus unit_id。`None` 沿用 `DeviceConfig.unit_id`；設值覆寫至 0-255 |

---

## Quick Example

```python
from csp_lib.equipment.core import ReadPoint
from csp_lib.modbus import Float32, FunctionCode

# 基本用法
point = ReadPoint(
    name="voltage",
    address=0,
    data_type=Float32(),
    function_code=FunctionCode.READ_HOLDING_REGISTERS,  # default
    pipeline=None,
    read_group="",
)

# v0.8.0+：啟用 NaN/Inf 拒絕（針對「此設備絕不應回傳 NaN」的 point）
soc_point = ReadPoint(
    name="soc",
    address=100,
    data_type=Float32(),
    reject_non_finite=True,  # 讀到 NaN 保留舊值，不觸發 value_change
)
```

---

## reject_non_finite（v0.8.0）

當 `reject_non_finite=True` 時，若 `AsyncModbusDevice` 本次讀取的解碼值為非有限 float（NaN / +Inf / -Inf）：

1. **保留** `_latest_values[name]` 中的上一次有效值（不覆寫）
2. **發出** WARNING log（含 device_id、point 名稱、非法值）
3. **不觸發** `value_change` 事件
4. **不送入** 告警評估（`_evaluate_alarm`）
5. **不出現在** `EVENT_READ_COMPLETE` payload 與 `read_once()` 回傳（使用 `effective_values`，reject 的值替換為 last_value）

> [!note] 設計用途
> 此功能是 SEC-013b 防禦的裝置端入口：對明確不應出現非有限值的 point（如 SOC、電壓），啟用此選項可防止通訊瞬態的 NaN/Inf 污染保護邏輯或策略上下文。
> 預設 `False` 維持 IEEE 754 permissive 行為（保留合法 NaN/Inf sentinel，如電表 fault 信號），由 L6 ContextBuilder 的 `math.isfinite()` 過濾（SEC-013a）。

---

## Common Patterns

### 與 ContextBuilder 的配合

`reject_non_finite=True` 的 point 遇到 NaN 時，`latest_values` 保留上次有效值。`ContextBuilder` 讀取 `latest_values` 時看到的仍是有效數值，不需額外處理。

### 啟用時機

- SOC、電壓、電流等「物理量有界」的 point — 適合啟用
- 電表 fault code（以 NaN 表達不同 fault）— 不應啟用（NaN 是合法語義）

---

## 相關頁面

- [[WritePoint]] — 寫入點位定義
- [[ProcessingPipeline]] — 資料處理管線
- [[AsyncModbusDevice]] — 使用 `reject_non_finite` 的設備層實作
- [[ContextBuilder]] — L6 層的 `math.isfinite()` 過濾（SEC-013a）
- [[_MOC Equipment]] — 設備模組總覽
