import pytest

from csp_lib.core.errors import ConfigurationError
from csp_lib.equipment.device.config import DeviceConfig


class TestDeviceConfigEdgeCases:
    def test_device_id_empty_raises(self):
        with pytest.raises(ConfigurationError):
            DeviceConfig(device_id="")

    def test_unit_id_negative_raises(self):
        with pytest.raises(ConfigurationError):
            DeviceConfig(device_id="dev1", unit_id=-1)

    def test_unit_id_256_raises(self):
        with pytest.raises(ConfigurationError):
            DeviceConfig(device_id="dev1", unit_id=256)

    def test_read_interval_zero_raises(self):
        with pytest.raises(ConfigurationError):
            DeviceConfig(device_id="dev1", read_interval=0)

    def test_read_interval_negative_raises(self):
        with pytest.raises(ConfigurationError):
            DeviceConfig(device_id="dev1", read_interval=-1.0)

    def test_disconnect_threshold_zero_raises(self):
        with pytest.raises(ConfigurationError):
            DeviceConfig(device_id="dev1", disconnect_threshold=0)

    def test_max_concurrent_reads_negative_raises(self):
        with pytest.raises(ConfigurationError):
            DeviceConfig(device_id="dev1", max_concurrent_reads=-1)

    def test_max_concurrent_reads_zero_allowed(self):
        """Config allows 0 but GroupReader would reject it"""
        config = DeviceConfig(device_id="dev1", max_concurrent_reads=0)
        assert config.max_concurrent_reads == 0

    def test_valid_boundary_values(self):
        """Boundary values that should be valid"""
        config0 = DeviceConfig(device_id="dev1", unit_id=0)
        assert config0.unit_id == 0
        config255 = DeviceConfig(device_id="dev1", unit_id=255)
        assert config255.unit_id == 255
        config_small = DeviceConfig(device_id="dev1", read_interval=0.001)
        assert config_small.read_interval == 0.001
