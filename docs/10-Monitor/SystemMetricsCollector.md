---
tags:
  - type/class
  - layer/monitor
  - status/complete
source: csp_lib/monitor/collector.py
created: 2026-02-17
---

# SystemMetricsCollector

> CPU/RAM/Disk/Network 指標收集

`SystemMetricsCollector` 使用 `psutil` 收集系統資源指標，包含 CPU 使用率、RAM 用量、磁碟使用率、網路流量與速率。

---

## 核心元件一覽

| 元件 | 來源 | 說明 |
|------|------|------|
| `SystemMetricsCollector` | `csp_lib/monitor/collector.py` | 收集 CPU/RAM/Disk/Network 指標 |
| `SystemMetrics` | `csp_lib/monitor/collector.py` | 系統指標資料結構（frozen dataclass） |
| `SystemAlarmEvaluator` | `csp_lib/monitor/alarm.py` | 依閾值產生系統告警（複用 equipment.alarm） |
| `ModuleHealthCollector` | `csp_lib/monitor/collector.py` | 模組健康檢查（註冊 `HealthCheckable` 模組） |
| `RedisMonitorPublisher` | `csp_lib/monitor/publisher.py` | 將指標/告警/健康發佈到 Redis |

---

## SystemMetrics

系統指標資料結構：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `cpu_percent` | `float` | CPU 使用率（%） |
| `ram_percent` | `float` | RAM 使用率（%） |
| `ram_used_mb` | `float` | RAM 已使用量（MB） |
| `ram_total_mb` | `float` | RAM 總量（MB） |
| `disk_usage` | `dict[str, float]` | 磁碟使用率 `{路徑: 百分比}` |
| `net_bytes_sent` | `int` | 網路已發送位元組 |
| `net_bytes_recv` | `int` | 網路已接收位元組 |
| `net_send_rate` | `float` | 網路發送速率（bytes/s） |
| `net_recv_rate` | `float` | 網路接收速率（bytes/s） |

---

## SystemAlarmEvaluator

複用 `csp_lib.equipment.alarm` 模組的 `ThresholdAlarmEvaluator` 與 `AlarmStateManager`，對 CPU、RAM、Disk 指標進行閾值告警評估。支援 hysteresis（遲滯）機制防止抖動。

---

## ModuleHealthCollector

| 方法 | 說明 |
|------|------|
| `register_module(name, module)` | 註冊 `HealthCheckable` 模組 |
| `register_check(name, check_fn)` | 註冊自訂健康檢查函式 |
| `collect()` | 收集所有模組健康狀態，回傳 `ModuleHealthSnapshot` |

`ModuleHealthSnapshot` 包含 `modules: list[ModuleStatus]` 與 `overall_status: HealthStatus`。整體狀態由所有模組中最嚴重的狀態決定：

- 任一模組 `UNHEALTHY` -> 整體 `UNHEALTHY`
- 任一模組 `DEGRADED` -> 整體 `DEGRADED`
- 全部 `HEALTHY` -> 整體 `HEALTHY`

---

## RedisMonitorPublisher

Redis Key 結構：

| Key | 型別 | 說明 |
|-----|------|------|
| `{prefix}:metrics` | Hash | 最新系統指標（有 TTL） |
| `{prefix}:modules` | Hash | 最新模組健康（有 TTL） |
| `{prefix}:alarms` | Set | 活躍系統告警代碼 |

Pub/Sub Channel：

| Channel | 說明 |
|---------|------|
| `channel:{prefix}:metrics` | 即時指標串流 |
| `channel:{prefix}:modules` | 即時模組健康串流 |
| `channel:{prefix}:alarm` | 告警觸發/解除事件 |

---

## 相關頁面

- [[MonitorConfig]] -- 監控配置（含 MetricThresholds）
- [[SystemMonitor]] -- 主要監控器
- [[_MOC Monitor]] -- 模組總覽
