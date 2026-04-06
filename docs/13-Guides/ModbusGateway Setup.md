---
tags:
  - type/guide
  - layer/modbus-gateway
  - status/complete
created: 2026-04-06
updated: 2026-04-06
version: ">=0.7.1"
---

# ModbusGateway 設定指南

本指南說明如何使用 [[ModbusGatewayServer]] 將 csp_lib 控制系統的狀態暴露給外部 EMS/SCADA，並接收 EMS 的功率命令寫入。

---

## 概觀

`ModbusGatewayServer` 是一個 Modbus TCP Server，讓外部 EMS 或 SCADA 能透過標準 Modbus TCP 協定：
- **讀取**系統狀態（SOC、功率量測等）— 透過 Input Registers (FC04)
- **寫入**控制命令（功率設定點等）— 透過 Holding Registers (FC03/FC06/FC16)

典型使用場景：

```
EMS / SCADA  ←── Modbus TCP ──→  ModbusGatewayServer  ←──→  csp_lib SystemController
                                      ↑
                         (暴露 soc, p_meas 等狀態)
                         (接收 p_command, mode 等命令)
```

> [!info] 依賴安裝
> ModbusGateway 需要 `modbus` 可選依賴：
> ```bash
> pip install csp0924_lib[modbus]
> ```

---

## Quick Example

以下是一個完整的最小可運行範例，包含 Holding Register 接收命令與 Input Register 回報狀態：

```python
import asyncio
from csp_lib.modbus import UInt16, Int32
from csp_lib.modbus_gateway import (
    GatewayServerConfig,
    GatewayRegisterDef,
    ModbusGatewayServer,
    RegisterType,
    CallbackHook,
    PollingCallbackSource,
)


async def on_ems_write(name: str, old: float, new: float) -> None:
    """EMS 寫入命令時的回呼"""
    print(f"[EMS 命令] {name}: {old} kW → {new} kW")


async def read_device_status() -> dict[str, float]:
    """模擬從設備讀取當前狀態（實際應從 DeviceRegistry 取值）"""
    return {"soc": 75.5, "p_meas": 480.0}


async def main() -> None:
    # 1. 定義 Register 空間
    registers = [
        # Holding Registers — EMS 可讀寫
        GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING, unit="kW"),
        GatewayRegisterDef("q_command", 2, Int32(), RegisterType.HOLDING, unit="kVar"),
        # Input Registers — EMS 唯讀
        GatewayRegisterDef("soc", 100, UInt16(), RegisterType.INPUT, scale=10, unit="%"),
        GatewayRegisterDef("p_meas", 102, Int32(), RegisterType.INPUT, unit="kW"),
    ]

    # 2. 建立伺服器設定
    config = GatewayServerConfig(host="0.0.0.0", port=502, unit_id=1)

    # 3. 啟動 Gateway
    async with ModbusGatewayServer(
        config,
        registers,
        hooks=[CallbackHook(on_ems_write)],
        sync_sources=[PollingCallbackSource(read_device_status, interval=1.0)],
    ) as gw:
        print(f"Gateway 已啟動：{config.host}:{config.port}")
        await gw.serve()


asyncio.run(main())
```

---

## 設定詳解

### GatewayServerConfig

伺服器基本設定。

```python
from csp_lib.modbus_gateway import GatewayServerConfig, WatchdogConfig

config = GatewayServerConfig(
    host="0.0.0.0",           # 綁定 IP（預設 0.0.0.0 = 所有介面）
    port=502,                  # TCP Port（預設 502）
    unit_id=1,                 # Modbus Slave ID，範圍 1~247
    byte_order=ByteOrder.BIG_ENDIAN,      # 預設位元組順序
    register_order=RegisterOrder.HIGH_FIRST,  # 預設暫存器順序
    register_space_size=10000, # 位址空間總大小（預設 10000）
    watchdog=WatchdogConfig(
        timeout_seconds=60.0,  # 無通訊超時時間（秒）
        check_interval=5.0,    # 檢查間隔（秒）
        enabled=True,          # 是否啟用
    ),
)
```

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `host` | `str` | `"0.0.0.0"` | 綁定 IP 位址 |
| `port` | `int` | `502` | TCP 通訊埠 |
| `unit_id` | `int` | `1` | Modbus Slave ID（1–247） |
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 全域位元組順序 |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 全域暫存器順序 |
| `register_space_size` | `int` | `10000` | 位址空間大小 |
| `watchdog` | `WatchdogConfig` | 見下方 | 通訊看門狗設定 |

