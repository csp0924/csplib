---
tags:
  - type/class
  - layer/integration
  - status/complete
source: csp_lib/integration/data_feed.py
---

# DeviceDataFeed

設備事件 → PVDataService 資料餵入，隸屬於 [[_MOC Integration|Integration 模組]]。

## 概述

`DeviceDataFeed` 訂閱單一設備的 `read_complete` 事件，將指定點位的 PV 功率值餵入 `PVDataService`。透過 [[DataFeedMapping]] 指定目標設備。

### 設備解析模式

- **device_id 模式**：直接查詢指定設備
- **trait 模式**：取第一台 responsive 設備

### 設計備註

實作與 [[DeviceEventSubscriber]] 相同的 subscribe/unsubscribe 模式，但不繼承該類別以避免 import `csp_lib.manager`（其 `__init__` 會載入可選依賴 motor）。

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `registry` | [[DeviceRegistry]] | 設備查詢索引 |
| `mapping` | [[DataFeedMapping]] | PV 資料來源映射 |
| `pv_service` | `PVDataService` | PV 資料服務實例 |

## API

| 方法 | 說明 |
|------|------|
| `attach()` | 解析目標設備並訂閱 `read_complete` 事件 |
| `detach()` | 取消訂閱當前設備的事件 |

## 值處理規則

- 數值型（`int` / `float`）→ `pv_service.append(float(value))`
- 非數值或缺失 → `pv_service.append(None)`

## 相關頁面

- [[DataFeedMapping]] — 映射定義
- [[DeviceRegistry]] — 設備查詢索引
- [[GridControlLoop]] — 自動管理 DeviceDataFeed 的 attach/detach
- [[SystemController]] — 自動管理 DeviceDataFeed 的 attach/detach
