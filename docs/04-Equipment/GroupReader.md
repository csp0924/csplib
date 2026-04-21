---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/transport/reader.py
updated: 2026-04-22
version: ">=0.9.0"
---

# GroupReader

> 群組讀取器

`GroupReader` 負責執行 Modbus 讀取並解碼 [[PointGrouper]] 產生的 `ReadGroup` 資料。支援串列與並行兩種讀取模式。

---

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `client` | `AsyncModbusClientBase` | (必填) | Modbus 客戶端 |
| `unit_id` | `int` | `1` | 設備 fallback unit_id；`ReadGroup.unit_id` 若非 None 則覆寫（v0.9.0+） |
| `address_offset` | `int` | `0` | 位址偏移（PLC 1-based 定址時設為 1） |
| `max_concurrent_reads` | `int` | `1` | 最大並行讀取數（>= 1） |

### 並行讀取建議

- **TCP client**：可設定 `max_concurrent_reads=3`，同時發送多個請求
- **SharedTCP / RTU client**：保持 `max_concurrent_reads=1`，串列讀取

### Per-unit_id 序列化（v0.9.0+）

`GroupReader` 對每個 `unit_id` 獨立維護 semaphore：

- **同 unit_id** 請求：永遠串列（保護單一 slave，避免被自己的 in-flight 請求打爆）
- **跨 unit_id** 請求：可並行（仍受 `max_concurrent_reads` 全域上限）

語義上先取 per-unit semaphore 再取全域 semaphore，避免同一 unit_id 的大量請求
占用全域額度而擠掉其他 unit_id。詳見 [[Multi-UnitID Device]]。

---

## 主要方法

| 方法 | 說明 |
|------|------|
| `read(group)` | 讀取單一群組並解碼，回傳 `{點位名稱: 值}` |
| `read_many(groups)` | 讀取多個群組並合併結果 |

---

## 解碼流程

1. 根據 `function_code` 呼叫對應的 Modbus 讀取函數
2. 從原始資料中按 `address` 偏移提取每個點位的資料切片
3. 呼叫 `data_type.decode()` 解碼暫存器值
4. 若點位有 `pipeline`，執行 `pipeline.process()` 進行轉換

---

## Quick Example

```python
from csp_lib.equipment.transport import GroupReader, PointGrouper

grouper = PointGrouper()
groups = grouper.group(points)

reader = GroupReader(client=client, address_offset=0)
data = await reader.read_many(groups)
# -> {"voltage": 220.5, "temperature": 25.3}
```

---

> [!note] v0.7.2 並行讀取 partial failure 修復（SEC-016）
> `read_many()` 並行模式（`max_concurrent_reads > 1`）改用 `asyncio.gather(..., return_exceptions=True)` 並逐結果檢查。
> - 單一群組讀取失敗（`Exception`）：記錄 warning 並跳過，其他成功結果正常回傳
> - `BaseException`（`CancelledError` / `SystemExit` / `KeyboardInterrupt`）：正常 re-raise，不被吞掉
>
> 修復前：任何群組失敗都使整批 `latest_values` 不更新，控制策略被迫基於陳舊資料決策。

## 相關頁面

- [[PointGrouper]] -- 點位分組器
- [[_MOC Equipment]] -- 設備模組總覽
