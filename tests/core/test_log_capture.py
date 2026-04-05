# =============== Core Tests - LogCapture ===============
#
# LogCapture 測試用日誌捕獲器測試

from __future__ import annotations

from loguru import logger as _root_logger

from csp_lib.core.logging.capture import CapturedRecord, LogCapture


class TestLogCapture:
    """LogCapture 捕獲器測試"""

    def test_capture_records(self):
        """捕獲 log records"""
        test_logger = _root_logger.bind(module="test.capture")
        with LogCapture() as cap:
            test_logger.info("hello world")
        assert len(cap.records) == 1
        assert cap.records[0].message == "hello world"
        assert cap.records[0].level == "INFO"

    def test_contains(self):
        """contains 子字串匹配"""
        test_logger = _root_logger.bind(module="test.capture")
        with LogCapture() as cap:
            test_logger.info("device connected successfully")
        assert cap.contains("connected")
        assert not cap.contains("disconnected")

    def test_contains_with_level(self):
        """contains 指定等級過濾"""
        test_logger = _root_logger.bind(module="test.capture")
        with LogCapture() as cap:
            test_logger.info("info message")
            test_logger.warning("warning message")
        assert cap.contains("info", level="INFO")
        assert not cap.contains("info", level="WARNING")

    def test_contains_with_module(self):
        """contains 指定模組過濾"""
        logger_a = _root_logger.bind(module="mod_a")
        logger_b = _root_logger.bind(module="mod_b")
        with LogCapture() as cap:
            logger_a.info("from a")
            logger_b.info("from b")
        assert cap.contains("from a", module="mod_a")
        assert not cap.contains("from a", module="mod_b")

    def test_filter_by_level(self):
        """filter 依等級過濾"""
        test_logger = _root_logger.bind(module="test.capture")
        with LogCapture() as cap:
            test_logger.info("info msg")
            test_logger.warning("warn msg")
            test_logger.error("error msg")
        results = cap.filter(level="WARNING")
        assert len(results) == 1
        assert results[0].message == "warn msg"

    def test_filter_by_pattern(self):
        """filter 依正則表達式過濾"""
        test_logger = _root_logger.bind(module="test.capture")
        with LogCapture() as cap:
            test_logger.info("device PCS-01 connected")
            test_logger.info("device PCS-02 connected")
            test_logger.info("alarm triggered")
        results = cap.filter(message_pattern=r"PCS-\d+")
        assert len(results) == 2

    def test_clear(self):
        """clear 清除所有記錄"""
        test_logger = _root_logger.bind(module="test.capture")
        with LogCapture() as cap:
            test_logger.info("msg1")
            test_logger.info("msg2")
            assert len(cap.records) == 2
            cap.clear()
            assert len(cap.records) == 0

    def test_text_property(self):
        """text 屬性回傳以換行分隔的可讀文字"""
        test_logger = _root_logger.bind(module="test.capture")
        with LogCapture() as cap:
            test_logger.info("line1")
            test_logger.info("line2")
        assert "line1" in cap.text
        assert "line2" in cap.text
        assert cap.text == "line1\nline2"

    def test_context_manager_install_uninstall(self):
        """with 自動 install/uninstall sink"""
        cap = LogCapture()
        assert cap._sink_id is None
        with cap:
            assert cap._sink_id is not None
        assert cap._sink_id is None

    def test_captured_record_fields(self):
        """CapturedRecord 包含正確欄位"""
        test_logger = _root_logger.bind(module="test.module")
        with LogCapture() as cap:
            test_logger.info("test msg")
        rec = cap.records[0]
        assert isinstance(rec, CapturedRecord)
        assert rec.level == "INFO"
        assert rec.message == "test msg"
        assert rec.module == "test.module"
        assert rec.time is not None

    def test_capture_with_level_filter(self):
        """初始化指定 level，低於該等級的不捕獲"""
        test_logger = _root_logger.bind(module="test.capture")
        with LogCapture(level="WARNING") as cap:
            test_logger.debug("debug msg")
            test_logger.info("info msg")
            test_logger.warning("warn msg")
        # debug 和 info 低於 WARNING，不應被捕獲
        assert len(cap.records) == 1
        assert cap.records[0].level == "WARNING"
