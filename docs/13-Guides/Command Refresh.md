---
tags:
  - type/guide
  - layer/integration
  - status/complete
created: 2026-04-17
updated: 2026-04-17
version: ">=0.8.1"
---

# Command Refresh（命令刷新服務）

`CommandRefreshService` 是 v0.8.1 引入的 reconciler 服務，解決「控制器下發命令後，設備端卻沒有持續維持在該值」的三類問題。

## 三大問題

### A. 寫入失敗黑洞

`StrategyExecutor` 以固定週期（如 30 s）執行策略、輸出 `Command`。若某個週期內
`CommandRouter._safe_write` 寫入失敗（TCP 抖動、佇列滿、設備 NAK），下一次策略執行前 PCS 端完全收不到目標值更新。若策略輸出未改變（`NO_CHANGE` 或相同值），`CommandRouter.route()` 甚至不會重試。

### B. PCS 業務 watchdog 歸零

SMA / SunGrow / Delta 等品牌 PCS 通常有 5–10 s 的「setpoint watchdog」：若在此時間內未收到新 setpoint，PCS 自動歸零輸出。策略週期若超過此窗口，PCS 就會不斷閃斷。

### C. Gateway 繞過覆蓋

透過 `ModbusGatewayServer` 暴露的 Modbus TCP 介面，EMS / SCADA 可直接對 HOLDING register（如 `p_command`）寫值，繞過 `CommandRouter`。下個策略週期才會蓋回，中間有一段「意圖錯亂」窗口。

## Refresh vs Heartbeat：分工明確

| 服務 | 管理對象 | 寫入內容來源 | 典型點位 |
|------|---------|------------|---------|
| `HeartbeatService` | 心跳 register（存活信號） | `HeartbeatValueGenerator`（toggle/counter）| `heartbeat_reg`、`alive_counter` |
| `CommandRefreshService` | 業務 setpoint | `CommandRouter._last_written`（最近成功寫入值）| `p_command`、`q_command` |

> [!warning] 同一點位不可同時被兩者管
> 若相同的 `(device_id, point_name)` 同時出現在 `HeartbeatMapping` 與 `CommandRouter` 的路由映射，兩個服務會互相覆蓋，導致寫入值不可預測。這屬於配置錯誤，目前不自動偵測，需由使用者確保分工。

## 快速配置

```python
from csp_lib.integration import SystemControllerConfig

config = (
    SystemControllerConfig.builder()
    # 其他配置...
    .map_command(field="p_target", point_name="p_command", trait="pcs")
    .map_command(field="q_target", point_name="q_command", trait="pcs")
    # 啟用 Command Refresh：週期 1 s（< PCS watchdog 5 s）
    .command_refresh(
        interval_seconds=1.0,  # < PCS_watchdog / 2（保守建議）
        enabled=True,
        devices=["pcs1", "pcs2"],  # None = 所有被 CommandRouter 追蹤的設備
    )
    .build()
)
```

`interval_seconds` 建議設為 `PCS_watchdog / 2`，例如 watchdog 5 s → 設 2.0 s。

### 直接使用 CommandRefreshConfig

```python
from csp_lib.integration import CommandRefreshConfig, SystemControllerConfig

config = SystemControllerConfig(
    # ...
    command_refresh=CommandRefreshConfig(
        refresh_interval=2.0,
        enabled=True,
        device_filter=frozenset({"pcs1", "pcs2"}),
    ),
)
```

## 生命週期整合

`SystemController` 啟動順序：

```
StrategyExecutor.start()
  → CommandRefreshService.start()   # refresh 在 executor 存活後才啟動
    → HeartbeatService.start()
```

停止順序（反向）：

```
HeartbeatService.stop()
  → CommandRefreshService.stop()
    → StrategyExecutor.stop()
```

這確保 reconciler 只在設備寫入能力（CommandRouter）存在期間運行。

## 與其他元件的互動

### 與 PowerCompensator

`CommandRefreshService` 直接呼叫 `CommandRouter.try_write_single`，**不觸發**新的 FF 學習循環，也**不經過** `ProtectionGuard` / `PowerCompensator` pipeline。

Refresh 純粹是「把上次業務值重傳一次」，不是新的策略輸出。

