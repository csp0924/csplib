# =============== Core Tests - LogFilter ===============
#
# LogFilter 模組等級過濾器單元測試

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from csp_lib.core.logging.filter import LogFilter


class TestLogFilter:
    """LogFilter 等級過濾器測試"""

    # ---- 預設等級 ----

    def test_default_level(self):
        """預設等級為 INFO"""
        f = LogFilter()
        assert f.default_level == "INFO"

    def test_set_default_level(self):
        """透過 property setter 設定預設等級"""
        f = LogFilter()
        f.default_level = "DEBUG"
        assert f.default_level == "DEBUG"

    def test_init_custom_default_level(self):
        """初始化時指定預設等級"""
        f = LogFilter(default_level="WARNING")
        assert f.default_level == "WARNING"

    def test_invalid_level_raises(self):
        """無效等級拋出 ValueError"""
        with pytest.raises(ValueError, match="無效的 log 等級"):
            LogFilter(default_level="INVALID")

    def test_invalid_level_setter_raises(self):
        """setter 設定無效等級拋出 ValueError"""
        f = LogFilter()
        with pytest.raises(ValueError, match="無效的 log 等級"):
            f.default_level = "NOTREAL"

    # ---- 模組等級操作 ----

    def test_set_module_level(self):
        """設定模組專屬等級"""
        f = LogFilter()
        f.set_module_level("csp_lib.mongo", "DEBUG")
        assert f.module_levels == {"csp_lib.mongo": "DEBUG"}

    def test_set_module_level_invalid_raises(self):
        """設定模組等級時，無效等級拋出 ValueError"""
        f = LogFilter()
        with pytest.raises(ValueError):
            f.set_module_level("csp_lib.mongo", "FAKE")

    def test_remove_module_level(self):
        """移除模組等級設定"""
        f = LogFilter()
        f.set_module_level("csp_lib.mongo", "DEBUG")
        f.remove_module_level("csp_lib.mongo")
        assert f.module_levels == {}

    def test_remove_module_level_nonexistent(self):
        """移除不存在的模組等級不拋例外"""
        f = LogFilter()
        f.remove_module_level("nonexistent")  # 不應拋錯

    # ---- get_effective_level ----

    def test_get_effective_level_exact(self):
        """精確匹配模組名稱"""
        f = LogFilter()
        f.set_module_level("csp_lib.mongo", "DEBUG")
        assert f.get_effective_level("csp_lib.mongo") == "DEBUG"

    def test_get_effective_level_prefix(self):
        """前綴匹配：csp_lib.mongo 匹配 csp_lib.mongo.writer"""
        f = LogFilter()
        f.set_module_level("csp_lib.mongo", "DEBUG")
        assert f.get_effective_level("csp_lib.mongo.writer") == "DEBUG"

    def test_get_effective_level_longest_prefix(self):
        """最長前綴優先"""
        f = LogFilter()
        f.set_module_level("csp_lib", "WARNING")
        f.set_module_level("csp_lib.mongo", "DEBUG")
        assert f.get_effective_level("csp_lib.mongo.writer") == "DEBUG"
        assert f.get_effective_level("csp_lib.redis") == "WARNING"

    def test_get_effective_level_default(self):
        """無匹配時回傳預設等級"""
        f = LogFilter(default_level="ERROR")
        assert f.get_effective_level("unregistered.module") == "ERROR"

    def test_get_effective_level_no_partial_match(self):
        """不應部分匹配（csp_lib.mon 不應匹配 csp_lib.mongo 的規則）"""
        f = LogFilter()
        f.set_module_level("csp_lib.mongo", "DEBUG")
        # csp_lib.mon 不是 csp_lib.mongo 的前綴也不是精確匹配
        assert f.get_effective_level("csp_lib.mon") == "INFO"

    # ---- __call__ ----

    def test_call_filters_by_level(self):
        """__call__ 根據等級過濾 record"""
        from loguru import logger as _root_logger

        f = LogFilter(default_level="WARNING")

        # 建立模擬 record
        info_no = _root_logger.level("INFO").no
        warning_no = _root_logger.level("WARNING").no

        record_info = {
            "extra": {"module": "test"},
            "level": MagicMock(no=info_no),
        }
        record_warning = {
            "extra": {"module": "test"},
            "level": MagicMock(no=warning_no),
        }

        assert f(record_info) is False  # INFO < WARNING → 過濾
        assert f(record_warning) is True  # WARNING >= WARNING → 通過

    def test_call_respects_module_level(self):
        """__call__ 遵循模組專屬等級"""
        from loguru import logger as _root_logger

        f = LogFilter(default_level="WARNING")
        f.set_module_level("csp_lib.mongo", "DEBUG")

        debug_no = _root_logger.level("DEBUG").no
        record = {
            "extra": {"module": "csp_lib.mongo"},
            "level": MagicMock(no=debug_no),
        }
        assert f(record) is True  # DEBUG >= DEBUG → 通過

    # ---- module_levels property ----

    def test_module_levels_returns_copy(self):
        """module_levels property 回傳副本，修改不影響原始"""
        f = LogFilter()
        f.set_module_level("csp_lib.mongo", "DEBUG")
        levels = f.module_levels
        levels["csp_lib.redis"] = "ERROR"
        assert "csp_lib.redis" not in f.module_levels

    # ---- 等級大小寫正規化 ----

    def test_level_case_insensitive(self):
        """等級字串大小寫不敏感"""
        f = LogFilter(default_level="info")
        assert f.default_level == "INFO"
        f.set_module_level("test", "debug")
        assert f.module_levels["test"] == "DEBUG"
