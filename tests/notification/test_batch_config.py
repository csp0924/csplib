# =============== Notification Tests - Batch Config ===============
#
# BatchNotificationConfig 單元測試

from __future__ import annotations

import pytest

from csp_lib.notification import BatchNotificationConfig


class TestBatchNotificationConfig:
    """BatchNotificationConfig 測試"""

    def test_default_values(self):
        """預設值應正確"""
        config = BatchNotificationConfig()
        assert config.flush_interval == 5.0
        assert config.batch_size_threshold == 50
        assert config.max_queue_size == 5000
        assert config.deduplicate_by_key is True

    def test_custom_values(self):
        """自訂值應正確"""
        config = BatchNotificationConfig(
            flush_interval=10.0,
            batch_size_threshold=100,
            max_queue_size=10000,
            deduplicate_by_key=False,
        )
        assert config.flush_interval == 10.0
        assert config.batch_size_threshold == 100
        assert config.max_queue_size == 10000
        assert config.deduplicate_by_key is False

    def test_frozen(self):
        """BatchNotificationConfig 應為不可變"""
        config = BatchNotificationConfig()
        with pytest.raises(AttributeError):
            config.flush_interval = 10.0  # type: ignore[misc]

    def test_negative_flush_interval_raises(self):
        """負數 flush_interval 應拋錯"""
        with pytest.raises(ValueError, match="flush_interval"):
            BatchNotificationConfig(flush_interval=-1.0)

    def test_zero_flush_interval_raises(self):
        """零 flush_interval 應拋錯"""
        with pytest.raises(ValueError, match="flush_interval"):
            BatchNotificationConfig(flush_interval=0)

    def test_negative_batch_size_threshold_raises(self):
        """負數 batch_size_threshold 應拋錯"""
        with pytest.raises(ValueError, match="batch_size_threshold"):
            BatchNotificationConfig(batch_size_threshold=-1)

    def test_zero_batch_size_threshold_raises(self):
        """零 batch_size_threshold 應拋錯"""
        with pytest.raises(ValueError, match="batch_size_threshold"):
            BatchNotificationConfig(batch_size_threshold=0)

    def test_negative_max_queue_size_raises(self):
        """負數 max_queue_size 應拋錯"""
        with pytest.raises(ValueError, match="max_queue_size"):
            BatchNotificationConfig(max_queue_size=-1)

    def test_zero_max_queue_size_raises(self):
        """零 max_queue_size 應拋錯"""
        with pytest.raises(ValueError, match="max_queue_size"):
            BatchNotificationConfig(max_queue_size=0)
