---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/processing/aggregator.py
---

# Aggregators

> 聚合器

聚合器將多個點位的值合併或計算為衍生值。透過 `AggregatorPipeline` 串聯多個聚合器，可在 [[AsyncModbusDevice]] 的 `aggregator_pipeline` 參數中使用。

---

## 聚合器一覽

| 聚合器 | 說明 |
|--------|------|
| `CoilToBitmaskAggregator` | 將多個 Coil 點位合併為單一位元遮罩值 |
| `ComputedValueAggregator` | 根據多個點位計算衍生值 |
| `AggregatorPipeline` | 按順序執行多個聚合器 |

---

## CoilToBitmaskAggregator

將多個 discrete input / coil 點位合併為單一 bitmask 整數值。

| 參數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `output_name` | `str` | (必填) | 輸出值的名稱 |
| `coil_names` | `list[str]` | (必填) | coil 點位名稱列表（按位元順序，bit 0 在前） |
| `remove_source` | `bool` | `True` | 是否移除來源點位 |

```python
from csp_lib.equipment.processing import CoilToBitmaskAggregator

aggregator = CoilToBitmaskAggregator(
    output_name="error1",
    coil_names=[f"error_{i}" for i in range(2501, 2517)],
)
# error_2501 -> bit 0, error_2502 -> bit 1, ...
```

---

## ComputedValueAggregator

根據多個來源點位計算衍生值。

| 參數 | 型別 | 說明 |
|------|------|------|
| `output_name` | `str` | 輸出值的名稱 |
| `source_names` | `list[str]` | 來源點位名稱列表 |
| `compute_fn` | `Callable[..., Any]` | 計算函數，接收來源值作為參數 |

```python
from csp_lib.equipment.processing import ComputedValueAggregator

# 計算功率 = 電壓 x 電流
aggregator = ComputedValueAggregator(
    output_name="power",
    source_names=["voltage", "current"],
    compute_fn=lambda v, i: v * i if v and i else None,
)
```

---

## AggregatorPipeline

按順序執行多個聚合器，前一個聚合器的輸出作為下一個的輸入。

```python
from csp_lib.equipment.processing import AggregatorPipeline

pipeline = AggregatorPipeline(aggregators=[
    coil_aggregator,
    computed_aggregator,
])
result = pipeline.process(values)
```

---

## 相關頁面

- [[_MOC Equipment]] -- 設備模組總覽
