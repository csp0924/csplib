# =============== Equipment Transport Tests - Base ===============
#
# PointGrouper 分組器單元測試
#
# 測試基於理論行為設計，驗證分組邏輯正確性

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.equipment.core.point import ReadPoint
from csp_lib.equipment.transport.base import PointGrouper, ReadGroup
from csp_lib.modbus import Float32, FunctionCode, Int32, UInt16


class TestReadGroup:
    """ReadGroup dataclass 測試"""

    def test_immutable(self):
        """ReadGroup 為 frozen dataclass，不可修改"""
        group = ReadGroup(function_code=3, start_address=0, count=10)
        with pytest.raises(FrozenInstanceError):
            group.count = 20

    def test_basic_creation(self):
        """正確建立並存取所有欄位"""
        point = ReadPoint(name="test", address=100, data_type=UInt16())
        group = ReadGroup(function_code=3, start_address=100, count=5, points=(point,))
        assert group.function_code == 3
        assert group.start_address == 100
        assert group.count == 5
        assert len(group.points) == 1


class TestPointGrouperBasicBehavior:
    """PointGrouper 基本行為測試"""

    @pytest.fixture
    def grouper(self) -> PointGrouper:
        return PointGrouper()

    def test_empty_points(self, grouper: PointGrouper):
        """空列表應回傳空列表"""
        result = grouper.group([])
        assert result == []

    def test_single_point(self, grouper: PointGrouper):
        """單一點位應產生單一群組"""
        point = ReadPoint(name="p1", address=100, data_type=UInt16())
        result = grouper.group([point])

        assert len(result) == 1
        assert result[0].start_address == 100
        assert result[0].count == 1
        assert result[0].points == (point,)

    def test_two_consecutive_points(self, grouper: PointGrouper):
        """連續的兩個點位應合併成一個群組"""
        p1 = ReadPoint(name="p1", address=100, data_type=UInt16())
        p2 = ReadPoint(name="p2", address=101, data_type=UInt16())
        result = grouper.group([p1, p2])

        assert len(result) == 1
        assert result[0].start_address == 100
        assert result[0].count == 2
        assert result[0].points == (p1, p2)

    def test_two_non_consecutive_points_still_merge_within_max_length(self, grouper: PointGrouper):
        """
        不連續但在 max_length 內的兩個點位仍會合併到一個群組
        （這是 Modbus 最佳化的正常行為，減少請求次數）
        """
        p1 = ReadPoint(name="p1", address=100, data_type=UInt16())
        p2 = ReadPoint(name="p2", address=200, data_type=UInt16())
        result = grouper.group([p1, p2])

        # 200 + 1 - 100 = 101，在 125 限制內，會合併
        assert len(result) == 1
        assert result[0].start_address == 100
        assert result[0].count == 101  # 涵蓋 100-200 的範圍


class TestPointGrouperReadGroupSeparation:
    """read_group 分離測試 - 不同 read_group 必須分開"""

    @pytest.fixture
    def grouper(self) -> PointGrouper:
        return PointGrouper()

    def test_different_read_groups_separate(self, grouper: PointGrouper):
        """不同 read_group 的點位必須分成不同群組"""
        p1 = ReadPoint(name="p1", address=100, data_type=UInt16(), read_group="group_a")
        p2 = ReadPoint(name="p2", address=101, data_type=UInt16(), read_group="group_b")
        result = grouper.group([p1, p2])

        assert len(result) == 2
        # 驗證各群組只包含對應的點位
        group_a = [g for g in result if p1 in g.points][0]
        group_b = [g for g in result if p2 in g.points][0]
        assert group_a.points == (p1,)
        assert group_b.points == (p2,)

    def test_same_read_group_merge(self, grouper: PointGrouper):
        """相同 read_group 的連續點位應合併"""
        p1 = ReadPoint(name="p1", address=100, data_type=UInt16(), read_group="status")
        p2 = ReadPoint(name="p2", address=101, data_type=UInt16(), read_group="status")
        result = grouper.group([p1, p2])

        assert len(result) == 1
        assert result[0].points == (p1, p2)

    def test_empty_and_named_read_group_separate(self, grouper: PointGrouper):
        """空字串和命名 read_group 必須分開處理"""
        p1 = ReadPoint(name="p1", address=100, data_type=UInt16(), read_group="")
        p2 = ReadPoint(name="p2", address=101, data_type=UInt16(), read_group="named")
        result = grouper.group([p1, p2])

        assert len(result) == 2


