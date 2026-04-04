---
tags: [type/concept, layer/core, status/complete]
source: csp_lib/core/errors.py
updated: 2026-04-04
version: v0.6.1
---
# Error Hierarchy

> 統一例外階層

回到 [[_MOC Core]]

## 概述

`csp_lib.core.errors` 定義了整個函式庫的統一錯誤階層，讓上層模組可以透過標準的例外類別進行錯誤分類與處理。

## 例外類別一覽

| 例外類別 | 繼承自 | 建構參數 | 說明 |
|---------|--------|---------|------|
| `DeviceError` | `Exception` | `device_id`, `message` | 設備層基礎例外 |
| `DeviceConnectionError` | `DeviceError` | `device_id`, `message` | 連線/斷線失敗 |
| `CommunicationError` | `DeviceError` | `device_id`, `message` | 讀寫逾時/解碼錯誤 |
| `AlarmError` | `DeviceError` | `device_id`, `alarm_code`, `message` | 告警觸發 |
| `ConfigurationError` | `Exception` | `message` | 配置無效（非設備層級） |
| `StrategyExecutionError` | `Exception` | `strategy_name`, `message` | 策略執行失敗（非設備層級） |
| `ProtectionError` | `Exception` | `rule_name`, `message` | 保護鏈失敗（非設備層級） |
| `DeviceRegistryError` | `DeviceError` | `device_id`, `message` | 設備註冊/查詢失敗 |

> [!info] v0.5.1 新增
> `StrategyExecutionError`、`ProtectionError`、`DeviceRegistryError` 於 v0.5.1 加入。

## 繼承結構

```
Exception
├── DeviceError(device_id, message)
│   ├── DeviceConnectionError
│   ├── CommunicationError
│   ├── AlarmError(device_id, alarm_code, message)
│   └── DeviceRegistryError
├── ConfigurationError(message)
├── StrategyExecutionError(strategy_name, message)
└── ProtectionError(rule_name, message)
```

## Quick Example

### 捕捉設備相關錯誤

```python
from csp_lib.core import DeviceError, DeviceConnectionError, CommunicationError

try:
    await device.read()
except DeviceConnectionError as e:
    # 處理連線失敗
    logger.error(f"連線失敗: {e}")
except CommunicationError as e:
    # 處理通訊錯誤
    logger.error(f"通訊錯誤: {e}")
except DeviceError as e:
    # 捕捉所有設備層例外
    logger.error(f"設備錯誤: {e}")
```

### 告警例外

```python
from csp_lib.core import AlarmError

try:
    await process_alarm(device_id="pcs_01", alarm_code="OV001")
except AlarmError as e:
    logger.warning(f"告警 [{e.alarm_code}] 於設備 {e.device_id}: {e}")
```

### 配置驗證

```python
from csp_lib.core import ConfigurationError

if not config.is_valid():
    raise ConfigurationError("無效的系統配置：缺少必要欄位")
```

### 策略執行錯誤

> [!info] v0.5.1 新增

```python
from csp_lib.core import StrategyExecutionError

try:
    await executor.execute(strategy, context)
except StrategyExecutionError as e:
    logger.error(f"策略 {e.strategy_name} 執行失敗: {e}")
```

### 保護鏈錯誤

> [!info] v0.5.1 新增

```python
from csp_lib.core import ProtectionError

try:
    await guard.check(command)
except ProtectionError as e:
    logger.error(f"保護規則 {e.rule_name} 觸發: {e}")
```

### 設備註冊錯誤

> [!info] v0.5.1 新增

```python
from csp_lib.core import DeviceRegistryError

try:
    device = registry.get("pcs_01")
except DeviceRegistryError as e:
    logger.error(f"設備 {e.device_id} 註冊查詢失敗: {e}")
```

## 設計備註

- `DeviceError` 及其子類別皆攜帶 `device_id` 屬性，方便日誌與監控系統識別問題設備
- `AlarmError` 額外攜帶 `alarm_code`，對應告警定義中的代碼
- `ConfigurationError` 直接繼承 `Exception` 而非 `DeviceError`，因為配置錯誤不一定與特定設備相關
- `StrategyExecutionError` 攜帶 `strategy_name` 屬性，訊息格式：`Strategy '{strategy_name}': {message}`
- `ProtectionError` 攜帶 `rule_name` 屬性，訊息格式：`Protection rule '{rule_name}': {message}`
- `DeviceRegistryError` 繼承 `DeviceError`，因為設備註冊/查詢與特定設備相關
- 錯誤訊息格式：`[{device_id}] {message}`
