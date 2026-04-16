---
tags:
  - type/class
  - layer/modbus-gateway
  - status/complete
source: csp_lib/modbus_gateway/config.py
updated: 2026-04-16
version: ">=0.7.3"
---

# GatewayConfig

> [!info] v0.5.0 新增

ModbusGateway 的組態類別，全部採用 `@dataclass(frozen=True, slots=True)` 不可變模式。

來源：`csp_lib/modbus_gateway/config.py`

---

## RegisterType

暫存器類型列舉，決定讀寫能力。

```python
class RegisterType(Enum):
    HOLDING = "holding"  # 讀寫（FC03 / FC06 / FC16）
    INPUT = "input"      # 唯讀（FC04）
```

| 值 | Modbus Function Code | 說明 |
|---|---|---|
| `HOLDING` | FC03 (read), FC06/FC16 (write) | EMS 可讀可寫的指令暫存器 |
| `INPUT` | FC04 (read) | EMS 唯讀的狀態暫存器 |

---

## GatewayRegisterDef

單一暫存器定義，描述邏輯名稱到 Modbus 位址的映射。

```python
@dataclass(frozen=True, slots=True)
class GatewayRegisterDef:
    name: str
    address: int
    data_type: ModbusDataType
    register_type: RegisterType = RegisterType.HOLDING
    scale: float = 1.0
    unit: str = ""
    initial_value: Any = 0
    description: str = ""
    byte_order: ByteOrder | None = None
    register_order: RegisterOrder | None = None
    writable: bool = False          # v0.7.3 SEC-006
```

### 欄位說明

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `name` | `str` | -- | 唯一邏輯名稱（如 `"p_command"`, `"soc"`） |
| `address` | `int` | -- | Modbus 起始位址（0-based） |
| `data_type` | [[_MOC Modbus\|ModbusDataType]] | -- | 資料型別實例（`UInt16()`, `Int32()`, `Float32()` 等） |
| `register_type` | `RegisterType` | `HOLDING` | 暫存器類型 |
| `scale` | `float` | `1.0` | 比例因子：`stored = physical * scale`（不可為 0） |
| `unit` | `str` | `""` | 工程單位（如 `"kW"`, `"Hz"`, `"%"`） |
| `initial_value` | `Any` | `0` | 初始化值（物理值） |
| `description` | `str` | `""` | 人類可讀描述 |
| `byte_order` | `ByteOrder \| None` | `None` | 覆寫伺服器預設 byte order |
| `register_order` | `RegisterOrder \| None` | `None` | 覆寫伺服器預設 register order |
| `writable` | `bool` | `False` | EMS 是否可寫入此暫存器（v0.7.3 SEC-006）。僅對 HOLDING register 有效；INPUT register 在 Modbus 協定層本身即為唯讀 |

> [!warning] v0.7.3 行為變更 (SEC-006)
> `writable` 預設為 `False`。升級前所有 HOLDING register 隱式可寫，升級後必須明確設 `writable=True` 才允許 EMS 寫入。
> 未設 `writable=True` 的 register 在 EMS 嘗試寫入時會收到 `RegisterNotWritableError`。

### 驗證規則

- `address >= 0`
- `scale != 0`

### Quick Example

```python
from csp_lib.modbus import UInt16, Int32, Float32
from csp_lib.modbus_gateway import GatewayRegisterDef, RegisterType

# Holding Register — 明確 opt-in 允許 EMS 寫入的有功功率指令（v0.7.3 需加 writable=True）
p_cmd = GatewayRegisterDef(
    name="p_command",
    address=0,
    data_type=Int32(),
    register_type=RegisterType.HOLDING,
    unit="kW",
    description="Active power setpoint",
    writable=True,   # v0.7.3+ 必填，否則 EMS 寫入將被拒絕
)

# Holding Register — 不可被 EMS 寫入（預設行為，如版本號暫存器）
version_reg = GatewayRegisterDef(
    name="fw_version",
    address=10,
    data_type=UInt16(),
    register_type=RegisterType.HOLDING,
    # writable=False (預設)
)

# Input Register — EMS 唯讀的電池 SOC（INPUT 本身即為唯讀，writable 無作用）
soc = GatewayRegisterDef(
    name="soc",
    address=100,
    data_type=UInt16(),
    register_type=RegisterType.INPUT,
    scale=10,      # 75.5% 存為 755
    unit="%",
    initial_value=0,
)

# 使用 Float32 的頻率暫存器
freq = GatewayRegisterDef(
    name="frequency",
    address=200,
    data_type=Float32(),
    register_type=RegisterType.INPUT,
    unit="Hz",
    initial_value=60.0,
)
```

---

## WatchdogConfig

通訊看門狗組態，監控 EMS 通訊活動。若超過 `timeout_seconds` 未收到任何讀寫請求，觸發 timeout 回呼。

```python
@dataclass(frozen=True, slots=True)
class WatchdogConfig:
    timeout_seconds: float = 60.0
    check_interval: float = 5.0
    enabled: bool = True
```

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `timeout_seconds` | `float` | `60.0` | 最大閒置時間（秒），須 > 0 |
| `check_interval` | `float` | `5.0` | 檢查間隔（秒），須 > 0 |
| `enabled` | `bool` | `True` | 是否啟用看門狗 |

### CommunicationWatchdog

