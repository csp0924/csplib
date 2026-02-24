# =============== Equipment Processing - Aggregator ===============
#
# 聚合器
#
# 將多個點位的值聚合為單一值，

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass
class Processor(Protocol):
    def process(self, values: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class CoilToBitmaskAggregator:
    """
    Coil 轉位元遮罩聚合器

    將多個 coil 點位合併為單一位元遮罩值。
    解決設備：多個 discrete input 需要合併為 error register。

    Attributes:
        output_name: 輸出值的名稱
        coil_names: coil 點位名稱列表（按位元順序，bit 0 在前）
        remove_source: 是否移除來源點位

    使用範例：
        aggregator = CoilToBitmaskAggregator(
            output_name="error1",
            coil_names=[f"error_{i}" for i in range(2501, 2517)],
        )
        # error_2501 -> bit 0, error_2502 -> bit 1, ...
    """

    output_name: str
    coil_names: list[str]
    remove_source: bool = True

    def process(self, values: dict[str, Any]) -> dict[str, Any]:
        """
        聚合 coil 值為位元遮罩

        Args:
            values: {點位名稱: 值} 字典

        Returns:
            更新後的字典
        """
        result = values.copy()
        bitmask: int | None = 0

        for i, name in enumerate(self.coil_names):
            coil_value = values.get(name)
            if coil_value is None:
                bitmask = None
                break
            if coil_value:
                bitmask |= 1 << i  # type: ignore[operator]

        result[self.output_name] = bitmask

        if self.remove_source:
            for name in self.coil_names:
                result.pop(name, None)

        return result


@dataclass
class ComputedValueAggregator:
    """
    計算值聚合器

    根據多個點位計算衍生值。

    Attributes:
        output_name: 輸出值的名稱
        source_names: 來源點位名稱列表
        compute_fn: 計算函數，接收來源值列表，返回計算結果

    使用範例：
        # 計算功率 = 電壓 × 電流
        aggregator = ComputedValueAggregator(
            output_name="power",
            source_names=["voltage", "current"],
            compute_fn=lambda v, i: v * i if v and i else None,
        )
    """

    output_name: str
    source_names: list[str]
    compute_fn: Callable[..., Any]

    def process(self, values: dict[str, Any]) -> dict[str, Any]:
        """聚合計算"""
        result = values.copy()

        source_values = [values.get(name) for name in self.source_names]

        try:
            computed = self.compute_fn(*source_values)
            result[self.output_name] = computed
        except Exception:
            result[self.output_name] = None

        return result


class AggregatorPipeline:
    """
    聚合管線

    按順序執行多個聚合器。
    """

    def __init__(
        self,
        aggregators: list[Processor],
    ) -> None:
        self._aggregators = aggregators

    def process(self, values: dict[str, Any]) -> dict[str, Any]:
        """執行所有聚合器"""
        result = values
        for processor in self._aggregators:
            result = processor.process(result)
        return result


__all__ = [
    "AggregatorPipeline",
    "CoilToBitmaskAggregator",
    "ComputedValueAggregator",
]
