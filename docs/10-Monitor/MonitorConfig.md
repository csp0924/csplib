---
tags:
  - type/config
  - layer/monitor
  - status/complete
source: csp_lib/monitor/config.py
created: 2026-02-17
updated: 2026-04-04
version: 0.6.1
---

# MonitorConfig

> 監控器配置

`MonitorConfig` 與 `MetricThresholds` 定義系統監控的閾值與行為設定。兩者皆為 frozen dataclass，建構時自動進行參數驗證。

---

## MetricThresholds

系統指標閾值，用於 `SystemAlarmEvaluator` 判定告警觸發。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `cpu_percent` | `float` | `90.0` | CPU 使用率閾值（%） |
| `ram_percent` | `float` | `85.0` | RAM 使用率閾值（%） |
| `disk_percent` | `float` | `95.0` | 磁碟使用率閾值（%） |

> 所有值必須在 `(0, 100]` 範圍內。

---

## MonitorConfig

監控器完整配置。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `interval_seconds` | `float` | `5.0` | 監控間隔（秒），必須 > 0 |
| `thresholds` | `MetricThresholds` | `MetricThresholds()` | 系統指標閾值 |
| `enable_cpu` | `bool` | `True` | 啟用 CPU 監控 |
| `enable_ram` | `bool` | `True` | 啟用 RAM 監控 |
| `enable_disk` | `bool` | `True` | 啟用磁碟監控 |
| `enable_network` | `bool` | `True` | 啟用網路監控 |
| `enable_module_health` | `bool` | `True` | 啟用模組健康檢查 |
| `redis_key_prefix` | `str` | `"system"` | Redis key 前綴 |
| `metrics_ttl` | `int` | `30` | 指標 TTL（秒），必須 > 0 |
| `hysteresis_activate` | `int` | `3` | 告警觸發遲滯次數，必須 >= 1 |
| `hysteresis_clear` | `int` | `3` | 告警解除遲滯次數，必須 >= 1 |
| `disk_paths` | `tuple[str, ...]` | `("/",)` | 監控的磁碟路徑，不可為空 |
| `network_interfaces` | `tuple[str, ...] \| None` | `None` | 監控的網路介面名稱（`None` = 全部） |
| `network_thresholds` | `NetworkThresholds` | `NetworkThresholds()` | 網路介面閾值 |

---

## NetworkThresholds

網路介面閾值（frozen dataclass），用於 per-interface 流量告警。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `send_rate_bytes` | `float` | `0.0` | 發送速率閾值（bytes/s），`0` = 停用 |
| `recv_rate_bytes` | `float` | `0.0` | 接收速率閾值（bytes/s），`0` = 停用 |

`is_enabled` 屬性：當 `send_rate_bytes` 或 `recv_rate_bytes` > 0 時為 `True`。

---

## DistributedMonitorConfig

分散式監控配置（frozen dataclass），啟用多節點監控聚合。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `instance_id` | `str` | (必填) | 唯一節點 ID |
| `namespace` | `str` | `"default"` | 命名空間 |
| `node_ttl` | `int` | `30` | 節點註冊 TTL（秒），必須 > 0 |
| `aggregation_interval` | `float` | `10.0` | 聚合間隔（秒），必須 > 0 |
| `publish_cluster_health` | `bool` | `True` | 是否發布叢集健康狀態 |

### 方法

| 方法 | 說明 |
|------|------|
| `node_key(instance_id)` | 取得節點註冊 Key：`monitor:{namespace}:nodes:{instance_id}` |
| `node_pattern()` | 取得節點探索 Pattern：`monitor:{namespace}:nodes:*` |
| `metrics_prefix(instance_id)` | 取得節點指標 Key 前綴：`monitor:{namespace}:{instance_id}` |
| `cluster_health_key()` | 取得叢集健康 Key：`monitor:{namespace}:cluster:health` |

---

## 程式碼範例

```python
from csp_lib.monitor import MonitorConfig, MetricThresholds, NetworkThresholds

config = MonitorConfig(
    interval_seconds=5.0,
    thresholds=MetricThresholds(
        cpu_percent=90.0,
        ram_percent=85.0,
        disk_percent=95.0,
    ),
    enable_cpu=True,
    enable_ram=True,
    enable_disk=True,
    enable_network=True,
    enable_module_health=True,
    redis_key_prefix="system",
    metrics_ttl=30,
    hysteresis_activate=3,
    hysteresis_clear=3,
    disk_paths=("/",),
    network_interfaces=("eth0", "eth1"),  # None = 全部
    network_thresholds=NetworkThresholds(
        send_rate_bytes=100_000_000,  # 100 MB/s
        recv_rate_bytes=100_000_000,
    ),
)
```

---

## 相關頁面

- [[SystemMonitor]] -- 主要監控器
- [[SystemMetricsCollector]] -- 指標收集器
- [[_MOC Monitor]] -- 模組總覽
