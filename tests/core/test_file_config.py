# =============== Core Tests - FileSinkConfig ===============
#
# FileSinkConfig 檔案 sink 配置單元測試

from __future__ import annotations

import pytest

from csp_lib.core.logging.file_config import FileSinkConfig


class TestFileSinkConfig:
    """FileSinkConfig 不可變配置測試"""

    def test_default_values(self):
        """驗證所有預設值"""
        config = FileSinkConfig(path="/var/log/app.log")
        assert config.path == "/var/log/app.log"
        assert config.rotation == "100 MB"
        assert config.retention == "30 days"
        assert config.compression is None
        assert config.level == "DEBUG"
        assert config.format is None
        assert config.enqueue is True
        assert config.serialize is False
        assert config.encoding == "utf-8"
        assert config.name is None

    def test_frozen(self):
        """frozen=True，不可修改屬性"""
        config = FileSinkConfig(path="/var/log/app.log")
        with pytest.raises(AttributeError):
            config.path = "/other/path"  # type: ignore[misc]

    def test_custom_values(self):
        """自訂所有參數"""
        config = FileSinkConfig(
            path="/custom/path.log",
            rotation="50 MB",
            retention=10,
            compression="zip",
            level="WARNING",
            format="{message}",
            enqueue=False,
            serialize=True,
            encoding="big5",
            name="custom_sink",
        )
        assert config.path == "/custom/path.log"
        assert config.rotation == "50 MB"
        assert config.retention == 10
        assert config.compression == "zip"
        assert config.level == "WARNING"
        assert config.format == "{message}"
        assert config.enqueue is False
        assert config.serialize is True
        assert config.encoding == "big5"
        assert config.name == "custom_sink"

    def test_slots(self):
        """slots=True，不可動態新增屬性"""
        config = FileSinkConfig(path="/var/log/app.log")
        with pytest.raises((AttributeError, TypeError)):
            config.new_attr = "value"  # type: ignore[attr-defined]
