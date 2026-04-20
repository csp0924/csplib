---
tags:
  - type/class
  - layer/alarm
  - status/complete
source: csp_lib/alarm/aggregator.py
created: 2026-04-17
updated: 2026-04-17
version: ">=0.8.2"
---

# AlarmAggregator

In-process 事件驅動告警聚合器，多 source OR 聚合。

> [!info] 回到 [[_MOC Alarm]]

## 概述

`AlarmAggregator` 維護一組「告警 source」的 active 狀態。聚合語義為 **OR**：任意一個 source active，整體旗標即為 `True`；所有 source 皆 cleared 才回到 `False`。旗標每次由 `False→True` 或 `True→False` 時，同步觸發所有已登錄的 `on_change` callback。

典型使用情境：

- **多站聯動停機**：本機任何設備告警或 gateway watchdog timeout → `AlarmAggregator` 偵測到 → `RedisAlarmPublisher` 發佈到 `channel:gateway:alarm` → 其他 node 的 `RedisAlarmSource` 注入 → 各自 `AlarmAggregator` 旗標變化 → 整廠停機
- **本機 in-process 策略鎖定**：`on_change` 直接呼叫 `mode_manager.push_override(...)` 強制 RampStop

### Thread Safety

內部使用 `threading.Lock` 保護 `_active_sources` 與 `_observers`。Callback 在 lock 釋放後以快照呼叫，避免 observer 回呼期間重進 aggregator 造成死鎖。

---

## Quick Example

```python
from csp_lib.alarm import AlarmAggregator

agg = AlarmAggregator()

# 綁定 Modbus 設備（任一 alarm_triggered → source active）
agg.bind_device(device_a)                          # name = device_a.device_id
agg.bind_device(device_b, name="pcs_b")

# 綁定 CommunicationWatchdog（timeout → source active）
agg.bind_watchdog(watchdog, name="gateway_wd")

# 訂閱聚合旗標變化（同步 callback）
def _on_alarm_change(active: bool) -> None:
    if active:
        import asyncio
        asyncio.create_task(mode_manager.push_override("stop"))
    else:
        asyncio.create_task(mode_manager.pop_override("stop"))

agg.on_change(_on_alarm_change)

# 手動注入（RedisAlarmSource 使用）
agg.mark_source("remote_node_1", True)

# 查詢
print(agg.active)           # True / False
print(agg.active_sources)   # {'pcs_b', 'gateway_wd', 'remote_node_1'}

# 解除綁定
agg.unbind("pcs_b")
```

---

## Common Patterns

### 多站同步範例：單廠本機 + Redis 跨 node

```python
from csp_lib.alarm import AlarmAggregator, WatchdogProtocol
from csp_lib.alarm import RedisAlarmPublisher, RedisAlarmSource

# 本機聚合器
local_agg = AlarmAggregator()
local_agg.bind_device(pcs_device)
local_agg.bind_watchdog(comm_watchdog, name="gateway_wd")

# 跨 node：發佈到 Redis
publisher = RedisAlarmPublisher(local_agg, redis_client, channel="gateway:alarm")

# 跨 node：接收其他 node 的告警
remote_agg = AlarmAggregator()
source = RedisAlarmSource(remote_agg, redis_client, channel="gateway:alarm", name="node_2")

# 最終決策聚合器（本機 + 遠端）
final_agg = AlarmAggregator()
local_agg.on_change(lambda active: final_agg.mark_source("local", active))
remote_agg.on_change(lambda active: final_agg.mark_source("node_2", active))

async with publisher, source:
    # 整廠運行...
    pass
```

### 與 EventDrivenOverride 搭配

```python
# on_change 在 asyncio event loop 內執行時，可直接 create_task
def _alarm_handler(active: bool) -> None:
    import asyncio
    if active:
        asyncio.create_task(mode_manager.push_override("ramp_stop"))
    else:
        asyncio.create_task(mode_manager.pop_override("ramp_stop"))

agg.on_change(_alarm_handler)
```

---

## Gotchas / Tips

> [!warning] enabled_key 後的 async callback
> `on_change` callback 是**同步**函式。若需執行 async 操作（如寫設備點位），必須在 callback 內使用 `asyncio.create_task()`，且需確認當下有 running event loop。

> [!note] watchdog 無原生 unbind
> `bind_watchdog` 透過 captured flag 實作「軟取消」：呼叫 `unbind()` 後 watchdog 回呼仍可能被觸發，但會立即 return 不更新 aggregator 狀態。若需精確 unbind，應改用具備 unbind 機制的 watchdog 實作。

> [!tip] 同名重綁
> `bind_device` / `bind_watchdog` 若傳入相同 name，會自動先 unbind 舊 source 再重綁。不需手動呼叫 `unbind`。

---

## API Reference

### 建構

| 方法 | 說明 |
|------|------|
| `AlarmAggregator()` | 無參數建構；內部 lock 與 observer list 初始化 |

### 綁定方法

| 方法 | 說明 |
|------|------|
| `bind_device(device, *, name=None)` | 訂閱 device 的 `alarm_triggered` / `alarm_cleared` 事件；name 省略時使用 `device.device_id` |
| `bind_watchdog(watchdog, *, name)` | 訂閱 `WatchdogProtocol.on_timeout` / `on_recover`；name 必填 |
| `unbind(name)` | 移除 source；觸發旗標重算；不存在則靜默忽略 |
| `mark_source(name, active)` | 外部直接設定 source 狀態（供 `RedisAlarmSource` 等自訂來源使用） |

### Observer 方法

| 方法 | 說明 |
|------|------|
| `on_change(callback)` | 註冊 `AlarmChangeCallback`，旗標真正變化時觸發 |
| `remove_observer(callback)` | 移除 callback；不存在則靜默忽略 |

### Properties

| 屬性 | 型別 | 說明 |
|------|------|------|
| `active` | `bool` | 當前聚合旗標（OR 語義） |
| `active_sources` | `set[str]` | 目前 active 的 source 名稱快照（copy） |

---

## 相關連結

- [[_MOC Alarm]] — Alarm 模組索引
- [[Redis Adapter]] — `RedisAlarmPublisher` / `RedisAlarmSource`
- [[WatchdogProtocol]] — 本頁段落：protocols
- [[CommunicationWatchdog]] — Modbus Gateway 通訊看門狗
- [[AsyncLifecycleMixin]] — publisher/source 的生命週期基類
