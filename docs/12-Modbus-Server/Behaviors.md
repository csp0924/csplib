---
tags:
  - type/class
  - layer/modbus-server
  - status/complete
source: csp_lib/modbus_server/behaviors/
created: 2026-02-17
---

# Behaviors

> 可組合行為模組

行為模組（Behaviors）提供可組合的模擬行為，附加到 `BaseDeviceSimulator` 上為模擬器增添動態特性。位於 `csp_lib/modbus_server/behaviors/`。

---

## 行為一覽

| 行為 | 來源檔案 | 說明 |
|------|----------|------|
| `AlarmBehavior` | `behaviors/alarm.py` | 告警觸發/重置模擬 |
| `NoiseBehavior` | `behaviors/noise.py` | 隨機雜訊 |
| `RampBehavior` | `behaviors/ramp.py` | 線性漸變 |
| `CurveBehavior` | `behaviors/curve.py` | 曲線跟隨 |

---

## AlarmBehavior

管理單個 alarm bit 的觸發與重置邏輯。

| 參數 | 說明 |
|------|------|
| `alarm_code` | 告警代碼 |
| `bit_position` | alarm register 中的 bit 位置 |
| `reset_mode` | 重置模式 |

支援的 `AlarmResetMode`：

| 值 | 說明 |
|----|------|
| `AUTO` | 條件消失自動清除 |
| `MANUAL` | 需要寫入 reset 命令 |
| `LATCHED` | 需要完整 reset（force_reset） |

---

## NoiseBehavior

在 base_value 附近加入隨機波動。

| 參數 | 說明 |
|------|------|
| `base_value` | 基準值 |
| `amplitude` | 擾動幅度 |
| `noise_type` | 擾動類型（`UNIFORM` / `GAUSSIAN`） |

---

## RampBehavior

按指定的 `ramp_rate` 逐步趨近 target，模擬設備功率爬升/下降。

| 參數 | 說明 |
|------|------|
| `ramp_rate` | 每秒最大變化量 |
| `initial_value` | 初始值 |

呼叫 `update(dt)` 時，current_value 以 `ramp_rate * dt` 的速度趨近 target。

---

## CurveBehavior

使用 `CurveProvider` 按時間驅動數值變化。整合 [[_MOC Equipment]] 的 `CurvePoint` 與 `CurveProvider`，每個 `CurvePoint` 指定一個 value 和 duration，在 duration 內持續輸出該 value。

| 參數 | 說明 |
|------|------|
| `curve_provider` | 曲線資料提供者 |
| `default_value` | 預設值（無曲線時使用） |

---

## 相關頁面

- [[Simulators]] -- 使用行為模組的設備模擬器
- [[SimulationServer]] -- 模擬伺服器
- [[_MOC Modbus Server]] -- 模組總覽
