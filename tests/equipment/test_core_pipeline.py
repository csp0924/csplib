# =============== Equipment Core Tests - Pipeline ===============
#
# 資料處理管線單元測試

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.equipment.core.pipeline import ProcessingPipeline, pipeline
from csp_lib.equipment.core.transform import (
    BitExtractTransform,
    BoolTransform,
    ClampTransform,
    EnumMapTransform,
    RoundTransform,
    ScaleTransform,
)


class TestProcessingPipeline:
    """ProcessingPipeline 測試"""

    def test_empty_pipeline(self):
        """空管線應該回傳原值"""
        p = ProcessingPipeline(steps=())
        assert p.process(100) == 100
        assert p.process("hello") == "hello"

    def test_single_step(self):
        """單一步驟管線"""
        p = ProcessingPipeline(steps=(ScaleTransform(magnitude=0.1),))
        assert p.process(1000) == 100.0

    def test_multi_step(self):
        """多步驟管線: 縮放 → 四捨五入"""
        p = ProcessingPipeline(
            steps=(
                ScaleTransform(magnitude=0.1, offset=-40),
                RoundTransform(decimals=1),
            )
        )
        assert p.process(650) == 25.0  # 650 * 0.1 - 40 = 25.0

    def test_temperature_conversion_pipeline(self):
        """實際案例: 溫度轉換管線"""
        p = ProcessingPipeline(
            steps=(
                ScaleTransform(magnitude=0.1, offset=-40),
                RoundTransform(decimals=1),
                ClampTransform(min_value=-40, max_value=80),
            )
        )
        # 正常值
        assert p.process(650) == 25.0
        # 超出上限
        assert p.process(2000) == 80.0  # 2000 * 0.1 - 40 = 160 → clamp to 80
        # 超出下限
        assert p.process(0) == -40.0  # 0 * 0.1 - 40 = -40

    def test_bit_to_enum_pipeline(self):
        """狀態轉換管線: 位元提取 → 枚舉映射"""
        p = ProcessingPipeline(
            steps=(
                BitExtractTransform(bit_offset=0, bit_length=4),
                EnumMapTransform(mapping={0: "STOP", 1: "RUN", 2: "FAULT"}),
            )
        )
        assert p.process(0b11110000) == "STOP"  # 低 4 位 = 0
        assert p.process(0b11110001) == "RUN"  # 低 4 位 = 1
        assert p.process(0b11110010) == "FAULT"  # 低 4 位 = 2
        assert p.process(0b11111111) == "UNKNOWN"  # 低 4 位 = 15

    def test_len(self):
        """__len__ 測試"""
        p0 = ProcessingPipeline(steps=())
        p1 = ProcessingPipeline(steps=(ScaleTransform(),))
        p3 = ProcessingPipeline(steps=(ScaleTransform(), RoundTransform(), ClampTransform()))
        assert len(p0) == 0
        assert len(p1) == 1
        assert len(p3) == 3

    def test_bool(self):
        """__bool__ 測試"""
        p_empty = ProcessingPipeline(steps=())
        p_filled = ProcessingPipeline(steps=(ScaleTransform(),))
        assert bool(p_empty) is False
        assert bool(p_filled) is True

    def test_immutable(self):
        """管線應該是不可變的"""
        p = ProcessingPipeline(steps=(ScaleTransform(),))
        with pytest.raises(FrozenInstanceError):
            p.steps = ()

    def test_error_propagation(self):
        """錯誤應該傳播出來"""
        p = ProcessingPipeline(steps=(ScaleTransform(magnitude=0.1),))
        with pytest.raises(TypeError):
            p.process("invalid")


class TestPipelineFactory:
    """pipeline() 便捷函數測試"""

    def test_empty_pipeline(self):
        p = pipeline()
        assert len(p) == 0
        assert isinstance(p, ProcessingPipeline)

    def test_single_step(self):
        p = pipeline(ScaleTransform(magnitude=0.1))
        assert len(p) == 1
        assert p.process(100) == 10.0

    def test_multi_step(self):
        p = pipeline(
            ScaleTransform(magnitude=0.1),
            RoundTransform(decimals=0),
        )
        assert len(p) == 2
        assert p.process(123) == 12.0

    def test_typical_usage(self):
        """模擬典型使用方式"""
        temp_pipeline = pipeline(
            ScaleTransform(0.1, -40),
            RoundTransform(1),
        )
        assert temp_pipeline.process(650) == 25.0


class TestPipelineIntegration:
    """整合測試: 驗證管線與 ReadPoint 的整合"""

    def test_pipeline_with_complex_transforms(self):
        """複雜轉換組合"""
        # 模擬電池 SOC 轉換: raw 0-10000 → 0-100%
        soc_pipeline = pipeline(
            ScaleTransform(magnitude=0.01),  # /100
            RoundTransform(decimals=1),
            ClampTransform(min_value=0, max_value=100),
        )
        assert soc_pipeline.process(5500) == 55.0
        assert soc_pipeline.process(10000) == 100.0
        assert soc_pipeline.process(-100) == 0.0

    def test_pipeline_bool_output(self):
        """布林輸出管線"""
        running_pipeline = pipeline(
            BitExtractTransform(bit_offset=0, bit_length=1),
        )
        assert running_pipeline.process(0b0001) is True
        assert running_pipeline.process(0b0000) is False

    def test_pipeline_with_bool_transform(self):
        """使用 BoolTransform 的管線"""
        # 提取 mode 欄位 (bit 4-7)，判斷是否為特定模式
        mode_active_pipeline = pipeline(
            BitExtractTransform(bit_offset=4, bit_length=4),
            BoolTransform(true_values=frozenset({1, 2, 3})),  # 模式 1,2,3 視為 active
        )
        assert mode_active_pipeline.process(0b0001_0000) is True  # mode = 1
        assert mode_active_pipeline.process(0b0010_0000) is True  # mode = 2
        assert mode_active_pipeline.process(0b0000_0000) is False  # mode = 0
        assert mode_active_pipeline.process(0b1111_0000) is False  # mode = 15

    def test_pipeline_string_output(self):
        """字串輸出管線"""
        status_pipeline = pipeline(
            EnumMapTransform(
                mapping={0: "OFF", 1: "STANDBY", 2: "RUNNING", 3: "FAULT"},
                default="UNKNOWN",
            ),
        )
        assert status_pipeline.process(0) == "OFF"
        assert status_pipeline.process(2) == "RUNNING"
        assert status_pipeline.process(99) == "UNKNOWN"