class TestPointGrouperFunctionCodeSeparation:
    """function_code 分離測試 - 不同功能碼必須分開"""

    @pytest.fixture
    def grouper(self) -> PointGrouper:
        return PointGrouper()

    def test_different_function_codes_separate(self, grouper: PointGrouper):
        """不同 function_code 的點位必須分成不同群組"""
        p1 = ReadPoint(name="p1", address=100, data_type=UInt16(), function_code=FunctionCode.READ_HOLDING_REGISTERS)
        p2 = ReadPoint(name="p2", address=101, data_type=UInt16(), function_code=FunctionCode.READ_INPUT_REGISTERS)
        result = grouper.group([p1, p2])

        assert len(result) == 2
        fc_codes = {g.function_code for g in result}
        assert fc_codes == {3, 4}

    def test_holding_and_input_registers(self, grouper: PointGrouper):
        """FC=3 和 FC=4 的點位必須分開，即使位址連續"""
        p_holding = ReadPoint(
            name="holding", address=100, data_type=UInt16(), function_code=FunctionCode.READ_HOLDING_REGISTERS
        )
        p_input = ReadPoint(
            name="input", address=101, data_type=UInt16(), function_code=FunctionCode.READ_INPUT_REGISTERS
        )
        result = grouper.group([p_holding, p_input])

        assert len(result) == 2
        holding_group = [g for g in result if g.function_code == 3][0]
        input_group = [g for g in result if g.function_code == 4][0]
        assert holding_group.points == (p_holding,)
        assert input_group.points == (p_input,)


class TestPointGrouperMaxLengthLimit:
    """最大長度限制測試"""

    @pytest.fixture
    def grouper(self) -> PointGrouper:
        return PointGrouper()

    def test_exceeds_max_length_splits(self, grouper: PointGrouper):
        """超過最大長度時必須拆分成多個群組，且每個群組內容正確"""
        # FC=3 最大長度為 125
        p1 = ReadPoint(name="p1", address=0, data_type=UInt16())
        p2 = ReadPoint(name="p2", address=200, data_type=UInt16())  # 200 + 1 - 0 = 201 > 125
        result = grouper.group([p1, p2])

        assert len(result) == 2
        # 驗證每個群組包含正確的點位
        assert result[0].points == (p1,)
        assert result[0].start_address == 0
        assert result[0].count == 1
        assert result[1].points == (p2,)
        assert result[1].start_address == 200
        assert result[1].count == 1

    def test_exactly_max_length_single_register(self, grouper: PointGrouper):
        """剛好等於最大長度時應為一個群組（單一暫存器類型）"""
        # FC=3 最大長度為 125，位址 0 到 124 剛好 125 個
        p1 = ReadPoint(name="p1", address=0, data_type=UInt16())
        p2 = ReadPoint(name="p2", address=124, data_type=UInt16())
        result = grouper.group([p1, p2])

        assert len(result) == 1
        assert result[0].count == 125

    def test_exactly_max_length_but_last_point_exceeds(self, grouper: PointGrouper):
        """
        剛好最大長度，但最後一個點的 datatype 長度 > 1 時應該分開

        例如：位址 0 和 124，第二個點為 Int32 (佔 2 個暫存器)
        範圍應為 0 ~ 125 (共 126)，超過 125 限制
        """
        p1 = ReadPoint(name="p1", address=0, data_type=UInt16())
        p2 = ReadPoint(name="p2", address=124, data_type=Int32())  # 佔用 124, 125
        result = grouper.group([p1, p2])

        # 範圍 = 124 + 2 - 0 = 126 > 125，應該拆分
        assert len(result) == 2

    def test_coils_max_length_2000(self, grouper: PointGrouper):
        """FC=1 (Read Coils) 應使用 2000 的最大長度"""
        # 使用超過 125 但小於 2000 的範圍
        p1 = ReadPoint(name="p1", address=0, data_type=UInt16(), function_code=FunctionCode.READ_COILS)
        p2 = ReadPoint(name="p2", address=500, data_type=UInt16(), function_code=FunctionCode.READ_COILS)
        result = grouper.group([p1, p2])

        # 501 < 2000，應該合併
        assert len(result) == 1