### GatewayRegisterDef

定義單一暫存器的邏輯名稱、位址、型別與讀寫屬性。

```python
from csp_lib.modbus import Float32, Int32, UInt16
from csp_lib.modbus_gateway import GatewayRegisterDef, RegisterType

GatewayRegisterDef(
    name="p_command",           # 邏輯名稱（唯一）
    address=0,                  # 起始 Modbus 位址（0-based）
    data_type=Int32(),          # 資料型別（與 csp_lib.modbus 一致）
    register_type=RegisterType.HOLDING,  # HOLDING = 讀寫，INPUT = 唯讀
    scale=1.0,                  # 縮放係數（物理值 = raw / scale）
    unit="kW",                  # 工程單位（僅記錄用）
    initial_value=0,            # 初始值
    description="EMS 功率設定點",
)
```

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `name` | `str` | 必填 | 邏輯名稱（全域唯一） |
| `address` | `int` | 必填 | 起始位址（0-based） |
| `data_type` | `ModbusDataType` | 必填 | 編碼型別 |
| `register_type` | `RegisterType` | `HOLDING` | 讀寫或唯讀 |
| `scale` | `float` | `1.0` | 縮放係數（不可為 0） |
| `unit` | `str` | `""` | 工程單位字串 |
| `initial_value` | `Any` | `0` | 初始物理值 |
| `description` | `str` | `""` | 說明 |
| `byte_order` | `ByteOrder \| None` | `None` | 覆蓋全域 byte_order |
| `register_order` | `RegisterOrder \| None` | `None` | 覆蓋全域 register_order |

> [!note] scale 的語意
> `scale` 定義物理值到 raw 整數的映射：
> - `scale=10` → 物理值 75.5% 寫入 raw 755
> - `scale=0.1` → 物理值 480.0 kW 寫入 raw 48000
>
> EMS 讀到的是 raw 整數，需自行按 scale 換算物理值。

---

## 資料同步（DataSyncSource）

DataSyncSource 負責將外部資料（設備狀態）定期同步到 Input Registers。

### PollingCallbackSource

定期呼叫 async callback 取得 `{register_name: value}` 字典並更新暫存器：

```python
from csp_lib.modbus_gateway import PollingCallbackSource

async def get_latest_values() -> dict[str, float]:
    # 實際應從 DeviceRegistry 取值
    return {
        "soc": device_registry.get("bms").latest_values.get("soc", 0.0),
        "p_meas": device_registry.get("pcs").latest_values.get("active_power", 0.0),
    }

source = PollingCallbackSource(get_latest_values, interval=1.0)

# 建立時傳入
async with ModbusGatewayServer(config, registers, sync_sources=[source]) as gw:
    ...

# 或事後新增
gw.add_sync_source(source)
```

### RedisSubscriptionSource

訂閱 Redis channel，從 JSON 訊息更新暫存器：

```python
import redis.asyncio as aioredis
from csp_lib.modbus_gateway import RedisSubscriptionSource

redis_client = aioredis.from_url("redis://localhost:6379")
source = RedisSubscriptionSource(redis_client, channel="gateway:sync")

# 發佈端格式（3 種均支援）
# 單筆：{"register": "soc", "value": 75.5}
# 批次：[{"register": "soc", "value": 75.5}, {"register": "p_meas", "value": 480.0}]
# 簡潔：{"soc": 75.5, "p_meas": 480.0}   (batch_mode=True 時)
```

