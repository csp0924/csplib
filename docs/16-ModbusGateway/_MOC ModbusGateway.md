---
tags:
  - type/moc
  - layer/modbus-gateway
  - status/complete
created: 2026-04-04
---

# ModbusGateway 模組總覽

> [!info] v0.5.0 新增

> **Modbus TCP Gateway Server (`csp_lib.modbus_gateway`)**

ModbusGateway 模組讓 EMS/SCADA 透過標準 Modbus TCP 協定讀寫 csp_lib 管理的設備數據。Gateway 作為 Modbus slave 對外暴露暫存器，支援宣告式 register map 定義、寫入驗證鏈、資料同步來源、通訊看門狗等功能。

---

## 架構概覽

```
ModbusGatewayServer (AsyncLifecycleMixin, pymodbus TCP)
  ├── GatewayRegisterMap ─── 暫存器位址空間管理
  │     ├── Holding Registers (FC03/FC06/FC16)
  │     └── Input Registers (FC04, 唯讀)
  ├── WritePipeline ─── 寫入處理管線
  │     ├── WriteValidator chain (驗證)
  │     ├── WriteRule clamp/reject (規則)
  │     └── WriteHook dispatch (事件鉤子)
  ├── DataSyncSource ─── 外部資料同步
  │     ├── RedisSubscriptionSource
  │     └── PollingCallbackSource
  └── CommunicationWatchdog ─── 通訊看門狗
```

---

## 索引

### 核心

| 頁面 | 說明 |
|------|------|
| [[ModbusGatewayServer]] | Gateway 主 orchestrator，整合所有子元件的生命週期管理 |
| [[GatewayConfig]] | 組態類別：`GatewayServerConfig`, `GatewayRegisterDef`, `WatchdogConfig`, `WriteRule` |

### Register Map

| 頁面 | 說明 |
|------|------|
| [[RegisterMap]] | 暫存器位址空間管理器，支援命名暫存器、scale factor、thread-safe |

### 寫入驗證

| 頁面 | 說明 |
|------|------|
| [[WriteValidation]] | 寫入驗證鏈：`WritePipeline`, `WriteValidator`, `WriteHook`, 內建實作 |

### 資料同步

| 頁面 | 說明 |
|------|------|
| [[SyncSources]] | 外部資料來源同步：`RedisSubscriptionSource`, `PollingCallbackSource` |

---

## Quick Example

```python
from csp_lib.modbus import UInt16, Int32
from csp_lib.modbus_gateway import (
    GatewayServerConfig,
    GatewayRegisterDef,
    RegisterType,
    ModbusGatewayServer,
    WriteRule,
    AddressWhitelistValidator,
    CallbackHook,
)

async def on_write(name: str, old: float, new: float) -> None:
    print(f"EMS wrote {name}: {old} -> {new}")

# 定義暫存器
registers = [
    GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING, unit="kW"),
    GatewayRegisterDef("soc", 100, UInt16(), RegisterType.INPUT, scale=10, unit="%"),
]

# 寫入規則
rules = {"p_command": WriteRule("p_command", min_value=-500, max_value=500, clamp=True)}

# 建立 Gateway
config = GatewayServerConfig(port=502, unit_id=1)
async with ModbusGatewayServer(
    config,
    registers,
    write_rules=rules,
    validators=[AddressWhitelistValidator({"p_command"})],
    hooks=[CallbackHook(on_write)],
) as gw:
    await gw.serve()
```

---

## Dataview 查詢

```dataview
TABLE source AS "原始碼", tags AS "標籤"
FROM "16-ModbusGateway"
WHERE file.name != "_MOC ModbusGateway"
SORT file.name ASC
```

---

## 相關 MOC

- 使用：[[_MOC Modbus]] -- 底層 Modbus 資料型別（`Float32`, `UInt16`, `ModbusCodec` 等）
- 使用：[[_MOC Core]] -- `AsyncLifecycleMixin` 生命週期基類
- 對比：[[_MOC Modbus Server]] -- 模擬測試用 Modbus Server（模擬器導向）
