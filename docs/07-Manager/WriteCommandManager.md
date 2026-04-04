---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/command/manager.py
updated: 2026-04-04
---

# WriteCommandManager

寫入指令管理器，隸屬於 [[_MOC Manager|Manager 模組]]。

## 概述

`WriteCommandManager` 統一管理外部寫入指令，提供審計日誌與設備路由功能。支援多種指令來源（Redis、gRPC、REST 等），透過 `RedisCommandAdapter` 等 Adapter 接收外部指令。

### 職責

1. 維護設備註冊表（`device_id` → `device`）
2. 接收指令 → 記錄 DB → 執行 → 更新結果
3. 支援多種指令來源

## 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `repository` | `CommandRepository` | 指令記錄儲存庫 |

## API

### 設備註冊

| 方法 | 說明 |
|------|------|
| `subscribe(device)` | 統一訂閱 API（內部委派至 `register_device()`） |
| `register_device(device)` | 註冊可寫入的設備（已 deprecated，建議改用 `subscribe()`） |
| `unregister_device(device_id)` | 取消註冊設備 |
| `get_device(device_id) -> AsyncModbusDevice \| None` | 取得已註冊的設備 |
| `registered_device_ids` | 已註冊的設備 ID 列表（`list[str]`） |

### 指令執行

| 方法 | 說明 |
|------|------|
| `execute(command) -> WriteResult` | 執行寫入指令（完整流程） |
| `execute_from_dict(data, source) -> WriteResult` | 從字典建立指令並執行（供 Adapter 使用） |

## 執行流程

1. 建立 `pending` 記錄至 DB
2. 查找目標設備（不存在 → 更新為 `DEVICE_NOT_FOUND`）
3. 更新狀態為 `EXECUTING`
4. 執行設備寫入（`device.write(name, value, verify)`）
5. 更新 DB 結果（`SUCCESS` 或 `FAILED`）
6. 回傳 `WriteResult`

## Quick Example

```python
from csp_lib.manager.command import WriteCommandManager, WriteCommand

repo = MongoCommandRepository(db["commands"])
manager = WriteCommandManager(repository=repo)

# 註冊可寫入的設備
manager.subscribe(device1)
manager.subscribe(device2)

# 執行指令
command = WriteCommand(
    device_id="device_001",
    point_name="setpoint",
    value=100,
)
result = await manager.execute(command)

# 從字典執行（供 Adapter 使用）
result = await manager.execute_from_dict(
    {"device_id": "device_001", "point_name": "setpoint", "value": 100},
    source=CommandSource.REDIS,
)
```

## 相關頁面

- [[UnifiedDeviceManager]] — 自動串接指令管理器
- [[RedisClient]] — Redis 指令來源