```
StrategyExecutor → ProtectionGuard → PowerCompensator → CommandRouter → _last_written
                                                                              ↑
                                              CommandRefreshService 每 interval 秒讀取並重傳
```

### 與 NO_CHANGE sentinel

`NO_CHANGE` 軸（如 QV 策略的 `p_target=NO_CHANGE`）被 `CommandRouter.route()` 跳過，**不會**觸及 `_last_written`。因此 Refresh 永遠送的是最近一次實際業務值，不會把「跳過信號」誤傳為 0。

```python
# 策略輸出 p=NO_CHANGE, q=-500
command = Command(p_target=NO_CHANGE, q_target=-500.0)

# CommandRouter.route() 後：
# _last_written["pcs1"] = {"q_command": -500.0}  ← p 不動，q 記錄

# CommandRefreshService 每 interval：
# await router.try_write_single("pcs1", "q_command", -500.0)  ← 只重傳 q
```

### 與 is_fallback 命令

`StrategyExecutor` 在策略執行例外時回傳 `Command(p_target=0.0, q_target=0.0, is_fallback=True)`。這個 fallback 命令走的是**正常寫入路徑**，因此 `_last_written` 會被更新為 `{p_command: 0.0, q_command: 0.0}`。

Refresh 後續會持續重傳 0，這符合「安全停機語義」：即使策略繼續失敗，PCS 也不會因 watchdog 超時而自行歸零，而是維持在明確的 0。

## API 參考

### CommandRefreshService

```python
class CommandRefreshService(AsyncLifecycleMixin):
    def __init__(
        self,
        router: CommandRouter,
        *,
        interval: float = 1.0,
        device_filter: frozenset[str] | None = None,
    ) -> None: ...
```

| 參數 | 型別 | 說明 |
|------|------|------|
| `router` | `CommandRouter` | 目標路由器，讀取 desired state |
| `interval` | `float` | reconcile 週期（秒），必須 > 0 |
| `device_filter` | `frozenset[str] \| None` | 只 reconcile 這些 device_id；`None` 代表全部 |

| 屬性 | 型別 | 說明 |
|------|------|------|
| `is_running` | `bool` | reconcile task 是否正在執行 |

### CommandRefreshConfig

```python
@dataclass(frozen=True, slots=True)
class CommandRefreshConfig:
    refresh_interval: float = 1.0
    enabled: bool = False
    device_filter: frozenset[str] | None = None
```

> [!note] enabled 預設 False
> `CommandRefreshConfig` 的 `enabled` 預設為 `False`，需明確設為 `True` 或透過 Builder 的
> `.command_refresh(enabled=True)` 才會啟用服務。

### CommandRouter 新增方法（v0.8.1）

| 方法 | 說明 |
|------|------|
| `try_write_single(device_id, point_name, value) -> bool` | 單設備寫入；成功更新 `_last_written`；失敗回傳 `False` |
| `get_last_written(device_id) -> dict[str, Any]` | 回傳指定設備的 desired state snapshot |
| `get_tracked_device_ids() -> frozenset[str]` | 回傳所有被追蹤的 device_id |

## Gotchas

> [!tip] interval 與策略週期的關係
> Refresh 週期應獨立於策略執行週期。策略 30 s 執行一次，但 Refresh 可以 1 s 一次。
> Refresh 不重新計算策略，只是重傳上次已計算的結果。

> [!warning] device_filter 與 CommandRouter 路由映射的對應
> `device_filter` 中的 device_id 應為 `CommandRouter` 實際路由的設備。若設備不在
> `CommandRouter._last_written` 中（例如從未成功寫入），Refresh 對該設備無作用。

> [!note] CommandRefreshService 可獨立使用
> 雖然通常透過 `SystemControllerConfig.command_refresh` 整合，但
> `CommandRefreshService` 本身是獨立的 `AsyncLifecycleMixin`，可在其他情境下直接
> `async with CommandRefreshService(router, interval=1.0) as svc:` 使用。

## 相關頁面

- [[CommandRouter]] — desired state 的來源與寫入執行者
- [[SystemController]] — 生命週期整合點
- [[Reconciliation Pattern]] — Kubernetes reconciler 設計模式說明
- [[SystemController]] — HeartbeatService 透過 `SystemControllerConfig.heartbeat` 整合（與 Refresh 互補）
