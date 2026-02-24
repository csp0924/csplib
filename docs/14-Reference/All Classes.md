---
tags:
  - type/reference
  - status/complete
created: 2026-02-17
---

# 所有類別

使用 Dataview 動態查詢所有標記為 `type/class` 的頁面。

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class")
SORT file.name ASC
```

---

## 依模組分類

### Core

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/core")
SORT file.name ASC
```

### Modbus

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/modbus")
SORT file.name ASC
```

### Equipment

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/equipment")
SORT file.name ASC
```

### Controller

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/controller")
SORT file.name ASC
```

### Manager

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/manager")
SORT file.name ASC
```

### Integration

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/integration")
SORT file.name ASC
```

### Storage (Mongo / Redis)

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND (contains(tags, "layer/mongo") OR contains(tags, "layer/redis"))
SORT file.name ASC
```

### Cluster

```dataview
TABLE source AS "來源模組"
FROM ""
WHERE contains(tags, "type/class") AND contains(tags, "layer/cluster")
SORT file.name ASC
```
