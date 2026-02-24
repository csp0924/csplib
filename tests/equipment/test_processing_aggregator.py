# =============== Equipment Processing Tests - Aggregator ===============
#
# 聚合器單元測試


from csp_lib.equipment.processing.aggregator import (
    AggregatorPipeline,
    CoilToBitmaskAggregator,
    ComputedValueAggregator,
)

# ======================== CoilToBitmaskAggregator Tests ========================


class TestCoilToBitmaskAggregator:
    """CoilToBitmaskAggregator 測試"""

    def test_all_false(self):
        """所有 coil 為 False"""
        aggregator = CoilToBitmaskAggregator(
            output_name="error_mask",
            coil_names=["e1", "e2", "e3"],
        )
        result = aggregator.process({"e1": False, "e2": False, "e3": False})
        assert result["error_mask"] == 0b000

    def test_all_true(self):
        """所有 coil 為 True"""
        aggregator = CoilToBitmaskAggregator(
            output_name="error_mask",
            coil_names=["e1", "e2", "e3"],
        )
        result = aggregator.process({"e1": True, "e2": True, "e3": True})
        assert result["error_mask"] == 0b111

    def test_partial_true(self):
        """部分 coil 為 True"""
        aggregator = CoilToBitmaskAggregator(
            output_name="error_mask",
            coil_names=["e1", "e2", "e3", "e4"],
        )
        result = aggregator.process(
            {
                "e1": True,  # bit 0
                "e2": False,  # bit 1
                "e3": True,  # bit 2
                "e4": False,  # bit 3
            }
        )
        assert result["error_mask"] == 0b0101

    def test_bit_order(self):
        """位元順序：第一個 coil 對應 bit 0"""
        aggregator = CoilToBitmaskAggregator(
            output_name="mask",
            coil_names=["bit0", "bit1", "bit7"],
        )
        result = aggregator.process(
            {
                "bit0": False,
                "bit1": True,
                "bit7": True,
            }
        )
        # bit1 = 0b010, bit7 = 0b100 => 0b110
        assert result["mask"] == 0b110

    def test_remove_source_true(self):
        """remove_source=True 移除來源點位"""
        aggregator = CoilToBitmaskAggregator(
            output_name="mask",
            coil_names=["e1", "e2"],
            remove_source=True,
        )
        result = aggregator.process({"e1": True, "e2": False, "other": 123})
        assert "e1" not in result
        assert "e2" not in result
        assert result["other"] == 123
        assert result["mask"] == 0b01

    def test_remove_source_false(self):
        """remove_source=False 保留來源點位"""
        aggregator = CoilToBitmaskAggregator(
            output_name="mask",
            coil_names=["e1", "e2"],
            remove_source=False,
        )
        result = aggregator.process({"e1": True, "e2": False})
        assert "e1" in result
        assert "e2" in result
        assert result["mask"] == 0b01

    def test_missing_coil_returns_none(self):
        """缺少 coil 時返回 None"""
        aggregator = CoilToBitmaskAggregator(
            output_name="mask",
            coil_names=["e1", "e2", "e3"],
        )
        result = aggregator.process({"e1": True, "e2": False})  # 缺少 e3
        assert result["mask"] is None

    def test_large_bitmask(self):
        """大量 coil（16 個）"""
        coil_names = [f"error_{i}" for i in range(16)]
        aggregator = CoilToBitmaskAggregator(
            output_name="error_register",
            coil_names=coil_names,
        )
        values = {name: (i % 2 == 0) for i, name in enumerate(coil_names)}
        result = aggregator.process(values)
        # 偶數位 = True: 0b0101010101010101 = 0x5555
        assert result["error_register"] == 0x5555


# ======================== ComputedValueAggregator Tests ========================


