---
tags: [type/guide, status/complete]
updated: 2026-04-04
version: ">=0.4.2"
---
# Tag Taxonomy

> 標籤分類法

## 層級標籤 (Layer)

| 標籤 | 對應模組 |
|------|---------|
| `#layer/core` | `csp_lib.core` |
| `#layer/modbus` | `csp_lib.modbus` |
| `#layer/equipment` | `csp_lib.equipment` |
| `#layer/controller` | `csp_lib.controller` |
| `#layer/integration` | `csp_lib.integration` |
| `#layer/manager` | `csp_lib.manager` |
| `#layer/storage` | `csp_lib.mongo` + `csp_lib.redis` |
| `#layer/cluster` | `csp_lib.cluster` |
| `#layer/monitor` | `csp_lib.monitor` |
| `#layer/notification` | `csp_lib.notification` |
| `#layer/modbus-server` | `csp_lib.modbus_server` |

## 類型標籤 (Type)

| 標籤 | 說明 |
|------|------|
| `#type/class` | 類別頁面 |
| `#type/protocol` | Protocol / ABC 介面 |
| `#type/enum` | 列舉 |
| `#type/config` | 設定類別 |
| `#type/guide` | 使用教學 |
| `#type/reference` | 參考索引 |
| `#type/moc` | Map of Content 索引頁 |
| `#type/concept` | 概念說明 |

## 狀態標籤 (Status)

| 標籤 | 說明 |
|------|------|
| `#status/draft` | 草稿 |
| `#status/complete` | 完成 |
| `#status/stale` | 超過 2 個版本未更新 |

## 元資料欄位 (Metadata Fields)

| 欄位 | 格式 | 說明 |
|------|------|------|
| `updated:` | `YYYY-MM-DD` | 最後更新日期 |
| `version:` | `">=X.Y.Z"` | 此頁面適用的最低版本 |

所有文件的 frontmatter 應包含 `updated` 和 `version` 欄位，以便追蹤文件新鮮度與版本適用性。

## 查詢範例

```dataview
LIST
FROM #layer/equipment AND #type/class
SORT file.name ASC
```
