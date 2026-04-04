---
tags:
  - type/class
  - layer/modbus-gateway
  - status/complete
source: csp_lib/modbus_gateway/register_map.py
updated: 2026-04-04
version: ">=0.5.0"
---

# GatewayRegisterMap

> [!info] v0.5.0 新增

`GatewayRegisterMap` 是 Gateway 的暫存器位址空間管理器。維護 Holding Register (HR) 與 Input Register (IR) 兩組獨立的原始暫存器陣列，提供命名暫存器映射、[[_MOC Modbus|ModbusCodec]] 編解碼、scale factor 轉換，以及 `threading.Lock` 執行緒安全保障。

---

## 類別簽名

```python
class GatewayRegisterMap:
    def __init__(
        self,
        config: GatewayServerConfig,
        register_defs: Sequence[GatewayRegisterDef],
    ) -> None: ...
```

### 建構參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `config` | [[GatewayConfig#GatewayServerConfig]] | 提供 byte order、register order、address space size 預設值 |
| `register_defs` | `Sequence[GatewayRegisterDef]` | 暫存器定義列表 |

### 建構時驗證

- **名稱唯一性**：重複名稱拋出 `ValueError`
- **位址空間**：超出 `register_space_size` 拋出 `ValueError`
- **位址重疊**：同類型暫存器位址重疊拋出 [[GatewayConfig#RegisterConflictError|RegisterConflictError]]
- **初始值**：自動套用 `GatewayRegisterDef.initial_value`

---

## Public API

### 命名暫存器存取（物理值）

| 方法 | 說明 |
|------|------|
| `set_value(name, physical_value)` | 設定暫存器值（物理值 x scale 後編碼寫入） |
| `get_value(name)` | 取得暫存器值（解碼後 / scale 還原為物理值） |
| `get_all_values()` | 取得所有暫存器 `{name: physical_value}` |

### 原始暫存器存取

| 方法 | 說明 |
|------|------|
| `get_hr_raw(address, count)` | 讀取 Holding Register 原始 16-bit 值 |
| `set_hr_raw(address, values)` | 寫入 Holding Register 原始值 |
| `get_ir_raw(address, count)` | 讀取 Input Register 原始 16-bit 值 |

### 查詢方法

| 方法 | 說明 |
|------|------|
| `find_affected_registers(address, count, register_type)` | 找出受 raw write 影響的暫存器定義 |
| `get_register_def(name)` | 依名稱查詢暫存器定義 |

### Properties

| 屬性 | 型別 | 說明 |
|------|------|------|
| `register_defs` | `dict[str, GatewayRegisterDef]` | 所有暫存器定義（shallow copy） |
| `default_byte_order` | `ByteOrder` | 伺服器預設 byte order |
| `default_register_order` | `RegisterOrder` | 伺服器預設 register order |

---

## Scale Factor

暫存器值在儲存時套用 scale factor：

```
stored_value = physical_value * scale
physical_value = stored_value / scale
```

例如 SOC 以 0.1% 精度儲存：`scale=10`，物理值 75.5% 存為 755。

對於整數型 Modbus 資料型別，scaled 結果會四捨五入至最近整數。

---

## 執行緒安全

所有 public method 內部使用 `threading.Lock`，確保 pymodbus server thread 與 asyncio event loop 之間的安全存取。

---

## Quick Example

```python
from csp_lib.modbus import UInt16, Int32
from csp_lib.modbus_gateway import (
    GatewayServerConfig,
    GatewayRegisterDef,
    RegisterType,
    GatewayRegisterMap,
)

config = GatewayServerConfig()
defs = [
    GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING, unit="kW"),
    GatewayRegisterDef("soc", 100, UInt16(), RegisterType.INPUT, scale=10, unit="%"),
]

reg_map = GatewayRegisterMap(config, defs)

# 寫入物理值（自動 encode + scale）
reg_map.set_value("soc", 75.5)
assert reg_map.get_value("soc") == 75.5

# 原始暫存器值 = 75.5 * 10 = 755
raw = reg_map.get_ir_raw(100, 1)
assert raw == [755]

# 查詢暫存器定義
reg_def = reg_map.get_register_def("p_command")
assert reg_def.register_type == RegisterType.HOLDING
```

---

## 相關頁面

- [[GatewayConfig]] -- `GatewayRegisterDef` 與 `GatewayServerConfig` 定義
- [[ModbusGatewayServer]] -- 使用 RegisterMap 的主 orchestrator
- [[WriteValidation]] -- `WritePipeline` 依賴 RegisterMap 進行寫入處理
