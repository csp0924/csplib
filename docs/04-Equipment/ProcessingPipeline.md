---
tags:
  - type/class
  - layer/equipment
  - status/complete
source: csp_lib/equipment/core/pipeline.py
---

# ProcessingPipeline

> 資料處理管線

`ProcessingPipeline` 將多個 [[Transforms|TransformStep]] 串聯執行，依序處理資料。讀取點位可透過 `pipeline` 參數綁定管線，在讀取後自動進行轉換。

---

## 類別定義

```python
@dataclass(frozen=True)
class ProcessingPipeline:
    steps: tuple[TransformStep, ...]

    def process(self, raw_value: Any) -> Any:
        """依序執行所有轉換步驟"""
```

---

## 便捷建構函數

```python
from csp_lib.equipment.core import pipeline, ScaleTransform, RoundTransform

temp_pipeline = pipeline(
    ScaleTransform(0.1, -40),
    RoundTransform(1),
)
# 250 -> (250 * 0.1 - 40) = -15.0 -> -15.0
```

`pipeline()` 函數接受可變參數的 `TransformStep`，回傳 `ProcessingPipeline` 實例。

---

## 搭配 ReadPoint 使用

```python
from csp_lib.equipment.core import ReadPoint, pipeline, ScaleTransform, RoundTransform
from csp_lib.modbus import UInt16

temp_point = ReadPoint(
    name="temperature",
    address=10,
    data_type=UInt16(),
    pipeline=pipeline(
        ScaleTransform(0.1, -40),
        RoundTransform(1),
    ),
)
```

當 `GroupReader` 讀取此點位後，會自動呼叫 `pipeline.process()` 對原始值進行轉換。

---

## 相關頁面

- [[Transforms]] -- 可用的轉換步驟
- [[ReadPoint]] -- 讀取點位定義
- [[_MOC Equipment]] -- 設備模組總覽
