# =============== Equipment Device Tests - Config ===============
#
# DeviceConfig 設備設定單元測試
#
# 測試覆蓋：
# - 正常建立
# - 預設值
# - 各欄位驗證

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.equipment.device.config import DeviceConfig


class TestDeviceConfigCreation:
    """DeviceConfig 建立測試"""

    def test_create_with_required_fields(self):
        """只提供必填欄位應成功建立"""
        config = DeviceConfig(device_id="inverter_001")

        assert config.device_id == "inverter_001"
        assert config.unit_id == 1
        assert config.address_offset == 0
        assert config.read_interval == 1.0
        assert config.disconnect_threshold == 5
        assert config.max_concurrent_reads == 1

    def test_create_with_all_fields(self):
        """提供所有欄位應成功建立"""
        config = DeviceConfig(
            device_id="battery_001",
            unit_id=10,
            address_offset=1,
            read_interval=0.5,
            disconnect_threshold=3,
            max_concurrent_reads=2,
        )

        assert config.device_id == "battery_001"
        assert config.unit_id == 10
        assert config.address_offset == 1
        assert config.read_interval == 0.5
        assert config.disconnect_threshold == 3
        assert config.max_concurrent_reads == 2

    def test_frozen_immutable(self):
        """frozen=True 應使物件不可變"""
        config = DeviceConfig(device_id="test")

        with pytest.raises(FrozenInstanceError):
            config.device_id = "changed"


class TestDeviceConfigValidation:
    """DeviceConfig 驗證測試"""

    def test_device_id_empty_raises(self):
        """device_id 為空應拋錯"""
        with pytest.raises(ConfigurationError, match="device_id 不可為空"):
            DeviceConfig(device_id="")

    def test_unit_id_boundary_valid(self):
        """unit_id 邊界值應有效"""
        # 最小值
        config_min = DeviceConfig(device_id="test", unit_id=0)
        assert config_min.unit_id == 0

        # 最大值
        config_max = DeviceConfig(device_id="test", unit_id=255)
        assert config_max.unit_id == 255

    def test_unit_id_below_range_raises(self):
        """unit_id < 0 應拋錯"""
        with pytest.raises(ConfigurationError, match="unit_id 必須在 0-255 範圍內"):
            DeviceConfig(device_id="test", unit_id=-1)

    def test_unit_id_above_range_raises(self):
        """unit_id > 255 應拋錯"""
        with pytest.raises(ConfigurationError, match="unit_id 必須在 0-255 範圍內"):
            DeviceConfig(device_id="test", unit_id=256)

    def test_read_interval_zero_raises(self):
        """read_interval = 0 應拋錯"""
        with pytest.raises(ConfigurationError, match="read_interval 必須 > 0"):
            DeviceConfig(device_id="test", read_interval=0)

    def test_read_interval_negative_raises(self):
        """read_interval < 0 應拋錯"""
        with pytest.raises(ConfigurationError, match="read_interval 必須 > 0"):
            DeviceConfig(device_id="test", read_interval=-1.0)

    def test_read_interval_small_valid(self):
        """read_interval 極小正值應有效"""
        config = DeviceConfig(device_id="test", read_interval=0.001)
        assert config.read_interval == 0.001

    def test_disconnect_threshold_zero_raises(self):
        """disconnect_threshold = 0 應拋錯"""
        with pytest.raises(ConfigurationError, match="disconnect_threshold 必須 >= 1"):
            DeviceConfig(device_id="test", disconnect_threshold=0)

    def test_disconnect_threshold_min_valid(self):
        """disconnect_threshold = 1 應有效"""
        config = DeviceConfig(device_id="test", disconnect_threshold=1)
        assert config.disconnect_threshold == 1

    def test_max_concurrent_reads_negative_raises(self):
        """max_concurrent_reads < 0 應拋錯"""
        with pytest.raises(ConfigurationError, match="max_concurrent_reads 必須 >= 0"):
            DeviceConfig(device_id="test", max_concurrent_reads=-1)

    def test_max_concurrent_reads_zero_valid(self):
        """max_concurrent_reads = 0 應有效（表示不限制）"""
        config = DeviceConfig(device_id="test", max_concurrent_reads=0)
        assert config.max_concurrent_reads == 0

    def test_address_offset_negative_valid(self):
        """address_offset 負值應有效（某些設備可能需要）"""
        config = DeviceConfig(device_id="test", address_offset=-1)
        assert config.address_offset == -1


class TestDeviceConfigEquality:
    """DeviceConfig 相等性測試"""

    def test_same_values_equal(self):
        """相同值應相等"""
        config1 = DeviceConfig(device_id="test", unit_id=1)
        config2 = DeviceConfig(device_id="test", unit_id=1)

        assert config1 == config2

    def test_different_device_id_not_equal(self):
        """不同 device_id 應不相等"""
        config1 = DeviceConfig(device_id="test1")
        config2 = DeviceConfig(device_id="test2")

        assert config1 != config2

    def test_hashable(self):
        """frozen dataclass 應可雜湊"""
        config = DeviceConfig(device_id="test")
        config_set = {config}

        assert config in config_set