class TestComputedValueAggregator:
    """ComputedValueAggregator 測試"""

    def test_power_calculation(self):
        """計算功率 = 電壓 × 電流"""
        aggregator = ComputedValueAggregator(
            output_name="power",
            source_names=["voltage", "current"],
            compute_fn=lambda v, i: v * i,
        )
        result = aggregator.process({"voltage": 220.0, "current": 10.0})
        assert result["power"] == 2200.0
        # 來源值保留
        assert result["voltage"] == 220.0
        assert result["current"] == 10.0

    def test_sum_calculation(self):
        """計算多個值的總和"""
        aggregator = ComputedValueAggregator(
            output_name="total_power",
            source_names=["p1", "p2", "p3"],
            compute_fn=lambda a, b, c: a + b + c,
        )
        result = aggregator.process({"p1": 100, "p2": 200, "p3": 300})
        assert result["total_power"] == 600

    def test_conditional_calculation(self):
        """條件計算"""
        aggregator = ComputedValueAggregator(
            output_name="efficiency",
            source_names=["output", "input"],
            compute_fn=lambda out, inp: (out / inp * 100) if inp else None,
        )
        result = aggregator.process({"output": 90, "input": 100})
        assert result["efficiency"] == 90.0

    def test_missing_source_returns_none(self):
        """缺少來源值時使用 None 參與計算"""
        aggregator = ComputedValueAggregator(
            output_name="power",
            source_names=["voltage", "current"],
            compute_fn=lambda v, i: v * i if v and i else None,
        )
        result = aggregator.process({"voltage": 220.0})  # 缺少 current
        assert result["power"] is None

    def test_exception_returns_none(self):
        """計算異常時返回 None"""
        aggregator = ComputedValueAggregator(
            output_name="result",
            source_names=["a", "b"],
            compute_fn=lambda a, b: a / b,  # b=0 會拋錯
        )
        result = aggregator.process({"a": 10, "b": 0})
        assert result["result"] is None

    def test_preserves_other_values(self):
        """保留其他點位值"""
        aggregator = ComputedValueAggregator(
            output_name="sum",
            source_names=["a", "b"],
            compute_fn=lambda a, b: a + b,
        )
        result = aggregator.process({"a": 1, "b": 2, "unrelated": "value"})
        assert result["sum"] == 3
        assert result["unrelated"] == "value"


# ======================== AggregatorPipeline Tests ========================


class TestAggregatorPipeline:
    """AggregatorPipeline 測試"""

    def test_empty_pipeline(self):
        """空管線返回原值"""
        pipeline = AggregatorPipeline(aggregators=[])
        result = pipeline.process({"a": 1, "b": 2})
        assert result == {"a": 1, "b": 2}

    def test_single_aggregator(self):
        """單一聚合器"""
        pipeline = AggregatorPipeline(
            aggregators=[
                ComputedValueAggregator(
                    output_name="sum",
                    source_names=["a", "b"],
                    compute_fn=lambda a, b: a + b,
                ),
            ]
        )
        result = pipeline.process({"a": 1, "b": 2})
        assert result["sum"] == 3

    def test_multiple_aggregators(self):
        """多個聚合器串聯"""
        pipeline = AggregatorPipeline(
            aggregators=[
                # 第一步：計算總和
                ComputedValueAggregator(
                    output_name="sum",
                    source_names=["a", "b"],
                    compute_fn=lambda a, b: a + b,
                ),
                # 第二步：用總和計算平均
                ComputedValueAggregator(
                    output_name="avg",
                    source_names=["sum"],
                    compute_fn=lambda s: s / 2,
                ),
            ]
        )
        result = pipeline.process({"a": 10, "b": 20})
        assert result["sum"] == 30
        assert result["avg"] == 15.0

    def test_aggregator_chain_order(self):
        """聚合器執行順序"""
        pipeline = AggregatorPipeline(
            aggregators=[
                CoilToBitmaskAggregator(
                    output_name="mask",
                    coil_names=["c1", "c2"],
                    remove_source=True,
                ),
                ComputedValueAggregator(
                    output_name="has_error",
                    source_names=["mask"],
                    compute_fn=lambda m: m > 0 if m is not None else None,
                ),
            ]
        )
        result = pipeline.process({"c1": True, "c2": False})
        assert result["mask"] == 0b01
        assert result["has_error"] is True
        assert "c1" not in result
        assert "c2" not in result

    def test_mixed_aggregators(self):
        """混合使用不同類型聚合器"""
        pipeline = AggregatorPipeline(
            aggregators=[
                CoilToBitmaskAggregator(
                    output_name="error1",
                    coil_names=["e1", "e2"],
                ),
                CoilToBitmaskAggregator(
                    output_name="error2",
                    coil_names=["e3", "e4"],
                ),
                ComputedValueAggregator(
                    output_name="total_errors",
                    source_names=["error1", "error2"],
                    compute_fn=lambda a, b: bin(a).count("1") + bin(b).count("1") if a and b else 0,
                ),
            ]
        )
        result = pipeline.process(
            {
                "e1": True,
                "e2": True,  # error1 = 0b11 (2 errors)
                "e3": True,
                "e4": False,  # error2 = 0b01 (1 error)
            }
        )
        assert result["error1"] == 0b11
        assert result["error2"] == 0b01
        assert result["total_errors"] == 3
