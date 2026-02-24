---
tags: [type/concept, layer/core, status/complete]
source: csp_lib/core/errors.py
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

## 繼承結構

```
Exception
├── DeviceError(device_id, message)
│   ├── DeviceConnectionError
│   ├── CommunicationError
│   └── AlarmError(device_id, alarm_code, message)
└── ConfigurationError(message)
```

## 使用範例

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

## 設計備註

- `DeviceError` 及其子類別皆攜帶 `device_id` 屬性，方便日誌與監控系統識別問題設備
- `AlarmError` 額外攜帶 `alarm_code`，對應告警定義中的代碼
- `ConfigurationError` 直接繼承 `Exception` 而非 `DeviceError`，因為配置錯誤不一定與特定設備相關
- 錯誤訊息格式：`[{device_id}] {message}`
