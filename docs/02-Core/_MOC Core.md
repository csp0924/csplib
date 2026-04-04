---
tags: [type/moc, layer/core, status/complete]
updated: 2026-04-04
version: v0.6.1
---
# _MOC Core

> 核心基礎設施模組 (`csp_lib.core`)

## 概述

提供日誌、生命週期管理、統一錯誤階層、健康檢查等基礎功能，為所有上層模組的共用基底。

## 頁面索引

- [[Logging]] — 基於 loguru 的模組化日誌系統
- [[AsyncLifecycleMixin]] — 非同步生命週期管理基底
- [[Error Hierarchy]] — 統一例外階層
- [[Health Check]] — 健康狀態檢查
- [[Resilience]] — 斷路器（CircuitBreaker）與重試策略（RetryPolicy）
- [[RuntimeParameters]] — Thread-safe 即時參數容器

## Dataview 索引

```dataview
TABLE source AS "原始碼"
FROM "02-Core"
WHERE contains(tags, "type/class") OR contains(tags, "type/concept")
SORT file.name ASC
```

## 相關模組

- 下游：[[_MOC Modbus]]、[[_MOC Equipment]]、[[_MOC Controller]]
