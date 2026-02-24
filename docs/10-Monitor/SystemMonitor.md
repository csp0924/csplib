---
tags:
  - type/class
  - layer/monitor
  - status/complete
source: csp_lib/monitor/manager.py
created: 2026-02-17
---

# SystemMonitor

> 系統監控器（主入口）

`SystemMonitor` 是 Monitor 模組的主入口類別，繼承自 `AsyncLifecycleMixin`。它整合指標收集、告警評估、模組健康檢查、Redis 發布與通知分發，以固定間隔定期執行監控週期。

---

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `redis_client` | `RedisClient \| None` | `None` | Redis 客戶端（用於發布指標） |
| `dispatcher` | `NotificationDispatcher \| None` | `None` | 通知分發器（用於發送告警通知） |
| `config` | `MonitorConfig \| None` | `None` | 監控配置（預設使用 `MonitorConfig()`） |

---

## 屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `is_running` | `bool` | 是否正在運行 |
| `active_alarms` | `list[str]` | 活躍告警代碼列表 |
| `last_metrics` | `SystemMetrics \| None` | 最近一次系統指標 |
| `last_module_health` | `ModuleHealthSnapshot \| None` | 最近一次模組健康快照 |

---

## 方法

| 方法 | 說明 |
|------|------|
| `start()` | 啟動監控迴圈 |
| `stop()` | 停止監控迴圈 |
| `register_module(name, module)` | 註冊 `HealthCheckable` 模組 |
| `register_check(name, check_fn)` | 註冊自訂健康檢查函式 |
| `health()` | 回報監控器自身健康狀態（`HealthReport`） |

---

## 監控週期（_tick）

每次 tick 依序執行：

1. **收集系統指標** -- `SystemMetricsCollector.collect()`
2. **評估告警** -- `SystemAlarmEvaluator.evaluate(metrics)`
3. **發布指標至 Redis** -- `RedisMonitorPublisher.publish_metrics()`
4. **處理告警事件** -- 發布至 Redis + 透過 `NotificationDispatcher` 發送通知
5. **收集模組健康** -- `ModuleHealthCollector.collect()`，發布至 Redis

---

## 程式碼範例

```python
from csp_lib.monitor import SystemMonitor, MonitorConfig

monitor = SystemMonitor(
    config=MonitorConfig(interval_seconds=5.0),
    redis_client=redis,
    dispatcher=dispatcher,
)

# 註冊 HealthCheckable 模組
monitor.register_module("device_manager", device_manager)
monitor.register_check("redis", redis_health_check)

async with monitor:
    await asyncio.Event().wait()
```

---

## 相關頁面

- [[MonitorConfig]] -- 監控配置
- [[SystemMetricsCollector]] -- 指標收集與元件一覽
- [[NotificationDispatcher]] -- 通知分發器
- [[_MOC Monitor]] -- 模組總覽