> [!tip] 與 csp_lib Redis 整合
> 若已使用 `StateSyncManager` 將設備值同步到 Redis，可直接訂閱同一 channel 避免重複輪詢：
> ```python
> RedisSubscriptionSource(redis_client, channel="device:state")
> ```

---

## 寫入驗證（WriteValidation）

所有 Holding Register 的寫入請求都會經過驗證鏈。

### WriteRule（範圍驗證）

在建立 `ModbusGatewayServer` 時傳入 `write_rules` dict 定義每個暫存器的允許範圍：

```python
from csp_lib.modbus_gateway import WriteRule

async with ModbusGatewayServer(
    config,
    registers,
    write_rules={
        "p_command": WriteRule(
            register_name="p_command",
            min_value=-2000.0,  # kW
            max_value=2000.0,
            clamp=True,         # True = 超出範圍自動夾緊，False = 拒絕寫入
        ),
        "q_command": WriteRule(
            register_name="q_command",
            min_value=-500.0,
            max_value=500.0,
            clamp=False,        # 超出範圍直接拒絕
        ),
    },
) as gw:
    ...
```

### WriteHook（寫入後通知）

WriteHook 在寫入成功後觸發，適合記錄、轉發命令或狀態持久化：

**CallbackHook** — 最彈性，使用 async callback：

```python
from csp_lib.modbus_gateway import CallbackHook

async def handle_command(name: str, old: float, new: float) -> None:
    if name == "p_command":
        await system_controller.manual_set_p(new)

gw.add_hook(CallbackHook(handle_command))
```

**RedisPublishHook** — 寫入事件發布到 Redis channel：

```python
from csp_lib.modbus_gateway import RedisPublishHook

# 發布格式：{"register": "p_command", "old": 0, "new": 500, "ts": 1234567890.0}
gw.add_hook(RedisPublishHook(redis_client, channel="gateway:writes"))
```

**StatePersistHook** — 重啟後自動恢復 Holding Register 狀態：

```python
from csp_lib.modbus_gateway import StatePersistHook

# 寫入時自動儲存到 Redis Hash，重啟時自動恢復
persist_hook = StatePersistHook(redis_client, server_name="main_gw")
# Gateway 啟動時會自動呼叫 restore_all()
gw.add_hook(persist_hook)
```

> [!warning] StatePersistHook 順序
> `StatePersistHook` 必須在 `ModbusGatewayServer` 啟動前（`async with` 之前）或
> 在建構函式的 `hooks=` 中傳入，才能在 `_on_start` 時正確恢復狀態。
> 使用 `gw.add_hook()` 在 `async with` 進入後添加，仍可接收後續寫入通知，但不會觸發恢復流程。

---

## Watchdog 設定

Watchdog 監控 EMS 通訊活躍度，若超時可觸發保護動作：

```python
from csp_lib.modbus_gateway import WatchdogConfig

config = GatewayServerConfig(
    ...
    watchdog=WatchdogConfig(
        timeout_seconds=30.0,  # 30 秒無通訊 → 超時
        check_interval=5.0,    # 每 5 秒檢查一次
        enabled=True,
    ),
)

# 監聽超時事件
async with ModbusGatewayServer(config, registers) as gw:
    gw.watchdog.on_timeout(async_timeout_callback)
    await gw.serve()
```

> [!tip] 超時處理建議
> 超時發生時，建議透過 `CallbackHook` 或 watchdog 回呼通知 `SystemController` 切換到停機模式，
> 避免 EMS 失聯後系統維持最後命令無限運行。

---

## 完整整合範例

以下範例展示 ModbusGatewayServer 與 SystemController 的完整整合，包含：
- EMS 命令寫入後轉發給 SystemController
- 系統狀態每秒同步到 Input Registers
- 狀態持久化（重啟恢復）

