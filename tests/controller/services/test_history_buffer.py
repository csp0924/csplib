"""HistoryBuffer 單元測試

通用時序緩衝區，取代舊 PVDataService 語義化綁定。
涵蓋 CRUD、None 佔位過濾、邊界值、maxlen 淘汰、`__len__` / `__str__`。
"""

import pytest

from csp_lib.controller.services import HistoryBuffer


class TestHistoryBufferBasicCRUD:
    def test_append_and_get_history(self):
        buf = HistoryBuffer(max_history=10)
        buf.append(100.0)
        buf.append(200.0)
        buf.append(300.0)

        assert buf.get_history() == [100.0, 200.0, 300.0]
        assert buf.count == 3

    def test_empty_buffer_initial_state(self):
        buf = HistoryBuffer(max_history=10)

        assert buf.get_history() == []
        assert buf.get_latest() is None
        assert buf.get_average() is None
        assert buf.count == 0
        assert len(buf) == 0


class TestHistoryBufferNoneHandling:
    def test_append_none_as_placeholder(self):
        """None 佔位應保留 slot 但被 get_history 過濾"""
        buf = HistoryBuffer(max_history=10)
        buf.append(100.0)
        buf.append(None)
        buf.append(200.0)

        # count 含 None，get_history 不含
        assert buf.count == 3
        assert buf.get_history() == [100.0, 200.0]

    def test_get_latest_skips_trailing_none(self):
        """get_latest 應跳過末端 None 取最新有效值"""
        buf = HistoryBuffer(max_history=10)
        buf.append(100.0)
        buf.append(200.0)
        buf.append(None)
        buf.append(None)

        assert buf.get_latest() == 200.0

    def test_get_latest_all_none_returns_none(self):
        buf = HistoryBuffer(max_history=10)
        buf.append(None)
        buf.append(None)

        assert buf.get_latest() is None

    def test_get_average_filters_none(self):
        buf = HistoryBuffer(max_history=10)
        buf.append(100.0)
        buf.append(None)
        buf.append(200.0)
        buf.append(None)
        buf.append(300.0)

        # 有效值為 [100, 200, 300]，平均 200
        assert buf.get_average() == 200.0

    def test_get_average_all_none_returns_none(self):
        buf = HistoryBuffer(max_history=10)
        buf.append(None)
        buf.append(None)

        assert buf.get_average() is None

    def test_get_average_empty_buffer_returns_none(self):
        buf = HistoryBuffer(max_history=10)

        assert buf.get_average() is None


class TestHistoryBufferClear:
    def test_clear_removes_all_data(self):
        buf = HistoryBuffer(max_history=10)
        buf.append(100.0)
        buf.append(200.0)
        buf.append(None)

        buf.clear()

        assert buf.count == 0
        assert len(buf) == 0
        assert buf.get_history() == []
        assert buf.get_latest() is None
        assert buf.get_average() is None

    def test_can_append_after_clear(self):
        buf = HistoryBuffer(max_history=10)
        buf.append(100.0)
        buf.clear()
        buf.append(200.0)

        assert buf.get_latest() == 200.0
        assert buf.count == 1


class TestHistoryBufferMaxHistoryProperty:
    def test_max_history_property_returns_ctor_value(self):
        buf = HistoryBuffer(max_history=42)
        assert buf.max_history == 42

    def test_default_max_history_is_300(self):
        buf = HistoryBuffer()
        assert buf.max_history == 300


class TestHistoryBufferMaxHistoryValidation:
    """max_history 邊界驗證 — fail-loud（bug-validation-fail-loud 原則）"""

    def test_max_history_zero_raises(self):
        with pytest.raises(ValueError, match="max_history"):
            HistoryBuffer(max_history=0)

    def test_max_history_negative_raises(self):
        with pytest.raises(ValueError, match="max_history"):
            HistoryBuffer(max_history=-1)

    def test_max_history_one_is_valid(self):
        """max_history=1 是合法的（邊界最小值）"""
        buf = HistoryBuffer(max_history=1)
        buf.append(100.0)
        buf.append(200.0)

        # 只保留最後一筆
        assert buf.count == 1
        assert buf.get_latest() == 200.0


class TestHistoryBufferMaxLenEviction:
    def test_append_beyond_max_history_evicts_oldest(self):
        """超過 max_history 時最舊的值被擠出（deque maxlen 語義）"""
        buf = HistoryBuffer(max_history=3)
        for i in range(10):
            buf.append(float(i))

        assert buf.count == 3
        assert buf.get_history() == [7.0, 8.0, 9.0]
        assert buf.get_latest() == 9.0

    def test_eviction_with_none_values(self):
        """None 佔位也會被淘汰（佔 slot）"""
        buf = HistoryBuffer(max_history=3)
        buf.append(100.0)
        buf.append(None)
        buf.append(200.0)
        buf.append(300.0)  # 擠掉 100.0

        # 內部存 [None, 200, 300]；有效值只 [200, 300]
        assert buf.count == 3
        assert buf.get_history() == [200.0, 300.0]


class TestHistoryBufferLen:
    def test_len_counts_only_valid_values(self):
        """__len__ 回傳有效值數（不含 None）"""
        buf = HistoryBuffer(max_history=10)
        buf.append(100.0)
        buf.append(None)
        buf.append(200.0)
        buf.append(None)

        # count=4 (含 None)；len=2 (有效值)
        assert buf.count == 4
        assert len(buf) == 2

    def test_len_empty_buffer(self):
        buf = HistoryBuffer(max_history=10)
        assert len(buf) == 0


class TestHistoryBufferStr:
    def test_str_format(self):
        """__str__ 格式應包含類名、count、valid"""
        buf = HistoryBuffer(max_history=10)
        buf.append(100.0)
        buf.append(None)

        s = str(buf)
        assert "HistoryBuffer" in s
        assert "count=2" in s
        assert "valid=1" in s

    def test_str_empty_buffer(self):
        buf = HistoryBuffer(max_history=10)
        s = str(buf)
        assert "HistoryBuffer" in s
        assert "count=0" in s
        assert "valid=0" in s


class TestHistoryBufferFloatPrecision:
    """邊界值：float 精度與特殊值"""

    def test_zero_value(self):
        buf = HistoryBuffer()
        buf.append(0.0)
        assert buf.get_latest() == 0.0
        assert buf.get_average() == 0.0
        assert len(buf) == 1  # 0.0 是有效值，不是 None

    def test_negative_values(self):
        buf = HistoryBuffer()
        buf.append(-100.0)
        buf.append(-200.0)
        assert buf.get_average() == -150.0