`CommunicationWatchdog`（`csp_lib/modbus_gateway/watchdog.py`）是非同步通訊看門狗的實作：

```python
watchdog = CommunicationWatchdog(WatchdogConfig(timeout_seconds=30))
watchdog.on_timeout(my_timeout_handler)
watchdog.on_recover(my_recover_handler)
await watchdog.start()

# pymodbus DataBlock 讀寫時自動呼叫：
watchdog.touch()
```

| 方法/屬性 | 說明 |
|-----------|------|
| `touch()` | 記錄一次通訊事件（thread-safe） |
| `on_timeout(callback)` | 註冊 timeout 回呼（`async () -> None`） |
| `on_recover(callback)` | 註冊通訊恢復回呼（`async () -> None`） |
| `start()` / `stop()` | 啟停檢查迴圈 |
| `is_timed_out` | 是否處於 timeout 狀態 |
| `elapsed` | 距上次通訊的秒數 |

> [!note] thread-safe
> `touch()` 只執行單一 float 賦值，可安全從 pymodbus server thread 呼叫。

---

## GatewayServerConfig

Gateway 伺服器頂層組態。

```python
@dataclass(frozen=True, slots=True)
class GatewayServerConfig:
    host: str = "127.0.0.1"   # v0.7.3 SEC-011：從 "0.0.0.0" 改為僅本機
    port: int = 502
    unit_id: int = 1
    byte_order: ByteOrder = ByteOrder.BIG_ENDIAN
    register_order: RegisterOrder = RegisterOrder.HIGH_FIRST
    register_space_size: int = 10000
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
```

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `host` | `str` | `"127.0.0.1"` | 綁定 IP 位址（v0.7.3 前預設為 `"0.0.0.0"`）。使用 `"0.0.0.0"` 時啟動記錄 WARNING |
| `port` | `int` | `502` | TCP 端口（0-65535） |
| `unit_id` | `int` | `1` | Modbus slave/unit ID（1-247） |
| `byte_order` | `ByteOrder` | `BIG_ENDIAN` | 預設 byte order |
| `register_order` | `RegisterOrder` | `HIGH_FIRST` | 預設 register order（多暫存器型別） |
| `register_space_size` | `int` | `10000` | 暫存器位址空間大小 |
| `watchdog` | `WatchdogConfig` | `WatchdogConfig()` | 看門狗組態 |

> [!warning] v0.7.3 行為變更 (SEC-011)
> `host` 預設從 `"0.0.0.0"` 改為 `"127.0.0.1"`。需要讓外部 EMS 連線的部署必須明確設定：
> ```python
> GatewayServerConfig(host="0.0.0.0", port=502)   # 或指定特定介面 IP
> ```

### 驗證規則

- `1 <= unit_id <= 247`
- `0 <= port <= 65535`

### Quick Example

```python
from csp_lib.modbus import ByteOrder, RegisterOrder
from csp_lib.modbus_gateway import GatewayServerConfig, WatchdogConfig

config = GatewayServerConfig(
    host="192.168.1.100",
    port=5020,
    unit_id=10,
    byte_order=ByteOrder.BIG_ENDIAN,
    register_order=RegisterOrder.HIGH_FIRST,
    register_space_size=20000,
    watchdog=WatchdogConfig(timeout_seconds=30, check_interval=2),
)
```

---

## WriteRule

單一暫存器的寫入約束規則。

```python
@dataclass(frozen=True, slots=True)
class WriteRule:
    register_name: str
    min_value: float | None = None
    max_value: float | None = None
    clamp: bool = False
```

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `register_name` | `str` | -- | 目標暫存器名稱 |
| `min_value` | `float \| None` | `None` | 最小允許值（None = 無下限） |
| `max_value` | `float \| None` | `None` | 最大允許值（None = 無上限） |
| `clamp` | `bool` | `False` | `True` = 超出範圍時截斷；`False` = 超出時拒絕寫入 |

### `apply(name, value)` 方法

回傳 `tuple[float, bool]`：`(processed_value, rejected)`。

```python
rule = WriteRule("power", min_value=-500, max_value=500, clamp=True)
rule.apply("power", 600)   # (500, False)  — clamped
rule.apply("power", 300)   # (300, False)  — pass through

rule = WriteRule("power", min_value=-500, max_value=500, clamp=False)
rule.apply("power", 600)   # (600, True)   — rejected
```

---

## 錯誤類別

來源：`csp_lib/modbus_gateway/errors.py`

| 例外 | 基類 | 說明 |
|------|------|------|
| `GatewayError` | `Exception` | Gateway 模組基礎例外 |
| `RegisterConflictError` | `GatewayError` | 暫存器位址空間重疊（含 `name_a`, `name_b`, `overlap_start`, `overlap_end`） |
| `WriteRejectedError` | `GatewayError` | 寫入被驗證鏈拒絕（含 `address`, `reason`） |
| `RegisterNotWritableError` | `WriteRejectedError` | EMS 嘗試寫入 `writable=False` 的 HOLDING register（v0.7.3 SEC-006，含 `register_name`, `address`） |

---

## 相關頁面

- [[ModbusGatewayServer]] -- 使用這些組態的主類別
- [[RegisterMap]] -- 使用 `GatewayServerConfig` 與 `GatewayRegisterDef`
- [[WriteValidation]] -- 使用 `WriteRule`
