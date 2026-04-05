# =============== Core Tests - SinkManager ===============
#
# SinkManager 全域 sink 管理器單元測試

from __future__ import annotations

import io

import pytest

from csp_lib.core.logging.sink_manager import SinkInfo, SinkManager


@pytest.fixture(autouse=True)
def _reset_sink_manager():
    """每個測試前後重置 SinkManager 單例，避免跨測試污染"""
    SinkManager.reset()
    yield
    SinkManager.reset()


class TestSinkManagerSingleton:
    """SinkManager 單例測試"""

    def test_singleton(self):
        """get_instance 回傳同一實例"""
        mgr1 = SinkManager.get_instance()
        mgr2 = SinkManager.get_instance()
        assert mgr1 is mgr2

    def test_reset(self):
        """reset 後回傳新實例"""
        mgr1 = SinkManager.get_instance()
        SinkManager.reset()
        mgr2 = SinkManager.get_instance()
        assert mgr1 is not mgr2


class TestSinkManagerAddRemove:
    """SinkManager sink 新增/移除測試"""

    def test_add_sink(self):
        """add_sink 回傳 int sink_id"""
        mgr = SinkManager.get_instance()
        buf = io.StringIO()
        sink_id = mgr.add_sink(buf, name="test_buf", sink_type="custom")
        assert isinstance(sink_id, int)
        assert len(mgr.list_sinks()) == 1

    def test_remove_sink(self):
        """remove_sink 後 list_sinks 不含該 sink"""
        mgr = SinkManager.get_instance()
        buf = io.StringIO()
        sink_id = mgr.add_sink(buf, name="test_buf")
        mgr.remove_sink(sink_id)
        assert len(mgr.list_sinks()) == 0

    def test_remove_sink_not_found(self):
        """移除不存在的 sink_id 拋 KeyError"""
        mgr = SinkManager.get_instance()
        with pytest.raises(KeyError, match="不存在"):
            mgr.remove_sink(99999)

    def test_remove_sink_by_name(self):
        """依名稱移除 sink"""
        mgr = SinkManager.get_instance()
        buf = io.StringIO()
        mgr.add_sink(buf, name="named_sink")
        mgr.remove_sink_by_name("named_sink")
        assert len(mgr.list_sinks()) == 0

    def test_remove_sink_by_name_not_found(self):
        """依名稱移除不存在的 sink 拋 KeyError"""
        mgr = SinkManager.get_instance()
        with pytest.raises(KeyError, match="不存在"):
            mgr.remove_sink_by_name("nonexistent")

    def test_remove_all(self):
        """remove_all 移除所有 sink"""
        mgr = SinkManager.get_instance()
        mgr.add_sink(io.StringIO(), name="s1")
        mgr.add_sink(io.StringIO(), name="s2")
        assert len(mgr.list_sinks()) == 2
        mgr.remove_all()
        assert len(mgr.list_sinks()) == 0


class TestSinkManagerQuery:
    """SinkManager 查詢測試"""

    def test_list_sinks(self):
        """list_sinks 回傳 SinkInfo list"""
        mgr = SinkManager.get_instance()
        mgr.add_sink(io.StringIO(), name="s1", sink_type="custom")
        sinks = mgr.list_sinks()
        assert len(sinks) == 1
        assert isinstance(sinks[0], SinkInfo)
        assert sinks[0].name == "s1"

    def test_get_sink(self):
        """依名稱查詢 sink"""
        mgr = SinkManager.get_instance()
        mgr.add_sink(io.StringIO(), name="findme", sink_type="custom")
        info = mgr.get_sink("findme")
        assert info is not None
        assert info.name == "findme"
        assert info.sink_type == "custom"

    def test_get_sink_not_found(self):
        """查詢不存在的名稱回傳 None"""
        mgr = SinkManager.get_instance()
        assert mgr.get_sink("ghost") is None

    def test_diagnose_false_default(self):
        """SinkInfo 預設 is_active 為 True，且 add_sink diagnose 預設 False 不影響 SinkInfo"""
        mgr = SinkManager.get_instance()
        sid = mgr.add_sink(io.StringIO(), name="diag_test")
        info = mgr.get_sink("diag_test")
        assert info is not None
        assert info.is_active is True
        assert info.sink_id == sid


class TestSinkManagerLevel:
    """SinkManager 等級控制測試"""

    def test_set_level_updates_filter(self):
        """set_level 更新 LogFilter 的預設等級"""
        mgr = SinkManager.get_instance()
        mgr.set_level("DEBUG")
        assert mgr.filter.default_level == "DEBUG"

    def test_set_level_module(self):
        """設定模組專屬等級"""
        mgr = SinkManager.get_instance()
        mgr.set_level("TRACE", module="csp_lib.mongo")
        assert mgr.filter.get_effective_level("csp_lib.mongo") == "TRACE"

    def test_set_level_does_not_change_sink_count(self):
        """set_level 不摧毀/重建 sink（sink 數量不變）"""
        mgr = SinkManager.get_instance()
        mgr.add_sink(io.StringIO(), name="stable")
        count_before = len(mgr.list_sinks())
        mgr.set_level("DEBUG")
        mgr.set_level("WARNING")
        count_after = len(mgr.list_sinks())
        assert count_before == count_after


class TestSinkManagerFileSink:
    """SinkManager file sink 測試"""

    def test_add_file_sink(self, tmp_path):
        """FileSinkConfig → add_file_sink 成功"""
        from csp_lib.core.logging.file_config import FileSinkConfig

        config = FileSinkConfig(
            path=str(tmp_path / "test.log"),
            rotation=None,
            retention=None,
            name="file_test",
        )
        mgr = SinkManager.get_instance()
        sid = mgr.add_file_sink(config)
        assert isinstance(sid, int)

        info = mgr.get_sink("file_test")
        assert info is not None
        assert info.sink_type == "file"

    def test_add_file_sink_auto_name(self, tmp_path):
        """FileSinkConfig.name 為 None 時使用 file:{path} 作為名稱"""
        from csp_lib.core.logging.file_config import FileSinkConfig

        log_path = str(tmp_path / "auto.log")
        config = FileSinkConfig(path=log_path, rotation=None, retention=None)
        mgr = SinkManager.get_instance()
        mgr.add_file_sink(config)

        info = mgr.get_sink(f"file:{log_path}")
        assert info is not None


class TestSinkManagerAsyncSink:
    """SinkManager async sink 測試"""

    async def test_add_async_sink(self):
        """async handler sink 成功新增"""
        received: list[str] = []

        async def handler(msg: str) -> None:
            received.append(msg)

        mgr = SinkManager.get_instance()
        sid = mgr.add_async_sink(handler, name="async_test")
        assert isinstance(sid, int)

        info = mgr.get_sink("async_test")
        assert info is not None
        assert info.sink_type == "async"
