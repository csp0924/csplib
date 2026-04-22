"""PVDataService 相容性測試（v0.9.x deprecation path）。

驗證：
1. 建構時觸發 DeprecationWarning
2. 繼承 HistoryBuffer（isinstance True）
3. 所有 HistoryBuffer API 在 subclass 上行為一致
4. __str__ 仍以 PVDataService(...) 為前綴（不繼承父類格式）
"""

import warnings

import pytest

from csp_lib.controller.services import HistoryBuffer, PVDataService


class TestPVDataServiceDeprecation:
    def test_ctor_emits_deprecation_warning(self):
        """建構時應發 DeprecationWarning，訊息指向 HistoryBuffer 與 v1.0 移除計畫"""
        with pytest.warns(DeprecationWarning, match="PVDataService is deprecated"):
            PVDataService()

    def test_deprecation_warning_mentions_migration_target(self):
        with pytest.warns(DeprecationWarning) as record:
            PVDataService(max_history=50)

        msg = str(record[0].message)
        assert "HistoryBuffer" in msg
        assert "v1.0" in msg

    def test_isinstance_history_buffer(self):
        """PVDataService 應為 HistoryBuffer 的 subclass，讓 isinstance 檢查通過"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            svc = PVDataService()

        assert isinstance(svc, HistoryBuffer)


class TestPVDataServiceAPIParity:
    """驗證所有 HistoryBuffer 公開 API 在 PVDataService 上行為完全一致"""

    @pytest.fixture
    def svc(self) -> PVDataService:
        # suppress deprecation 讓 fixture 安靜
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return PVDataService(max_history=5)

    def test_append_and_get_history(self, svc: PVDataService):
        svc.append(100.0)
        svc.append(200.0)
        assert svc.get_history() == [100.0, 200.0]

    def test_append_none_filtered_by_get_history(self, svc: PVDataService):
        svc.append(100.0)
        svc.append(None)
        assert svc.get_history() == [100.0]

    def test_get_latest(self, svc: PVDataService):
        svc.append(100.0)
        svc.append(200.0)
        assert svc.get_latest() == 200.0

    def test_get_latest_skips_trailing_none(self, svc: PVDataService):
        svc.append(100.0)
        svc.append(None)
        assert svc.get_latest() == 100.0

    def test_get_latest_all_none(self, svc: PVDataService):
        svc.append(None)
        svc.append(None)
        assert svc.get_latest() is None

    def test_get_average(self, svc: PVDataService):
        svc.append(100.0)
        svc.append(200.0)
        svc.append(None)
        assert svc.get_average() == 150.0

    def test_get_average_empty_returns_none(self, svc: PVDataService):
        assert svc.get_average() is None

    def test_clear(self, svc: PVDataService):
        svc.append(100.0)
        svc.append(200.0)
        svc.clear()
        assert svc.count == 0
        assert svc.get_latest() is None

    def test_count_includes_none(self, svc: PVDataService):
        svc.append(100.0)
        svc.append(None)
        assert svc.count == 2

    def test_len_excludes_none(self, svc: PVDataService):
        svc.append(100.0)
        svc.append(None)
        assert len(svc) == 1

    def test_max_history_property(self, svc: PVDataService):
        assert svc.max_history == 5

    def test_maxlen_eviction(self, svc: PVDataService):
        for i in range(10):
            svc.append(float(i))
        # max_history=5 from fixture
        assert svc.count == 5
        assert svc.get_history() == [5.0, 6.0, 7.0, 8.0, 9.0]


class TestPVDataServiceValidation:
    """PVDataService 也應承襲 HistoryBuffer 的 max_history 驗證"""

    def test_max_history_zero_raises(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(ValueError, match="max_history"):
                PVDataService(max_history=0)

    def test_max_history_negative_raises(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with pytest.raises(ValueError, match="max_history"):
                PVDataService(max_history=-1)


class TestPVDataServiceStr:
    def test_str_prefix_is_pv_data_service(self):
        """__str__ 應以 PVDataService(...) 開頭（subclass 覆蓋），
        而不是繼承父類的 HistoryBuffer(...) 前綴
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            svc = PVDataService()
            svc.append(100.0)
            svc.append(None)

        s = str(svc)
        assert s.startswith("PVDataService(")
        assert "HistoryBuffer(" not in s
        assert "count=2" in s
        assert "valid=1" in s
