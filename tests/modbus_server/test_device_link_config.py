# =============== Modbus Server Tests - DeviceLinkConfig & MeterAggregationConfig ===============
#
# v0.6.2 新增的設備連結與電表聚合配置驗證測試

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.modbus_server.config import DeviceLinkConfig, MeterAggregationConfig


class TestDeviceLinkConfig:
    """DeviceLinkConfig 驗證測試"""

    def test_valid_creation(self):
        """有效建立"""
        cfg = DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_sub")
        assert cfg.source_device_id == "pcs_1"
        assert cfg.target_meter_id == "meter_sub"
        assert cfg.loss_factor == 0.0

    def test_valid_with_loss_factor(self):
        """有效建立（含 loss_factor）"""
        cfg = DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_sub", loss_factor=0.05)
        assert cfg.loss_factor == 0.05

    def test_empty_source_device_id_raises(self):
        """空 source_device_id 應拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="source_device_id"):
            DeviceLinkConfig(source_device_id="", target_meter_id="meter_sub")

    def test_empty_target_meter_id_raises(self):
        """空 target_meter_id 應拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="target_meter_id"):
            DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="")

    def test_loss_factor_negative_raises(self):
        """loss_factor < 0 應拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="loss_factor"):
            DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_sub", loss_factor=-0.01)

    def test_loss_factor_one_raises(self):
        """loss_factor >= 1.0 應拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="loss_factor"):
            DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_sub", loss_factor=1.0)

    def test_loss_factor_above_one_raises(self):
        """loss_factor > 1.0 應拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="loss_factor"):
            DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_sub", loss_factor=1.5)

    def test_loss_factor_zero_valid(self):
        """loss_factor = 0.0 為合法預設值"""
        cfg = DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_sub", loss_factor=0.0)
        assert cfg.loss_factor == 0.0

    def test_loss_factor_boundary_just_below_one(self):
        """loss_factor = 0.99 為合法邊界值"""
        cfg = DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_sub", loss_factor=0.99)
        assert cfg.loss_factor == 0.99

    def test_frozen(self):
        """frozen dataclass 不可修改"""
        cfg = DeviceLinkConfig(source_device_id="pcs_1", target_meter_id="meter_sub")
        with pytest.raises(FrozenInstanceError):
            cfg.loss_factor = 0.1  # type: ignore[misc]


class TestMeterAggregationConfig:
    """MeterAggregationConfig 驗證測試"""

    def test_valid_creation(self):
        """有效建立"""
        cfg = MeterAggregationConfig(source_meter_ids=("meter_a", "meter_b"), target_meter_id="meter_main")
        assert cfg.source_meter_ids == ("meter_a", "meter_b")
        assert cfg.target_meter_id == "meter_main"

    def test_single_source(self):
        """單一來源也是合法的"""
        cfg = MeterAggregationConfig(source_meter_ids=("meter_a",), target_meter_id="meter_main")
        assert len(cfg.source_meter_ids) == 1

    def test_empty_source_meter_ids_raises(self):
        """空 source_meter_ids 應拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="source_meter_ids"):
            MeterAggregationConfig(source_meter_ids=(), target_meter_id="meter_main")

    def test_target_in_source_raises(self):
        """target 在 source 中應拋 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="target_meter_id"):
            MeterAggregationConfig(source_meter_ids=("meter_main", "meter_b"), target_meter_id="meter_main")

    def test_frozen(self):
        """frozen dataclass 不可修改"""
        cfg = MeterAggregationConfig(source_meter_ids=("meter_a",), target_meter_id="meter_main")
        with pytest.raises(FrozenInstanceError):
            cfg.target_meter_id = "other"  # type: ignore[misc]