class TestPointGrouperEdgeCases:
    """邊界情況測試"""

    @pytest.fixture
    def grouper(self) -> PointGrouper:
        return PointGrouper()

    def test_overlapping_addresses(self, grouper: PointGrouper):
        """重疊位址時 count 應正確計算（取最大範圍）"""
        # p1 佔用 100, 101；p2 佔用 101, 102
        p1 = ReadPoint(name="p1", address=100, data_type=Int32())
        p2 = ReadPoint(name="p2", address=101, data_type=Int32())
        result = grouper.group([p1, p2])

        assert len(result) == 1
        # 範圍應為 100 ~ 102，共 3 個暫存器
        assert result[0].start_address == 100
        assert result[0].count == 3

    def test_points_out_of_order(self, grouper: PointGrouper):
        """輸入未排序時仍應正確分組"""
        p1 = ReadPoint(name="p1", address=200, data_type=UInt16())
        p2 = ReadPoint(name="p2", address=100, data_type=UInt16())
        p3 = ReadPoint(name="p3", address=150, data_type=UInt16())
        result = grouper.group([p1, p2, p3])

        # 應該先排序再處理，101 在 125 限制內
        assert len(result) == 1
        assert result[0].start_address == 100
        # points tuple 順序應按位址排序
        assert result[0].points[0].address == 100
        assert result[0].points[1].address == 150
        assert result[0].points[2].address == 200

    def test_multiple_register_types_mixed(self, grouper: PointGrouper):
        """不同 register_count 的資料類型混合時正確處理"""
        p1 = ReadPoint(name="uint16", address=100, data_type=UInt16())  # 1 reg
        p2 = ReadPoint(name="int32", address=101, data_type=Int32())  # 2 regs
        p3 = ReadPoint(name="float32", address=103, data_type=Float32())  # 2 regs
        result = grouper.group([p1, p2, p3])

        assert len(result) == 1
        assert result[0].start_address == 100
        # count = 105 - 100 = 5 (100, 101-102, 103-104)
        assert result[0].count == 5

    def test_complex_scenario_multiple_groups(self, grouper: PointGrouper):
        """
        複合情境：多個 read_group 和 function_code 組合
        應該產生正確數量的群組
        """
        points = [
            ReadPoint(name="a1", address=0, data_type=UInt16(), read_group="a"),
            ReadPoint(name="a2", address=1, data_type=UInt16(), read_group="a"),
            ReadPoint(name="b1", address=0, data_type=UInt16(), read_group="b"),
            ReadPoint(
                name="a_input",
                address=0,
                data_type=UInt16(),
                read_group="a",
                function_code=FunctionCode.READ_INPUT_REGISTERS,
            ),
        ]
        result = grouper.group(points)

        # 應有 3 個群組：
        # 1. read_group="a", FC=3 (a1, a2)
        # 2. read_group="b", FC=3 (b1)
        # 3. read_group="a", FC=4 (a_input)
        assert len(result) == 3
