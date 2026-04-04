---
tags:
  - type/class
  - layer/modbus-gateway
  - status/complete
source: csp_lib/modbus_gateway/server.py
updated: 2026-04-04
version: ">=0.5.0"
---

# ModbusGatewayServer

> [!info] v0.5.0 新增

`ModbusGatewayServer` 是 Modbus TCP Gateway 的主 orchestrator，對外暴露系統狀態讓 EMS/SCADA 透過標準 Modbus TCP 讀寫。整合 [[RegisterMap|GatewayRegisterMap]]、[[WriteValidation|WritePipeline]]、[[SyncSources|DataSyncSource]]、[[GatewayConfig#CommunicationWatchdog|CommunicationWatchdog]] 的完整生命週期管理。

---

## 類別簽名

```python
class ModbusGatewayServer(AsyncLifecycleMixin):
    def __init__(
        self,
        config: GatewayServerConfig,
        register_defs: Sequence[GatewayRegisterDef],
        *,
        write_rules: Mapping[str, Any] | None = None,
        validators: Sequence[WriteValidator] = (),
        hooks: Sequence[WriteHook] = (),
        sync_sources: Sequence[DataSyncSource] = (),
    ) -> None: ...
```

### 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | [[GatewayConfig#GatewayServerConfig]] | 伺服器組態（host, port, unit_id 等） |
| `register_defs` | `Sequence[GatewayRegisterDef]` | 暫存器定義列表 |
| `write_rules` | `Mapping[str, WriteRule] \| None` | 每個暫存器的寫入規則（clamp/reject） |
| `validators` | `Sequence[WriteValidator]` | 寫入驗證器鏈 |
| `hooks` | `Sequence[WriteHook]` | 寫入後事件鉤子 |
| `sync_sources` | `Sequence[DataSyncSource]` | 外部資料同步來源 |

---

## 生命週期

`ModbusGatewayServer` 繼承 [[AsyncLifecycleMixin]]，支援 `async with` 語法：

```python
async with ModbusGatewayServer(config, registers) as gw:
    # Server 已啟動
    await gw.serve()  # 阻塞直到 stop() 或 context exit
```

### 啟動流程 (`_on_start`)

1. 建立 pymodbus `ModbusTcpServer`（含 HR/IR DataBlock）
2. 啟動 pymodbus server（background mode）
3. 恢復持久化狀態（若有 [[WriteValidation#StatePersistHook|StatePersistHook]]）
4. 啟動所有 [[SyncSources|DataSyncSource]]
5. 啟動 [[GatewayConfig#CommunicationWatchdog|CommunicationWatchdog]]

### 關閉流程 (`_on_stop`)

1. 停止 Watchdog
2. 停止所有 DataSyncSource
3. 關閉 pymodbus server
4. 設定 serve event（解除 `serve()` 阻塞）

---

## Public API

### Properties

| 屬性 | 型別 | 說明 |
|------|------|------|
| `config` | `GatewayServerConfig` | 伺服器組態 |
| `register_map` | `GatewayRegisterMap` | 暫存器位址空間管理器 |
| `watchdog` | `CommunicationWatchdog` | 通訊看門狗 |
| `is_running` | `bool` | 伺服器是否正在運行 |

### Methods

| 方法 | 說明 |
|------|------|
| `add_validator(validator)` | 新增寫入驗證器到管線 |
| `add_hook(hook)` | 新增寫入後事件鉤子 |
| `add_sync_source(source)` | 新增資料同步來源 |
| `set_register(name, value)` | 以程式方式設定暫存器值（物理值） |
| `get_register(name)` | 取得暫存器值（物理值） |
| `get_all_registers()` | 取得所有暫存器值 `{name: value}` |
| `await serve()` | 阻塞直到伺服器停止 |

---

## Quick Example

```python
from csp_lib.modbus import UInt16, Int32
from csp_lib.modbus_gateway import (
    GatewayServerConfig,
    GatewayRegisterDef,
    RegisterType,
    ModbusGatewayServer,
    CallbackHook,
    PollingCallbackSource,
)

async def on_write(name: str, old: float, new: float) -> None:
    print(f"EMS wrote {name}: {old} -> {new}")

async def poll_device() -> dict[str, float]:
    return {"soc": 75.5, "soh": 98.0}

registers = [
    GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING, unit="kW"),
    GatewayRegisterDef("soc", 100, UInt16(), RegisterType.INPUT, scale=10, unit="%"),
    GatewayRegisterDef("soh", 101, UInt16(), RegisterType.INPUT, scale=10, unit="%"),
]

config = GatewayServerConfig(port=502, unit_id=1)

async with ModbusGatewayServer(
    config,
    registers,
    hooks=[CallbackHook(on_write)],
    sync_sources=[PollingCallbackSource(poll_device, interval=1.0)],
) as gw:
    # 程式化更新 Input Register
    gw.set_register("soc", 80.0)
    await gw.serve()
```

---

## 相關頁面

- [[GatewayConfig]] -- 組態類別詳細說明
- [[RegisterMap]] -- 暫存器位址空間管理
- [[WriteValidation]] -- 寫入驗證鏈
- [[SyncSources]] -- 資料同步來源
