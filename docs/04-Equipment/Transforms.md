---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/core/transform.py
---

# Transforms

> 資料轉換步驟

所有轉換步驟實作 `TransformStep` Protocol，提供 `apply(value)` 方法。可透過 [[ProcessingPipeline]] 串聯多個轉換步驟。

---

## 轉換步驟一覽

| Transform | 參數 | 說明 | 範例 |
|-----------|------|------|------|
| `ScaleTransform` | `magnitude: float = 1.0`, `offset: float = 0.0` | 縮放: `value * magnitude + offset` | 溫度: `ScaleTransform(0.1, -40)` |
| `RoundTransform` | `decimals: int = 2` | 四捨五入 | `RoundTransform(1)` |
| `EnumMapTransform` | `mapping: dict[int, str]`, `default: str = "UNKNOWN"` | 數值到枚舉映射 | `{0: "STOP", 1: "RUN"}` |
| `ClampTransform` | `min_value: float \| None`, `max_value: float \| None` | 值域限制 | `ClampTransform(0, 100)` |
| `BoolTransform` | `true_values: frozenset[int] = {1}` | 布林轉換 | `0 -> False, 非0 -> True` |
| `BitExtractTransform` | `bit_offset: int`, `bit_length: int = 1` | 位元欄位提取 | `BitExtractTransform(8, 4)` |
| `ByteExtractTransform` | `byte_offset: int = 0`, `byte_length: int = 1` | 位元組提取 | 從暫存器列表提取指定位元組 |
| `MultiFieldExtractTransform` | `fields: tuple[tuple[str, int, int], ...]` | 多位元欄位提取 | 從單一整數提取多個命名欄位 |
| `InverseTransform` | `magnitude: float = 1.0`, `offset: float = 0.0` | 反向縮放（寫入用）: `(value - offset) / magnitude` | ScaleTransform 的逆運算 |
| `PowerFactorTransform` | `include_status: bool = False` | 功率因數解碼（Schneider PM5350 專用） | 特殊四象限編碼 |

---

## TransformStep Protocol

```python
class TransformStep(Protocol):
    def apply(self, value: Any) -> Any:
        """套用轉換"""
        ...
```

---

## 詳細說明

### ScaleTransform

計算公式：`result = value * magnitude + offset`

```python
# 溫度轉換: raw_value * 0.1 - 40
temp = ScaleTransform(magnitude=0.1, offset=-40)
temp.apply(250)  # -> -15.0
```

### BitExtractTransform

從整數值中提取指定範圍的位元，不限制位元大小（支援 16/32/64 bit 或更大）。

```python
# 提取 Bit 0 作為布林值
BitExtractTransform(bit_offset=0).apply(0xFF01)  # -> True

# 提取 Bit 8-11 作為 4-bit 數值
BitExtractTransform(bit_offset=8, bit_length=4).apply(0x0F00)  # -> 15
```

### MultiFieldExtractTransform

從單一整數值中提取多個命名位元欄位：

```python
transform = MultiFieldExtractTransform(fields=(
    ("is_running", 0, 1),    # Bit 0, 布林
    ("has_fault", 1, 1),     # Bit 1, 布林
    ("mode", 8, 4),          # Bit 8-11, 4-bit 數值
))
transform.apply(0x0301)
# -> {"is_running": True, "has_fault": False, "mode": 3}
```

### PowerFactorTransform

Schneider PM5350 專用功率因數解碼，支援四象限編碼：

- Q1 (0 ~ 90 度): `0 < x < 1` -> PF = x, lagging
- Q2 (90 ~ 180 度): `-2 < x < -1` -> PF = -2 - x, leading
- Q3 (180 ~ 270 度): `-1 < x < 0` -> PF = x, lagging
- Q4 (270 ~ 360 度): `1 < x < 2` -> PF = 2 - x, leading

---

## 相關頁面

- [[ProcessingPipeline]] -- 串聯多個轉換步驟
- [[_MOC Equipment]] -- 設備模組總覽
