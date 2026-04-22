---
tags:
  - type/class
  - layer/manager
  - status/complete
source: csp_lib/manager/command/manager.py
updated: 2026-04-23
version: ">=0.10.0"
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
| `leader_gate` | `LeaderGate \| None` (kw-only) | Leader 閘門；非 leader 時 `execute()` raise `NotLeaderError`。單節點可省略或傳 `AlwaysLeaderGate` |
| `validation_rules` | `Sequence[WriteValidationRule] \| Mapping[str, WriteValidationRule] \| None` (kw-only) | 寫入前驗證鏈，預設 `None` 退化為舊行為。Sequence = 全域、Mapping = per-point |

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

1. Leader gate 檢查（若注入 `leader_gate` 且非 leader → raise `NotLeaderError`）
2. 建立 `pending` 記錄至 DB
3. 查找目標設備（不存在 → 更新為 `DEVICE_NOT_FOUND`）
4. **驗證鏈**（若注入 `validation_rules`）：
   - 依序呼叫每條 rule；首條 reject 即中止，repository 寫入 `VALIDATION_FAILED` 並回 `WriteResult(status=WriteStatus.VALIDATION_FAILED)`
   - Clamp 情境下 `effective_value` 沿鏈累積，最終以 clamp 後值寫入設備
5. 更新狀態為 `EXECUTING`
6. 執行設備寫入（`device.write(name, value, verify)`）
7. 更新 DB 結果（`SUCCESS` 或 `FAILED`）
8. 回傳 `WriteResult`

## 寫入驗證鏈（validation_rules）

從 v0.10.0 開始，`WriteCommandManager` 可注入 `WriteValidationRule` 鏈（見 [[ValidationResult]] / [[RangeRule]]）於 `device.write()` 之前做宣告式驗證。

### 兩種注入型別

- `Sequence[WriteValidationRule]` — 全域 rule，對每個 point 依序全跑
- `Mapping[str, WriteValidationRule]` — per-point rule，僅對 key 指定的 `point_name` 套用；未列名的 point 直接 pass-through
- `None`（預設）— 完全 pass-through，行為與舊版相同

### Clamp vs Reject

- `accepted=True` 時使用 `effective_value` 繼續（可能是 clamp 後新值，後續 rule 以該值繼續驗證）
- `accepted=False` 時中止寫入；repository 記錄 `CommandStatus.VALIDATION_FAILED` 附原值與 `reason`
- NaN/Inf 一律 reject（對照 bug-lesson `numerical-safety-layered`）

完整情境見 [`examples/18_write_validation.py`](../../examples/18_write_validation.py)。

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
