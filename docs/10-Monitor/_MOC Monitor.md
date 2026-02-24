---
tags:
  - type/moc
  - layer/monitor
  - status/complete
created: 2026-02-17
---

# Monitor 模組總覽

> **系統監控模組 (`csp_lib.monitor`)**

Monitor 模組提供即時系統資源監控與模組健康檢查，整合告警評估、Redis 發布與通知分發。定期收集 CPU、RAM、磁碟、網路指標，依閾值產生系統告警，並透過 [[NotificationDispatcher]] 發送通知。

需安裝：`pip install csp0924_lib[monitor]`

---

## 架構概覽

```
SystemMonitor (主入口，AsyncLifecycleMixin)
  ├── SystemMetricsCollector ─── psutil 收集 CPU/RAM/Disk/Network
  ├── SystemAlarmEvaluator ──── 依閾值產生系統告警
  ├── ModuleHealthCollector ─── 模組健康檢查
  └── RedisMonitorPublisher ─── 指標/告警/健康發布至 Redis
```

---

## 索引

### 配置

| 頁面 | 說明 |
|------|------|
| [[MonitorConfig]] | 監控器配置與 MetricThresholds |

### 核心元件

| 頁面 | 說明 |
|------|------|
| [[SystemMonitor]] | 主要監控器（整合所有元件） |
| [[SystemMetricsCollector]] | 指標收集與元件一覽 |

---

## Dataview 查詢

```dataview
TABLE source AS "原始碼", tags AS "標籤"
FROM "10-Monitor"
WHERE file.name != "_MOC Monitor"
SORT file.name ASC
```

---

## 相關 MOC

- 使用：[[_MOC Storage]] -- Redis 發布系統指標
- 使用：[[_MOC Notification]] -- 透過 NotificationDispatcher 發送告警通知
- 使用：[[_MOC Equipment]] -- 複用 AlarmStateManager 與 ThresholdAlarmEvaluator
