---
tags:
  - type/class
  - layer/modbus-gateway
  - status/complete
source: csp_lib/modbus_gateway/registry_sync_source.py
created: 2026-04-17
updated: 2026-04-17
version: ">=0.8.2"
---

# RegistryAggregatingSource

> [!info] v0.8.2 新增

> [!info] 回到 [[_MOC ModbusGateway]]

`DataSyncSource` 實作：從 `DeviceRegistry` 聚合設備讀值，自動寫入 Modbus Gateway register。每 `interval` 秒輪詢一次，可選擇將聚合結果同步回 `RuntimeParameters`，讓 strategy 即時反映設備群體狀態。

---

## Quick Example

```python
from csp_lib.modbus_gateway import (
    RegistryAggregatingSource,
    RegisterAggregateMapping,
    AggregateFunc,
)

# 場景：聚合 3 台 BMS 的 SOC 平均值，寫入 gateway register "avg_soc"
mappings = [
    RegisterAggregateMapping(
        register="avg_soc",
        trait="bms",                    # 取出所有 trait="bms" 的設備
        point="soc",                    # 讀取 latest_values["soc"]
        aggregate=AggregateFunc.AVERAGE,
        offline_fallback=50.0,          # 全部離線時寫 50.0
        writable_param="fleet_soc",     # 同步回 RuntimeParameters["fleet_soc"]
    ),
    RegisterAggregateMapping(
        register="total_power",
        trait="bms",
        point="power",
        aggregate=AggregateFunc.SUM,    # 加總功率
        offline_fallback=None,          # 全部離線時本週期跳過
    ),
]

source = RegistryAggregatingSource(
    registry=registry,
    mappings=mappings,
    interval=2.0,
    params=params,                      # 有 writable_param 時必填
)

async with ModbusGatewayServer(config, registers, data_sync_sources=[source]) as gw:
    await gw.serve()
```

---

## Common Patterns

### 聚合 SOC → 回寫 RuntimeParameters → DroopStrategy 動態調整

```python
# 1. 聚合結果寫回 params["fleet_soc"]
source = RegistryAggregatingSource(
    registry,
    [RegisterAggregateMapping("avg_soc", "bms", "soc",
                               writable_param="fleet_soc")],
    params=params,
)

# 2. DroopStrategy 透過 param_keys 讀取（v0.8.2 動態化）
strategy = DroopStrategy(
    config,
    params=params,
    param_keys={"rated_power": "fleet_rated_p"},
)
```

### 自訂聚合函式

```python
from csp_lib.modbus_gateway import AggregateCallable

def weighted_avg(values: list[float]) -> float:
    """加權平均示例（假設所有設備同權重）"""
    return sum(values) / len(values) if values else 0.0

mapping = RegisterAggregateMapping(
    register="custom_avg",
    trait="pcs",
    point="output_power",
    aggregate=weighted_avg,   # AggregateCallable
)
```

---

## Gotchas / Tips

> [!warning] 僅允許寫入 INPUT registers
> `RegistryAggregatingSource` 走 `update_callback`，從 v0.7.3 起對 HOLDING register 寫入會拋 `PermissionError`（降級為 warning log，不中止服務）。聚合結果請確保對應到 INPUT register 定義。

> [!note] `offline_fallback=None` 的語義
> 當 trait 下所有設備均 `is_responsive=False` 或 `latest_values` 均不含 `point` 時，若 `offline_fallback=None`，本週期該 mapping **完全跳過**（不呼叫 update_callback，gateway register 維持上次值）。若需要明確清零，請設 `offline_fallback=0.0`。

> [!tip] `writable_param` 需提供 `params`
> 若 `RegisterAggregateMapping.writable_param` 設定但 `RegistryAggregatingSource(params=None)`，回寫步驟會靜默跳過（log at WARNING）。

---

## API Reference

### `RegistryAggregatingSource`

```python
class RegistryAggregatingSource:
    def __init__(
        self,
        registry: DeviceRegistry,
        mappings: list[RegisterAggregateMapping],
        interval: float = 1.0,
        params: RuntimeParameters | None = None,
    ) -> None: ...

    async def start(self, update_callback: UpdateRegisterCallback) -> None: ...
    async def stop(self) -> None: ...
```

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `registry` | `DeviceRegistry` | — | 設備登錄中心 |
| `mappings` | `list[RegisterAggregateMapping]` | — | 聚合映射定義列表 |
| `interval` | `float` | `1.0` | 輪詢週期（秒） |
| `params` | `RuntimeParameters \| None` | `None` | 用於 `writable_param` 回寫；None 時忽略回寫 |

---

### `RegisterAggregateMapping`

`@dataclass(frozen=True, slots=True)`

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `register` | `str` | — | 目標 gateway register 邏輯名稱 |
| `trait` | `str` | — | 設備 trait 標籤（決定聚合來源設備集合） |
| `point` | `str` | — | 設備 `latest_values` 的 key 名稱 |
| `aggregate` | `AggregateFunc \| AggregateCallable` | `AggregateFunc.AVERAGE` | 聚合函式 |
| `offline_fallback` | `float \| None` | `None` | 全設備離線時的回退值；None 則本週期跳過 |
| `writable_param` | `str \| None` | `None` | 聚合結果回寫的 `RuntimeParameters` key |

---

### `AggregateFunc`

```python
class AggregateFunc(Enum):
    AVERAGE = "average"
    SUM     = "sum"
    MIN     = "min"
    MAX     = "max"
```

---

### `AggregateCallable`

```python
AggregateCallable = Callable[[list[float]], float]
```

輸入為已過濾 None 的 float 列表（保證非空時才呼叫），回傳單一 float。

---

## 聚合邏輯

每個 mapping 的處理步驟：

1. `registry.get_devices_by_trait(trait)` 取得設備列表
2. 篩選 `is_responsive=True` 且 `latest_values` 包含 `point` 的設備
3. 將 `latest_values[point]` 轉型為 `float`；轉型失敗的項目跳過
4. 若 `values` 非空 → 套 `aggregate` 得 `result`
5. 若 `values` 為空且 `offline_fallback is not None` → `result = offline_fallback`
6. 若 `values` 為空且 `offline_fallback is None` → 本週期跳過此 mapping
7. `await update_callback(register, result)`
8. 若 `writable_param` 設且 `params` 非 None → `params.set(writable_param, result)`

**錯誤隔離**：自訂 `aggregate` callable 拋例外 → warning log，該 mapping 本週期跳過，其他 mapping 繼續執行。

---

## 相關頁面

- [[SyncSources]] — 其他 DataSyncSource 實作（Redis/Polling）
- [[ModbusGatewayServer]] — 管理 RegistryAggregatingSource 生命週期
- [[RegisterMap]] — 透過 update_callback 更新的暫存器空間
- [[DeviceRegistry]] — 提供設備列表的登錄中心
- [[DroopStrategy]] — 透過 `writable_param` + `param_keys` 動態調整下垂控制
