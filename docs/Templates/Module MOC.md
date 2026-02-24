---
tags: [type/moc, layer/<LAYER>, status/draft]
---
# _MOC ModuleName

> 模組一行說明

## 概述

模組簡述。

## 頁面索引

### 核心類別
- [[ClassName]]

### 輔助類別
- [[HelperClass]]

## Dataview 索引

```dataview
TABLE source AS "原始碼", tags AS "標籤"
FROM "XX-ModuleName"
WHERE contains(tags, "type/class")
SORT file.name ASC
```

## 相關模組

- 上游：[[_MOC UpstreamModule]]
- 下游：[[_MOC DownstreamModule]]
