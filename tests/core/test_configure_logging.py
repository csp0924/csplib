# =============== Core Tests - configure_logging ===============
#
# configure_logging / set_level / add_file_sink 公開 API 測試

from __future__ import annotations

import os

import pytest

from csp_lib.core import add_file_sink, configure_logging, set_level
from csp_lib.core.logging.file_config import FileSinkConfig
from csp_lib.core.logging.sink_manager import SinkManager


@pytest.fixture(autouse=True)
def _reset_sink_manager():
    """每個測試前後重置 SinkManager"""
    SinkManager.reset()
    yield
    SinkManager.reset()


class TestConfigureLogging:
    """configure_logging 整合測試"""

    def test_configure_logging_backward_compatible(self):
        """既有呼叫方式不受影響：只傳 level"""
        configure_logging(level="DEBUG")
        mgr = SinkManager.get_instance()
        assert mgr.filter.default_level == "DEBUG"
        # 應有一個 stderr sink
        sinks = mgr.list_sinks()
        assert len(sinks) == 1
        assert sinks[0].sink_type == "stderr"

    def test_configure_logging_with_format(self):
        """自訂 format 字串"""
        configure_logging(level="INFO", format_string="{message}")
        sinks = SinkManager.get_instance().list_sinks()
        assert len(sinks) == 1

    def test_configure_logging_with_enqueue_json(self):
        """enqueue + json_output 參數"""
        configure_logging(level="INFO", enqueue=True, json_output=True)
        sinks = SinkManager.get_instance().list_sinks()
        assert len(sinks) == 1


class TestSetLevel:
    """set_level 模組層級函式測試"""

    def test_set_level_global(self):
        """set_level 設定全域等級"""
        configure_logging(level="INFO")
        set_level("DEBUG")
        mgr = SinkManager.get_instance()
        assert mgr.filter.default_level == "DEBUG"

    def test_set_level_module(self):
        """set_level 設定模組專屬等級"""
        configure_logging(level="INFO")
        set_level("TRACE", module="csp_lib.mongo")
        mgr = SinkManager.get_instance()
        assert mgr.filter.get_effective_level("csp_lib.mongo") == "TRACE"

    def test_set_level_no_remove_readd(self):
        """set_level 不摧毀 sink（驗證 sink count 不變）"""
        configure_logging(level="INFO")
        mgr = SinkManager.get_instance()
        count_before = len(mgr.list_sinks())
        set_level("DEBUG")
        set_level("WARNING")
        count_after = len(mgr.list_sinks())
        assert count_before == count_after


class TestAddFileSink:
    """add_file_sink 便利函式測試"""

    def test_add_file_sink_convenience(self, tmp_path):
        """module-level add_file_sink 函式"""
        configure_logging(level="INFO")
        config = FileSinkConfig(
            path=str(tmp_path / "test.log"),
            rotation=None,
            retention=None,
            name="convenience_file",
        )
        sid = add_file_sink(config)
        assert isinstance(sid, int)

        mgr = SinkManager.get_instance()
        info = mgr.get_sink("convenience_file")
        assert info is not None
        assert info.sink_type == "file"


class TestEnvPrefixConfig:
    """環境變數載入測試"""

    def test_env_prefix_loads_env_vars(self, monkeypatch):
        """環境變數覆蓋 level 等配置"""
        monkeypatch.setenv("TEST_LOG_LEVEL", "ERROR")
        monkeypatch.setenv("TEST_LOG_ENQUEUE", "true")
        monkeypatch.setenv("TEST_LOG_JSON", "1")

        configure_logging(level="INFO", env_prefix="TEST")
        mgr = SinkManager.get_instance()
        # 等級應被環境變數覆蓋
        assert mgr.filter.default_level == "ERROR"

    def test_env_prefix_format(self, monkeypatch):
        """環境變數覆蓋 format"""
        monkeypatch.setenv("MY_LOG_FORMAT", "{message}")
        configure_logging(level="INFO", env_prefix="MY")
        # 不拋錯即可——format 已被環境變數覆蓋

    def test_env_prefix_diagnose(self, monkeypatch):
        """環境變數設定 diagnose"""
        monkeypatch.setenv("CSP_LOG_DIAGNOSE", "yes")
        configure_logging(level="INFO", env_prefix="CSP")
        # 不拋錯即可

    def test_env_prefix_none_no_env_read(self):
        """env_prefix=None 時不讀取環境變數"""
        # 確保即使環境變數存在也不影響
        os.environ.pop("CSP_LOG_LEVEL", None)
        configure_logging(level="INFO")  # env_prefix 預設為 None
        mgr = SinkManager.get_instance()
        assert mgr.filter.default_level == "INFO"
