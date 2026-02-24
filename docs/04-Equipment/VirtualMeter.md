---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/simulation/virtual_meter.py
---

# VirtualMeter

> 虛擬電表模擬器

`VirtualMeter` 用於測試控制策略（如 FP、QV），支援兩種運行模式：隨機波動與測試曲線。

---

## 運行模式

| 模式 | 列舉值 | 說明 |
|------|--------|------|
| `RANDOM` | `MeterMode.RANDOM` | 在基準值附近隨機波動（預設模式） |
| `TEST_CURVE` | `MeterMode.TEST_CURVE` | 執行預定義的測試曲線 |

---

## 建構參數

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `base_voltage` | `float` | `380.0` | 基準電壓 (V) |
| `base_frequency` | `float` | `60.0` | 基準頻率 (Hz) |
| `voltage_noise` | `float` | `5.0` | 電壓隨機波動範圍 (+/- V) |
| `frequency_noise` | `float` | `0.05` | 頻率隨機波動範圍 (+/- Hz) |
| `curve_provider` | `CurveProvider \| None` | `None` | 測試曲線提供者（預設使用 `DEFAULT_REGISTRY`） |

---

## MeterReading

不可變的電表讀值資料：

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `v` | `float` | `380.0` | 電壓 (V) |
| `f` | `float` | `60.0` | 頻率 (Hz) |
| `p` | `float` | `0.0` | 有功功率 (kW) |
| `q` | `float` | `0.0` | 無功功率 (kVar) |
| `s` | `float` | `0.0` | 視在功率 (kVA) |
| `pf` | `float` | `1.0` | 功率因數 |

可使用 `MeterReading.with_power(v, f, p, q)` 工廠方法自動計算 `s` 和 `pf`。

---

## 主要方法

| 方法 | 說明 |
|------|------|
| `update()` | 非同步更新電表讀值 |
| `get_frequency()` | 取得當前頻率 |
| `get_voltage()` | 取得當前電壓 |
| `start_test_curve(name)` | 啟動測試曲線，回傳是否成功 |
| `stop_test_curve()` | 停止測試曲線，切回 RANDOM 模式 |
| `list_available_curves()` | 列出可用的測試曲線名稱 |

---

## 程式碼範例

```python
from csp_lib.equipment.simulation import VirtualMeter, MeterReading

meter = VirtualMeter(base_frequency=60.0)

# 隨機模式
await meter.update()
print(meter.get_frequency())

# 測試曲線模式
meter.start_test_curve("fp_step")
while meter.mode == MeterMode.TEST_CURVE:
    await meter.update()
    print(f"f={meter.get_frequency():.3f}Hz")
    await asyncio.sleep(1)
```

---

## 相關頁面

- [[CurveRegistry]] -- 測試曲線註冊表
- [[_MOC Equipment]] -- 設備模組總覽
