import pytest

from csp_lib.controller.services import PVDataService


class TestPVDataServiceEdgeCases:
    def test_max_history_one(self):
        """Only stores one value"""
        svc = PVDataService(max_history=1)
        svc.append(100.0)
        svc.append(200.0)
        assert svc.count == 1
        assert svc.get_latest() == 200.0

    def test_max_history_zero_raises(self):
        with pytest.raises(ValueError):
            PVDataService(max_history=0)

    def test_max_history_negative_raises(self):
        with pytest.raises(ValueError):
            PVDataService(max_history=-1)

    def test_append_beyond_max_history(self):
        svc = PVDataService(max_history=3)
        for i in range(10):
            svc.append(float(i))
        assert svc.count == 3
        assert svc.get_history() == [7.0, 8.0, 9.0]

    def test_get_history_all_none(self):
        svc = PVDataService(max_history=10)
        svc.append(None)
        svc.append(None)
        assert svc.get_history() == []
        assert len(svc) == 0

    def test_get_latest_no_data(self):
        svc = PVDataService(max_history=10)
        assert svc.get_latest() is None

    def test_get_latest_all_none(self):
        svc = PVDataService(max_history=10)
        svc.append(None)
        svc.append(None)
        assert svc.get_latest() is None

    def test_get_average_empty(self):
        svc = PVDataService(max_history=10)
        assert svc.get_average() is None

    def test_clear(self):
        svc = PVDataService(max_history=10)
        svc.append(100.0)
        svc.append(200.0)
        svc.clear()
        assert svc.count == 0
        assert svc.get_latest() is None
