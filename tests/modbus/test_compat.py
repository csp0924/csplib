from unittest.mock import MagicMock, patch

from csp_lib.modbus.clients.compat import _get_pymodbus_version, slave_kwarg


class TestCompat:
    def setup_method(self):
        _get_pymodbus_version.cache_clear()

    def test_slave_kwarg_new_api(self):
        _get_pymodbus_version.cache_clear()
        with patch("csp_lib.modbus.clients.compat._get_pymodbus_version", return_value=(3, 10, 0)):
            result = slave_kwarg(5)
            assert result == {"device_id": 5}

    def test_slave_kwarg_old_api(self):
        _get_pymodbus_version.cache_clear()
        with patch("csp_lib.modbus.clients.compat._get_pymodbus_version", return_value=(3, 9, 0)):
            result = slave_kwarg(5)
            assert result == {"slave": 5}

    def test_version_with_dev_suffix(self):
        """Handles '3.10.0-dev' version string correctly"""
        _get_pymodbus_version.cache_clear()
        mock_pymodbus = MagicMock()
        mock_pymodbus.__version__ = "3.10.0-dev"
        with patch.dict("sys.modules", {"pymodbus": mock_pymodbus}):
            result = _get_pymodbus_version()
            assert result == (3, 10, 0)

    def test_version_import_error(self):
        """When pymodbus not installed, defaults to (3, 10, 0)"""
        _get_pymodbus_version.cache_clear()
        with patch.dict("sys.modules", {"pymodbus": None}):
            # Importing a module mapped to None raises ImportError
            result = _get_pymodbus_version()
            assert result == (3, 10, 0)

    def teardown_method(self):
        _get_pymodbus_version.cache_clear()
