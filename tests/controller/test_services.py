# =============== Services Tests ===============
#
# 測試 PVDataService

import pytest

from csp_lib.controller.services import PVDataService


class TestPVDataService:
    """PVDataService PV 資料服務測試"""

    def test_init_with_valid_max_history(self):
        """正常初始化"""
        service = PVDataService(max_history=100)
        assert service.max_history == 100
        assert service.count == 0

    def test_init_with_invalid_max_history(self):
        """max_history < 1 應拋出 ValueError"""
        with pytest.raises(ValueError, match="must be at least 1"):
            PVDataService(max_history=0)

    def test_append_and_count(self):
        """append 應增加 count"""
        service = PVDataService(max_history=10)

        service.append(100.0)
        assert service.count == 1

        service.append(200.0)
        assert service.count == 2

    def test_append_with_none(self):
        """append(None) 應計入 count"""
        service = PVDataService(max_history=10)

        service.append(None)
        assert service.count == 1
        assert len(service) == 0  # 有效資料為 0

    def test_max_history_limit(self):
        """超過 max_history 應移除最舊資料"""
        service = PVDataService(max_history=3)

        service.append(1.0)
        service.append(2.0)
        service.append(3.0)
        service.append(4.0)  # 這會移除 1.0

        assert service.count == 3
        history = service.get_history()
        assert history == [2.0, 3.0, 4.0]

    def test_get_history_filters_none(self):
        """get_history 應過濾 None"""
        service = PVDataService(max_history=10)

        service.append(100.0)
        service.append(None)
        service.append(200.0)

        history = service.get_history()
        assert history == [100.0, 200.0]

    def test_get_latest_returns_last_valid(self):
        """get_latest 應返回最新有效值"""
        service = PVDataService(max_history=10)

        service.append(100.0)
        service.append(200.0)
        service.append(None)

        assert service.get_latest() == 200.0

    def test_get_latest_returns_none_when_empty(self):
        """無資料時 get_latest 返回 None"""
        service = PVDataService(max_history=10)
        assert service.get_latest() is None

    def test_get_latest_returns_none_when_all_none(self):
        """全部都是 None 時 get_latest 返回 None"""
        service = PVDataService(max_history=10)
        service.append(None)
        service.append(None)

        assert service.get_latest() is None

    def test_get_average(self):
        """get_average 計算有效資料平均"""
        service = PVDataService(max_history=10)

        service.append(100.0)
        service.append(200.0)
        service.append(300.0)

        assert service.get_average() == 200.0

    def test_get_average_filters_none(self):
        """get_average 應忽略 None"""
        service = PVDataService(max_history=10)

        service.append(100.0)
        service.append(None)
        service.append(200.0)

        assert service.get_average() == 150.0

    def test_get_average_returns_none_when_empty(self):
        """無有效資料時 get_average 返回 None"""
        service = PVDataService(max_history=10)
        assert service.get_average() is None

        service.append(None)
        assert service.get_average() is None

    def test_clear(self):
        """clear 應清空所有資料"""
        service = PVDataService(max_history=10)

        service.append(100.0)
        service.append(200.0)
        service.clear()

        assert service.count == 0
        assert len(service) == 0

    def test_len_returns_valid_count(self):
        """__len__ 返回有效資料筆數 (不含 None)"""
        service = PVDataService(max_history=10)

        service.append(100.0)
        service.append(None)
        service.append(200.0)

        assert len(service) == 2
        assert service.count == 3  # 總筆數

    def test_str_representation(self):
        """__str__ 應包含 count 和 valid"""
        service = PVDataService(max_history=10)
        service.append(100.0)
        service.append(None)

        s = str(service)
        assert "count=2" in s
        assert "valid=1" in s