```python
import asyncio
import redis.asyncio as aioredis
from csp_lib.modbus import UInt16, Int32, Float32
from csp_lib.modbus_gateway import (
    GatewayServerConfig,
    GatewayRegisterDef,
    ModbusGatewayServer,
    RegisterType,
    CallbackHook,
    PollingCallbackSource,
    StatePersistHook,
    WriteRule,
    WatchdogConfig,
)


async def run_gateway(system_controller, device_registry):
    redis_client = aioredis.from_url("redis://localhost:6379")

    registers = [
        # Holding — EMS 命令
        GatewayRegisterDef("p_command", 0, Int32(), RegisterType.HOLDING, unit="kW"),
        GatewayRegisterDef("q_command", 2, Int32(), RegisterType.HOLDING, unit="kVar"),
        GatewayRegisterDef("mode", 4, UInt16(), RegisterType.HOLDING),
        # Input — 狀態回報
        GatewayRegisterDef("soc",   100, UInt16(), RegisterType.INPUT, scale=10, unit="%"),
        GatewayRegisterDef("p_meas", 102, Int32(),  RegisterType.INPUT, unit="kW"),
        GatewayRegisterDef("q_meas", 104, Int32(),  RegisterType.INPUT, unit="kVar"),
        GatewayRegisterDef("status", 106, UInt16(), RegisterType.INPUT),
    ]

    async def on_write(name: str, old: float, new: float) -> None:
        if name == "p_command":
            await system_controller.override_p_command(new)
        elif name == "mode":
            await system_controller.set_mode_by_id(int(new))

    async def poll_status() -> dict[str, float]:
        bms = device_registry.get("bms_001")
        pcs = device_registry.get("pcs_001")
        return {
            "soc":    bms.latest_values.get("soc", 0.0),
            "p_meas": pcs.latest_values.get("active_power", 0.0),
            "q_meas": pcs.latest_values.get("reactive_power", 0.0),
            "status": 1 if pcs.is_responsive else 0,
        }

    config = GatewayServerConfig(
        port=502,
        watchdog=WatchdogConfig(timeout_seconds=30.0),
    )

    async with ModbusGatewayServer(
        config,
        registers,
        write_rules={
            "p_command": WriteRule("p_command", min_value=-2000.0, max_value=2000.0, clamp=True),
            "q_command": WriteRule("q_command", min_value=-500.0, max_value=500.0, clamp=True),
        },
        hooks=[
            CallbackHook(on_write),
            StatePersistHook(redis_client, server_name="main"),
        ],
        sync_sources=[PollingCallbackSource(poll_status, interval=1.0)],
    ) as gw:
        print("ModbusGateway 已啟動，等待 EMS 連線...")
        await gw.serve()
```

---

## 常見問題

### Q: 如何同時運行 Gateway 與 SystemController？

使用 `asyncio.gather` 同時啟動兩個 `serve()` 迴圈：

```python
async with system_controller, gateway:
    await asyncio.gather(
        system_controller.run(),
        gateway.serve(),
    )
```

### Q: EMS 讀取的是 raw 值還是物理值？

EMS 讀取的是 **raw 整數**。若 `scale=10`，EMS 讀到 755 表示物理值 75.5。
EMS 端需按 scale 自行換算，或在 Gateway 設定中將 scale 設為 `1.0` 直接傳物理整數。

### Q: 如何防止 EMS 寫入超出安全範圍的值？

使用 `WriteRule` 的 `clamp=True` 自動夾緊，或 `clamp=False` 直接拒絕寫入：

```python
write_rules={
    "p_command": WriteRule("p_command", min_value=-2000.0, max_value=2000.0, clamp=False),
}
```

---

## 相關頁面

- [[ModbusGatewayServer]] — 主類別 API 參考
- [[GatewayConfig]] — 所有組態類別詳細說明
- [[RegisterMap]] — 暫存器位址空間管理
- [[WriteValidation]] — 寫入驗證鏈
- [[SyncSources]] — 資料同步來源
- [[_MOC ModbusGateway]] — 模組索引
