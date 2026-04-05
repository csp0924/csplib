---
tags:
  - type/class
  - layer/core
  - status/complete
source: csp_lib/core/logging/
created: 2026-02-17
updated: 2026-04-05
version: ">=0.7.0"
---

# Logging

> 基於 loguru 的模組化日誌系統（v0.7.0 全面重構）

回到 [[_MOC Core]]

## 概述

`csp_lib.core` 提供集中化的日誌管理，基於 [loguru](https://github.com/Delgan/loguru) 實作，以 `module` 欄位區分日誌來源。

v0.7.0 將日誌功能拆分至 `csp_lib/core/logging/` 子套件，引入 `SinkManager`、`LogFilter`、`LogContext`、`LogCapture` 等元件，提供完整的 Sink 生命週期管理、結構化上下文注入與測試工具。所有頂層 API（`get_logger`、`set_level`、`configure_logging`）保持向後相容。

---

## Quick Example

### 最小初始化

```python
from csp_lib.core import get_logger, configure_logging

configure_logging(level="INFO")

logger = get_logger("csp_lib.mongo")
logger.info("已連線至 MongoDB")
```

### 完整生產配置

```python
from csp_lib.core import configure_logging, add_file_sink, FileSinkConfig

# 初始化（diagnose=False 是生產預設，防止洩漏敏感資訊）
configure_logging(level="INFO", enqueue=True, diagnose=False)

# 新增 rotating file sink
add_file_sink(FileSinkConfig(
    path="/var/log/csp/app.log",
    rotation="100 MB",
    retention="30 days",
    compression="zip",
    level="DEBUG",
    enqueue=True,
))
```

### 環境變數配置

```python
# 讀取 CSP_LOG_LEVEL / CSP_LOG_ENQUEUE / CSP_LOG_JSON / CSP_LOG_DIAGNOSE
configure_logging(level="INFO", env_prefix="CSP")
```

```bash
export CSP_LOG_LEVEL=DEBUG
export CSP_LOG_ENQUEUE=true
export CSP_LOG_JSON=false
```

---

## Common Patterns

### 依模組設定等級

```python
from csp_lib.core import set_level

# 只對 mongo 模組開啟 DEBUG
set_level("DEBUG", module="csp_lib.mongo")

# 將 redis 模組設為 WARNING
set_level("WARNING", module="csp_lib.redis")
```

### 結構化上下文（LogContext）

```python
from csp_lib.core import get_logger, LogContext

logger = get_logger("csp_lib.controller")

# context manager：自動還原
async with LogContext(request_id="req-abc", device_id="PCS-01"):
    logger.info("處理請求")   # extra 自動包含 request_id 和 device_id

# decorator 用法
@LogContext(operation="calibrate")
async def calibrate_device(device_id: str) -> None:
    logger.info("校準 {}", device_id)
```

### 非同步 Sink（傳送至遠端）

```python
from csp_lib.core import SinkManager

async def send_to_webhook(msg: str) -> None:
    await http_client.post("https://log.example.com/ingest", data=msg)

mgr = SinkManager.get_instance()
mgr.add_async_sink(send_to_webhook, name="webhook", level="WARNING", max_queue_size=5000)
```

### 遠端等級控制（Redis）

```python
from csp_lib.core import SinkManager
from csp_lib.redis import RedisLogLevelSource

# Redis Hash: csp:log_levels → {module: level}
source = RedisLogLevelSource(redis_client, key_prefix="csp")
await SinkManager.get_instance().attach_remote_source(source, poll_interval=60.0)
```

---

## Gotchas / Tips

> [!warning] `diagnose=False` 為生產預設（v0.7.0 行為變更）
> 舊版 `configure_logging()` 預設 `diagnose=True`。v0.7.0 起改為 `False`，
> 防止 exception traceback 洩漏 Modbus 位址、Redis 密碼等敏感資訊。
> 開發環境可手動傳入 `diagnose=True`。

> [!note] `set_level()` 不再重建 Sink
> v0.7.0 前，`set_level()` 會 remove/re-add 所有 sink，導致 file sink 短暫中斷。
> 現在改為更新 `LogFilter` 的 dict，立即生效且無 I/O 開銷。

> [!tip] `SinkManager.reset()` 用於測試
> 每個測試 case 前呼叫 `SinkManager.reset()` 可清除所有 sink，避免 sink 狀態污染。
> 或直接使用 `LogCapture` — 它不經過 SinkManager，不受影響。

> [!tip] `LogCapture` 僅供測試使用
> `LogCapture` 直接操作 loguru root logger，不受 `SinkManager` 管理。
> 在 `with LogCapture() as cap:` 退出時自動移除，不需要手動清理。

---

## API Reference

### 頂層函式（`csp_lib.core`）

| 函式 | 說明 |
|------|------|
| `get_logger(name: str) -> Logger` | 取得模組專屬 logger，回傳綁定 `module=name` 的 loguru Logger |
| `set_level(level: str, module: str \| None = None) -> None` | 設定 log 等級；`module=None` 設定全域預設等級 |
| `configure_logging(level, format_string, *, enqueue, json_output, diagnose, env_prefix) -> None` | 初始化 logging，重置 SinkManager 並新增 stderr sink |
| `add_file_sink(config: FileSinkConfig) -> int` | 新增檔案 sink，回傳 loguru sink ID |
| `logger` | 預設模組 logger（`module="csp_lib"`），供快速測試使用 |
| `DEFAULT_FORMAT` | 帶 ANSI 色彩的預設格式字串常數 |

#### `configure_logging()` 參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `level` | `str` | `"INFO"` | 預設 log 等級 |
| `format_string` | `str \| None` | `None` | 自訂格式字串，`None` 使用 `DEFAULT_FORMAT` |
| `enqueue` | `bool` | `False` | 是否啟用佇列寫入（多執行緒安全） |
| `json_output` | `bool` | `False` | 是否以 JSON Lines 輸出 |
| `diagnose` | `bool` | `False` | 是否在 exception 中顯示局部變數 |
| `env_prefix` | `str \| None` | `None` | 環境變數前綴，設定後讀取 `{prefix}_LOG_*` 覆蓋配置 |

---

### `LogFilter`

`csp_lib/core/logging/filter.py`

模組等級過濾器，可直接作為 loguru `filter` 參數使用（實作 `__call__`）。

```python
from csp_lib.core import LogFilter

f = LogFilter(default_level="INFO")
f.set_module_level("csp_lib.mongo", "DEBUG")
```

| 方法 / 屬性 | 說明 |
|-------------|------|
| `__init__(default_level: str = "INFO")` | 建立過濾器，設定預設等級 |
| `default_level: str` | 預設等級（property，可賦值） |
| `module_levels: dict[str, str]` | 模組等級對應表（防禦性複製） |
| `set_module_level(module, level)` | 設定特定模組等級 |
| `remove_module_level(module)` | 移除模組等級設定，回歸預設 |
| `get_effective_level(module_name) -> str` | 最長前綴匹配，取得有效等級 |
| `__call__(record: dict) -> bool` | loguru filter 介面，注入 LogContext 後判斷是否輸出 |

---

### `SinkManager`

`csp_lib/core/logging/sink_manager.py`

全域 Sink 生命週期管理單例。

```python
from csp_lib.core import SinkManager

mgr = SinkManager.get_instance()
sid = mgr.add_stderr_sink(level="DEBUG")
mgr.set_level("WARNING", module="csp_lib.redis")
```

#### 單例操作

| 方法 | 說明 |
|------|------|
| `SinkManager.get_instance() -> SinkManager` | 取得全域單例 |
| `SinkManager.reset() -> None` | 重置單例（測試用），移除所有 managed sinks |

#### Sink 操作

| 方法 | 說明 |
|------|------|
| `add_sink(sink, *, name, sink_type, level, format, enqueue, serialize, diagnose, **kwargs) -> int` | 新增 sink，回傳 loguru sink ID |
| `remove_sink(sink_id: int)` | 依 ID 移除 sink，不存在時拋 `KeyError` |
| `remove_sink_by_name(name: str)` | 依名稱移除 sink，不存在時拋 `KeyError` |
| `list_sinks() -> list[SinkInfo]` | 列出所有 managed sinks |
| `get_sink(name: str) -> SinkInfo \| None` | 依名稱查詢 sink |
| `remove_all()` | 移除所有 managed sinks |

#### 便利方法

| 方法 | 說明 |
|------|------|
| `add_stderr_sink(*, level, format, enqueue, serialize, diagnose) -> int` | 新增 stderr sink |
| `add_file_sink(config: FileSinkConfig) -> int` | 新增檔案 sink |
| `add_async_sink(handler, *, name, level, max_queue_size, **kwargs) -> int` | 新增非同步 sink |

#### 等級控制

| 方法 | 說明 |
|------|------|
| `set_level(level: str, module: str \| None = None)` | 設定等級，委派給 LogFilter，不重建 sink |
| `filter: LogFilter` | 取得模組等級過濾器（唯讀） |

#### 遠端等級控制

| 方法 | 說明 |
|------|------|
| `attach_remote_source(source, poll_interval=60.0)` | 連接遠端等級來源，啟動背景輪詢 |
| `detach_remote_source()` | 中斷遠端等級來源連線 |

---

### `SinkInfo`

`csp_lib/core/logging/sink_manager.py`

Sink 資訊，frozen dataclass。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `sink_id` | `int` | loguru 內部 sink ID |
| `name` | `str` | 使用者指定名稱 |
| `sink_type` | `str` | 類型：`"stderr"` \| `"file"` \| `"custom"` \| `"async"` |
| `level` | `str` | 設定的最低等級 |
| `is_active` | `bool` | 是否仍在使用中 |

---

### `FileSinkConfig`

`csp_lib/core/logging/file_config.py`

檔案 Sink 配置，frozen dataclass。

```python
from csp_lib.core import FileSinkConfig, add_file_sink

config = FileSinkConfig(
    path="/var/log/csp/app.log",
    rotation="100 MB",
    retention="30 days",
    compression="zip",
    level="DEBUG",
    enqueue=True,
)
add_file_sink(config)
```

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `path` | `str` | （必填） | 檔案路徑 |
| `rotation` | `str \| int \| None` | `"100 MB"` | 輪替條件（`"1 day"` / `"100 MB"` / `None`） |
| `retention` | `str \| int \| None` | `"30 days"` | 保留策略（`"30 days"` / `10` 個檔案） |
| `compression` | `str \| None` | `None` | 壓縮格式（`"zip"` / `"gz"`） |
| `level` | `str` | `"DEBUG"` | 最低 log 等級 |
| `format` | `str \| None` | `None` | 自訂格式字串 |
| `enqueue` | `bool` | `True` | 是否佇列寫入（async-safe） |
| `serialize` | `bool` | `False` | 是否 JSON Lines 輸出 |
| `encoding` | `str` | `"utf-8"` | 檔案編碼 |
| `name` | `str \| None` | `None` | Sink 名稱，`None` 則自動為 `"file:{path}"` |

---

### `LogContext`

`csp_lib/core/logging/context.py`

結構化日誌上下文管理器，使用 `contextvars.ContextVar` 實現 async-safe 上下文隔離。

```python
from csp_lib.core import LogContext

# context manager（同步/非同步均可）
with LogContext(request_id="req-001", device_id="PCS-01"):
    logger.info("處理中")   # log record 的 extra 包含 request_id, device_id

# 巢狀使用：內層繼承並可覆蓋外層
async with LogContext(session="s1"):
    async with LogContext(device_id="BMS-02"):
        logger.info("...")   # extra 同時有 session 和 device_id
```

| 方法 | 說明 |
|------|------|
| `__init__(**bindings)` | 建立上下文，指定要注入的 key-value |
| `__enter__() / __exit__()` | 同步 context manager |
| `__aenter__() / __aexit__()` | 非同步 context manager |
| `__call__(func)` | 作為 decorator，包裝同步或非同步函式 |
| `LogContext.current() -> dict` | 取得當前上下文所有 bindings（靜態，防禦性複製） |
| `LogContext.bind(**bindings)` | 直接新增 bindings（靜態，不可逆，建議優先用 context manager） |
| `LogContext.unbind(*keys)` | 從當前上下文移除指定 keys（靜態） |

---

### `LogCapture`

`csp_lib/core/logging/capture.py`

測試用日誌捕獲器，在 context manager 範圍內攔截所有 loguru 輸出。

```python
from csp_lib.core import LogCapture

with LogCapture(level="DEBUG") as cap:
    some_function_that_logs()

assert cap.contains("已連線", level="INFO")
assert len(cap.filter(module="csp_lib.mongo")) == 2
```

| 方法 / 屬性 | 說明 |
|-------------|------|
| `__init__(level: str = "TRACE")` | 設定最低攔截等級 |
| `__enter__() / __exit__()` | context manager，自動安裝/移除 sink |
| `records: list[CapturedRecord]` | 所有捕獲記錄 |
| `text: str` | 所有訊息合併為換行分隔的字串 |
| `contains(message, *, level, module) -> bool` | 部分匹配訊息，可選精確匹配 level/module |
| `filter(*, level, module, message_pattern) -> list[CapturedRecord]` | 多條件過濾，`message_pattern` 支援 regex |
| `clear()` | 清除所有記錄 |

---

### `CapturedRecord`

`csp_lib/core/logging/capture.py`

單筆捕獲的 log 記錄 dataclass。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `level` | `str` | 等級名稱（如 `"INFO"`） |
| `message` | `str` | 格式化前的原始訊息 |
| `module` | `str` | 模組名稱（來自 `extra["module"]`） |
| `extra` | `dict[str, Any]` | 其餘 extra 欄位 |
| `time` | `datetime \| None` | 記錄時間 |

---

### `RemoteLevelSource`

`csp_lib/core/logging/remote.py`

遠端 log 等級來源 `@runtime_checkable` Protocol，定義從外部系統取得模組等級的介面。

```python
from csp_lib.core import RemoteLevelSource

class MyHTTPSource:
    async def fetch_levels(self) -> dict[str, str]:
        resp = await http_client.get("/log-levels")
        return resp.json()  # {"csp_lib.mongo": "DEBUG", "": "INFO"}

    async def subscribe(self, callback) -> None:
        # 監聽 WebSocket 等級變更
        ...

assert isinstance(MyHTTPSource(), RemoteLevelSource)
```

| 方法 | 說明 |
|------|------|
| `async fetch_levels() -> dict[str, str]` | 一次性拉取所有模組等級；空字串 key `""` 代表預設等級 |
| `async subscribe(callback: Callable[[str, str], None]) -> None` | 訂閱等級變更，變更時呼叫 `callback(module, level)` |

---

### `AsyncSinkAdapter`

`csp_lib/core/logging/async_sink.py`

將 async handler 包裝為 loguru 可接受的同步 `write` 介面。

```python
from csp_lib.core import AsyncSinkAdapter

async def forward_to_sentry(msg: str) -> None:
    await sentry_client.capture_log(msg)

adapter = AsyncSinkAdapter(forward_to_sentry, max_queue_size=5000)
# 通常透過 SinkManager.add_async_sink() 使用，不需直接操作
```

| 方法 | 說明 |
|------|------|
| `__init__(async_handler, *, loop, max_queue_size, flush_timeout)` | 建立轉接器 |
| `write(message: str) -> None` | 同步寫入，佇列滿時靜默丟棄 |
| `async close() -> None` | 關閉，等待佇列清空（超時後強制關閉） |

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `async_handler` | `Callable[[str], Awaitable[None]]` | （必填） | 非同步 handler |
| `loop` | `AbstractEventLoop \| None` | `None` | 目標 event loop，`None` 使用當前 loop |
| `max_queue_size` | `int` | `10000` | 內部佇列上限 |
| `flush_timeout` | `float` | `5.0` | close 時等待清空的超時秒數 |

---

### `RedisLogLevelSource`

`csp_lib/redis/log_level_source.py`

`RemoteLevelSource` 的 Redis 實作，透過 Redis Hash + Pub/Sub 提供即時等級同步。

```python
from csp_lib.core import SinkManager
from csp_lib.redis import RedisLogLevelSource, RedisClient

async with RedisClient(config) as redis:
    source = RedisLogLevelSource(redis, key_prefix="csp")
    await SinkManager.get_instance().attach_remote_source(source, poll_interval=60.0)
    # 現在可透過 Redis 動態調整等級：
    # HSET csp:log_levels csp_lib.mongo DEBUG
    # PUBLISH csp:log_levels:changed "csp_lib.mongo:DEBUG"
```

Redis 結構：

| Key | 說明 |
|-----|------|
| `{key_prefix}:log_levels` | Hash，field = 模組名稱，value = 等級字串 |
| `{key_prefix}:log_levels:changed` | Pub/Sub channel，訊息格式 `"module:level"` |

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `client` | `RedisClient` | （必填） | Redis 客戶端 |
| `key_prefix` | `str` | `"csp"` | Redis key 前綴 |

---

## 等級匹配規則

設定等級時採用**最長前綴匹配**：

- 若同時設定了 `csp_lib.mongo` 與 `csp_lib.mongo.queue`：
  - `csp_lib.mongo.writer` 使用 `csp_lib.mongo` 的設定
  - `csp_lib.mongo.queue` 使用 `csp_lib.mongo.queue` 的設定（更精確）

## 支援的 Log 等級

`TRACE`、`DEBUG`、`INFO`、`SUCCESS`、`WARNING`、`ERROR`、`CRITICAL`

## 環境變數對照表

| 環境變數 | 對應參數 | 範例 |
|----------|----------|------|
| `{PREFIX}_LOG_LEVEL` | `level` | `INFO` |
| `{PREFIX}_LOG_FORMAT` | `format_string` | `{time} \| {level} \| {message}` |
| `{PREFIX}_LOG_ENQUEUE` | `enqueue` | `true` / `1` |
| `{PREFIX}_LOG_JSON` | `json_output` | `false` |
| `{PREFIX}_LOG_DIAGNOSE` | `diagnose` | `false` |

## Import 路徑

```python
# 頂層（推薦）
from csp_lib.core import (
    get_logger, set_level, configure_logging, add_file_sink,
    LogFilter, SinkManager, SinkInfo, FileSinkConfig,
    LogContext, LogCapture, CapturedRecord,
    RemoteLevelSource, AsyncSinkAdapter,
    DEFAULT_FORMAT,
)

# 子模組（進階用途）
from csp_lib.core.logging import LogFilter, SinkManager, LogContext
from csp_lib.redis import RedisLogLevelSource
```

## 相關頁面

- [[AsyncLifecycleMixin]] — 日誌系統在生命週期元件中的整合
- [[Error Hierarchy]] — 例外與 log 等級的搭配建議
- [[RuntimeParameters]] — 與 LogContext 搭配的即時參數容器
