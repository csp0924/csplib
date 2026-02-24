---
tags:
  - type/class
  - layer/controller
  - status/complete
source: csp_lib/controller/services/pv_data_service.py
created: 2026-02-17
---

# PVDataService

PV 功率資料服務，收集並維護 PV 功率歷史資料。

> [!info] 回到 [[_MOC Controller]]

## 概述

PVDataService 使用 `collections.deque` 維護固定長度的歷史資料佇列，供 [[PVSmoothStrategy]] 等策略使用。透過建構子注入策略，確保策略切換時資料不遺失。外部 loop 定期呼叫 `append()` 新增資料。

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `max_history` | `int` | `300` | 最大歷史筆數 (必須 >= 1) |

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `max_history` | `int` | 最大歷史筆數 |
| `count` | `int` | 目前資料筆數 (含 None) |

## 方法

| 方法 | 回傳 | 說明 |
|------|------|------|
| `append(power)` | `None` | 新增一筆 PV 功率資料，可為 None 表示讀取失敗 |
| `get_history()` | `list[float]` | 取得有效的歷史資料 (過濾 None) |
| `get_latest()` | `Optional[float]` | 取得最新一筆有效資料 |
| `get_average()` | `Optional[float]` | 計算有效資料的平均值 |
| `clear()` | `None` | 清空所有歷史資料 |

## 程式碼範例

```python
from csp_lib.controller import PVDataService

pv_service = PVDataService(max_history=300)
pv_service.append(500.0)        # Add data point
avg = pv_service.get_average()  # Get average
latest = pv_service.get_latest() # Get latest valid data
```

## 設計備註

- 使用 `deque(maxlen=max_history)` 自動移除最舊資料
- `append(None)` 表示讀取失敗，`get_history()` 和 `get_average()` 會自動過濾 None
- `__len__` 回傳有效資料筆數 (不含 None)，`count` 回傳全部筆數 (含 None)

## 相關連結

- [[PVSmoothStrategy]] — 使用 PVDataService 取得歷史功率
- [[_MOC Controller]] — 回到模組總覽
