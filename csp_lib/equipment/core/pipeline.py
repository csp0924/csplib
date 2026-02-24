# =============== Equipment Core - Pipeline ===============
#
# 資料處理管線
#
# 將多個轉換步驟串聯執行

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .transform import TransformStep


@dataclass(frozen=True)
class ProcessingPipeline:
    """
    資料處理管線

    將多個 TransformStep 串聯執行，依序處理資料。

    Attributes:
        steps: 轉換步驟元組

    使用範例：
        pipeline = ProcessingPipeline(steps=(
            ScaleTransform(magnitude=0.1, offset=-40),
            RoundTransform(decimals=1),
        ))
        result = pipeline.process(250)  # (250 * 0.1 - 40) = -15.0
    """

    steps: tuple[TransformStep, ...]

    def process(self, raw_value: Any) -> Any:
        """
        執行管線處理

        Args:
            raw_value: 原始值

        Returns:
            處理後的值
        """
        value = raw_value
        for step in self.steps:
            value = step.apply(value)
        return value

    def __len__(self) -> int:
        return len(self.steps)

    def __bool__(self) -> bool:
        return len(self.steps) > 0


def pipeline(*steps: TransformStep) -> ProcessingPipeline:
    """
    便捷建構函數

    使用範例：
        from csp_lib.equipment import pipeline, ScaleTransform, RoundTransform

        temp_pipeline = pipeline(
            ScaleTransform(0.1, -40),
            RoundTransform(1),
        )
    """
    return ProcessingPipeline(steps=steps)


__all__ = [
    "ProcessingPipeline",
    "pipeline",
]
