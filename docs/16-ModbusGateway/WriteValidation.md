---
tags:
  - type/class
  - layer/modbus-gateway
  - status/complete
source: csp_lib/modbus_gateway/validators.py, csp_lib/modbus_gateway/pipeline.py, csp_lib/modbus_gateway/hooks.py
updated: 2026-04-16
version: ">=0.7.3"
---

# WriteValidation

> [!info] v0.5.0 新增

寫入驗證鏈是 ModbusGateway 的核心安全機制，確保 EMS/SCADA 的寫入請求經過完整驗證才會生效。包含三個階段：**Validator 驗證** -> **Rule 規則** -> **Hook 事件鉤子**。

---

## 處理管線 (WritePipeline)

`WritePipeline`（`csp_lib/modbus_gateway/pipeline.py`）處理 EMS 寫入的完整管線：

```
EMS 原始寫入 (raw registers)
  │
  ├─ 1. 解碼 raw registers → physical value
  ├─ 2. writable gate — reg_def.writable=False 時記錄 RegisterNotWritableError 並 skip（不 raise，v0.7.3）
  ├─ 3. WriteValidator chain — 全部 accept 才繼續
  ├─ 4. WriteRule clamp/reject — 範圍限制
  ├─ 5. 更新 GatewayRegisterMap
  └─ 6. 收集變更 → dispatch WriteHook
```

> [!note] v0.7.3 SEC-006
> writable gate（步驟 2）在 validator chain 之前插入，`writable=False` 的 register 直接被 skip 並記錄 WARNING（包含 `RegisterNotWritableError` 訊息），不會進入後續驗證步驟。**此 error 僅作為日誌載體，不會 raise，也不會向 Modbus client 回傳 exception**——client 端觀察到的是寫入後讀回仍為舊值。

### `process_write(address, values)` 流程

1. 透過 [[RegisterMap|GatewayRegisterMap]] 的 `find_affected_registers()` 找出受影響的暫存器
2. 對每個受影響暫存器：
   - 從 raw values 提取對應 slice 並解碼為物理值
   - **檢查 `reg_def.writable`**（v0.7.3）— `False` 時記錄 WARNING 並 skip，不進入驗證鏈
   - 依序執行所有 `WriteValidator.validate()` — 任一拒絕即跳過此暫存器
   - 執行對應 `WriteRule.apply()` — 可 clamp 或 reject
   - 更新 RegisterMap
3. 回傳 `list[tuple[name, old_value, new_value]]` 供 Hook dispatch

---

## Protocol 介面

### WriteValidator

```python
@runtime_checkable
class WriteValidator(Protocol):
    def validate(self, register_name: str, value: Any) -> bool:
        """回傳 True 接受寫入，False 拒絕。"""
        ...
```

### WriteHook

```python
@runtime_checkable
class WriteHook(Protocol):
    async def on_write(self, register_name: str, old_value: Any, new_value: Any) -> None:
        """寫入成功後觸發的非同步鉤子。"""
        ...
```

來源：`csp_lib/modbus_gateway/protocol.py`

---

## 內建 Validator

### AddressWhitelistValidator

只允許白名單中的暫存器被寫入，不在白名單內的一律拒絕。

```python
from csp_lib.modbus_gateway import AddressWhitelistValidator

validator = AddressWhitelistValidator({"active_power_setpoint", "reactive_power_setpoint"})

# 白名單內 — 通過
assert validator.validate("active_power_setpoint", 100) is True

# 白名單外 — 拒絕
assert validator.validate("firmware_version", 42) is False
```

來源：`csp_lib/modbus_gateway/validators.py`

---

## WriteRule

[[GatewayConfig#WriteRule]] 定義單一暫存器的寫入約束。透過 `write_rules` 參數傳入 [[ModbusGatewayServer]]。

```python
from csp_lib.modbus_gateway import WriteRule

# Clamp 模式：超出範圍時自動截斷
rule = WriteRule("p_command", min_value=-500, max_value=500, clamp=True)
value, rejected = rule.apply("p_command", 600)
assert value == 500 and rejected is False

# Reject 模式：超出範圍時拒絕寫入
rule = WriteRule("p_command", min_value=-500, max_value=500, clamp=False)
value, rejected = rule.apply("p_command", 600)
assert rejected is True
```

---

## 內建 WriteHook

### CallbackHook

呼叫使用者提供的 async callback。

```python
from csp_lib.modbus_gateway import CallbackHook

async def my_handler(name: str, old: float, new: float) -> None:
    print(f"{name}: {old} -> {new}")

hook = CallbackHook(my_handler)
```

### RedisPublishHook

將寫入事件發布到 Redis channel，格式為 JSON：

```json
{"register": "<name>", "old": <old_value>, "new": <new_value>, "ts": <unix_timestamp>}
```

```python
from csp_lib.modbus_gateway import RedisPublishHook

hook = RedisPublishHook(redis_client, channel="gateway:writes")
```

### StatePersistHook

將 Holding Register 的寫入值持久化到 Redis Hash，伺服器重啟時可自動恢復。

- Redis key：`gateway:{server_name}:state`
- Hash field：暫存器名稱，value：JSON 編碼的物理值

```python
from csp_lib.modbus_gateway import StatePersistHook

hook = StatePersistHook(redis_client, server_name="pcs_gateway")
# 恢復先前持久化的狀態
count = await hook.restore_all(register_map)
```

| 方法 | 說明 |
|------|------|
| `on_write(name, old, new)` | 每次寫入後持久化新值到 Redis |
| `restore_all(register_map)` | 從 Redis 恢復所有值到 RegisterMap，回傳恢復數量 |
| `redis_key` | Redis Hash key（property） |

來源：`csp_lib/modbus_gateway/hooks.py`

---

## Quick Example

```python
from csp_lib.modbus import Int32
from csp_lib.modbus_gateway import (
    GatewayServerConfig,
    GatewayRegisterDef,
    RegisterType,
    ModbusGatewayServer,
    WriteRule,
    AddressWhitelistValidator,
    CallbackHook,
    RedisPublishHook,
    StatePersistHook,
)

registers = [
    GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING, unit="kW"),
    GatewayRegisterDef("q_command", 2, Int32(), RegisterType.HOLDING, unit="kVar"),
]

rules = {
    "p_command": WriteRule("p_command", min_value=-500, max_value=500, clamp=True),
    "q_command": WriteRule("q_command", min_value=-200, max_value=200, clamp=False),
}

async with ModbusGatewayServer(
    GatewayServerConfig(port=502),
    registers,
    write_rules=rules,
    validators=[AddressWhitelistValidator({"p_command", "q_command"})],
    hooks=[
        CallbackHook(my_handler),
        RedisPublishHook(redis_client),
        StatePersistHook(redis_client, server_name="pcs"),
    ],
) as gw:
    await gw.serve()
```

---

## 相關頁面

- [[ModbusGatewayServer]] -- 驗證鏈的整合入口
- [[RegisterMap]] -- `WritePipeline` 依賴的暫存器管理器
- [[GatewayConfig]] -- `WriteRule` 定義
