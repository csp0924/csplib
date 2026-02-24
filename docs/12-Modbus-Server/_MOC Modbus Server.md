---
tags:
  - type/moc
  - layer/modbus-server
  - status/complete
created: 2026-02-17
---

# Modbus Server 模組總覽

> **模擬測試用 Modbus TCP 伺服器 (`csp_lib.modbus_server`)**

Modbus Server 模組提供完整的 Modbus TCP 設備模擬環境，用於整合測試與控制機制驗證。內建多種設備模擬器（太陽能、PCS、發電機、負載、電表）與可組合行為模組（告警、雜訊、漸變、曲線），並支援微電網功率平衡聯動。

---

## 架構概覽

```
SimulationServer (AsyncLifecycleMixin, pymodbus TCP)
  ├── SimulatorDataBlock ─── 橋接 pymodbus ↔ RegisterBlock
  ├── BaseDeviceSimulator ─── 設備模擬器基類
  │     ├── SolarSimulator
  │     ├── PCSSimulator
  │     ├── GeneratorSimulator
  │     ├── LoadSimulator
  │     └── PowerMeterSimulator
  ├── MicrogridSimulator ─── 功率平衡協調器
  └── Behaviors
        ├── AlarmBehavior
        ├── NoiseBehavior
        ├── RampBehavior
        └── CurveBehavior
```

---

## 索引

### 伺服器

| 頁面 | 說明 |
|------|------|
| [[SimulationServer]] | Modbus TCP 模擬伺服器（含 ServerConfig） |
| [[MicrogridSimulator]] | 微電網功率平衡協調器 |

### 模擬器

| 頁面 | 說明 |
|------|------|
| [[Simulators]] | 5 種內建設備模擬器一覽 |

### 行為模組

| 頁面 | 說明 |
|------|------|
| [[Behaviors]] | 4 種可組合行為模組一覽 |

---

## Dataview 查詢

```dataview
TABLE source AS "原始碼", tags AS "標籤"
FROM "12-Modbus-Server"
WHERE file.name != "_MOC Modbus Server"
SORT file.name ASC
```

---

## 相關 MOC

- 使用：[[_MOC Modbus]] -- 底層 Modbus 資料型別（Float32, UInt16 等）
- 使用：[[_MOC Equipment]] -- 複用 CurveProvider（CurveBehavior）
