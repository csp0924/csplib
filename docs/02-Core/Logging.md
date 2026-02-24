---
tags: [type/class, layer/core, status/complete]
source: csp_lib/core/__init__.py
---
# Logging

> 基於 loguru 的模組化日誌系統

回到 [[_MOC Core]]

## 概述

`csp_lib.core` 提供集中化的日誌管理，支援依模組名稱獨立設定 log 等級。所有日誌透過 [loguru](https://github.com/Delgan/loguru) 實作，並以 `module` 欄位區分來源。

## 公開 API

| 函式 | 說明 |
|------|------|
| `get_logger(name)` | 取得模組專屬的 logger 實例，回傳綁定 `module=name` 的 loguru Logger |
| `set_level(level, module=None)` | 設定 log 等級；若 `module` 為 `None` 則設定全域等級 |
| `configure_logging(level, format_string=None)` | 初始化全域 logging 配置，可自訂格式字串 |

## 使用範例

### 基本初始化

```python
from csp_lib.core import get_logger, set_level, configure_logging

# 初始化 logging
configure_logging(level="INFO")

# 取得模組專屬 logger
logger = get_logger("csp_lib.mongo")
logger.info("Connected to MongoDB")
```

### 依模組設定等級

```python
from csp_lib.core import set_level

# 只對 mongo 模組開啟 DEBUG
set_level("DEBUG", module="csp_lib.mongo")

# 將 redis 模組設為 WARNING
set_level("WARNING", module="csp_lib.redis")
```

## 等級匹配規則

設定等級時採用**最長前綴匹配**：

- 若同時設定了 `csp_lib.mongo` 與 `csp_lib.mongo.queue`：
  - `csp_lib.mongo.writer` 會使用 `csp_lib.mongo` 的設定
  - `csp_lib.mongo.queue` 會使用 `csp_lib.mongo.queue` 的設定（更精確）

## 支援的 Log 等級

`TRACE`、`DEBUG`、`INFO`、`SUCCESS`、`WARNING`、`ERROR`、`CRITICAL`

## 預設輸出格式

```
{time:YYYY-MM-DD HH:mm:ss} | {level} | {module} | {message}
```

## 設計備註

- 內部使用 `_module_loggers` 字典快取已建立的 logger 實例
- `_module_levels` 儲存模組專屬等級設定，搭配 `_get_effective_level()` 進行前綴比對
- 每次呼叫 `set_level()` 會重新配置 loguru 的 handler（`_reconfigure_logger()`）
