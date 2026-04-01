# =============== Modbus Exceptions Tests ===============
#
# 測試 Modbus 例外類型定義與繼承結構

import pytest

from csp_lib.modbus.exceptions import (
    ModbusCircuitBreakerError,
    ModbusConfigError,
    ModbusDecodeError,
    ModbusEncodeError,
    ModbusError,
    ModbusQueueFullError,
)

# =============== ModbusError (Base) Tests ===============


class TestModbusError:
    """ModbusError 基礎例外測試"""

    def test_is_subclass_of_exception(self):
        """ModbusError 應為 Exception 的子類別"""
        assert issubclass(ModbusError, Exception)

    def test_instantiate_with_message(self):
        """可以帶訊息實例化"""
        err = ModbusError("something went wrong")
        assert str(err) == "something went wrong"

    def test_instantiate_without_message(self):
        """可以不帶訊息實例化"""
        err = ModbusError()
        assert str(err) == ""

    def test_raise_and_catch(self):
        """可以拋出並捕捉"""
        with pytest.raises(ModbusError, match="test error"):
            raise ModbusError("test error")

    def test_raise_and_catch_as_exception(self):
        """可以用 Exception 捕捉"""
        with pytest.raises(ModbusError):
            raise ModbusError("base error")


# =============== ModbusEncodeError Tests ===============


class TestModbusEncodeError:
    """ModbusEncodeError 編碼錯誤測試"""

    def test_is_subclass_of_modbus_error(self):
        """應為 ModbusError 的子類別"""
        assert issubclass(ModbusEncodeError, ModbusError)

    def test_is_subclass_of_exception(self):
        """應為 Exception 的子類別 (透過 ModbusError)"""
        assert issubclass(ModbusEncodeError, Exception)

    def test_instantiate_with_message(self):
        """可以帶訊息實例化"""
        err = ModbusEncodeError("value out of range")
        assert str(err) == "value out of range"

    def test_isinstance_of_modbus_error(self):
        """實例應為 ModbusError 的 isinstance"""
        err = ModbusEncodeError("encode failed")
        assert isinstance(err, ModbusError)

    def test_raise_and_catch_by_parent(self):
        """可以用 ModbusError 捕捉"""
        with pytest.raises(ModbusError):
            raise ModbusEncodeError("int16 overflow")

    def test_not_instance_of_sibling(self):
        """不應為兄弟類別的 isinstance"""
        err = ModbusEncodeError("encode")
        assert not isinstance(err, ModbusDecodeError)


# =============== ModbusDecodeError Tests ===============


class TestModbusDecodeError:
    """ModbusDecodeError 解碼錯誤測試"""

    def test_is_subclass_of_modbus_error(self):
        """應為 ModbusError 的子類別"""
        assert issubclass(ModbusDecodeError, ModbusError)

    def test_is_subclass_of_exception(self):
        """應為 Exception 的子類別 (透過 ModbusError)"""
        assert issubclass(ModbusDecodeError, Exception)

    def test_instantiate_with_message(self):
        """可以帶訊息實例化"""
        err = ModbusDecodeError("insufficient register data")
        assert str(err) == "insufficient register data"

    def test_isinstance_of_modbus_error(self):
        """實例應為 ModbusError 的 isinstance"""
        err = ModbusDecodeError("decode failed")
        assert isinstance(err, ModbusError)

    def test_raise_and_catch_by_parent(self):
        """可以用 ModbusError 捕捉"""
        with pytest.raises(ModbusError):
            raise ModbusDecodeError("invalid IEEE 754")

    def test_not_instance_of_sibling(self):
        """不應為兄弟類別的 isinstance"""
        err = ModbusDecodeError("decode")
        assert not isinstance(err, ModbusEncodeError)


# =============== ModbusConfigError Tests ===============


class TestModbusConfigError:
    """ModbusConfigError 設定錯誤測試"""

    def test_is_subclass_of_modbus_error(self):
        """應為 ModbusError 的子類別"""
        assert issubclass(ModbusConfigError, ModbusError)

    def test_is_subclass_of_exception(self):
        """應為 Exception 的子類別 (透過 ModbusError)"""
        assert issubclass(ModbusConfigError, Exception)

    def test_instantiate_with_message(self):
        """可以帶訊息實例化"""
        err = ModbusConfigError("invalid port number")
        assert str(err) == "invalid port number"

    def test_isinstance_of_modbus_error(self):
        """實例應為 ModbusError 的 isinstance"""
        err = ModbusConfigError("config error")
        assert isinstance(err, ModbusError)

    def test_raise_and_catch_by_parent(self):
        """可以用 ModbusError 捕捉"""
        with pytest.raises(ModbusError):
            raise ModbusConfigError("negative port")

    def test_not_instance_of_sibling(self):
        """不應為兄弟類別的 isinstance"""
        err = ModbusConfigError("config")
        assert not isinstance(err, ModbusEncodeError)
        assert not isinstance(err, ModbusDecodeError)


# =============== ModbusCircuitBreakerError Tests ===============


class TestModbusCircuitBreakerError:
    """ModbusCircuitBreakerError 斷路器錯誤測試"""

    def test_is_subclass_of_modbus_error(self):
        """應為 ModbusError 的子類別"""
        assert issubclass(ModbusCircuitBreakerError, ModbusError)

    def test_is_subclass_of_exception(self):
        """應為 Exception 的子類別 (透過 ModbusError)"""
        assert issubclass(ModbusCircuitBreakerError, Exception)

    def test_instantiate_with_unit_id_only(self):
        """只帶 unit_id 時應產生預設訊息"""
        err = ModbusCircuitBreakerError(unit_id=5)
        assert err.unit_id == 5
        assert "Circuit breaker is open for unit_id=5" in str(err)

    def test_instantiate_with_unit_id_and_message(self):
        """帶 unit_id 和自訂訊息時應使用自訂訊息"""
        err = ModbusCircuitBreakerError(unit_id=3, message="custom error")
        assert err.unit_id == 3
        assert "custom error" in str(err)

    def test_default_message_format_various_ids(self):
        """不同 unit_id 應產生對應的預設訊息"""
        for uid in (0, 1, 127, 255):
            err = ModbusCircuitBreakerError(unit_id=uid)
            assert f"Circuit breaker is open for unit_id={uid}" in str(err)
            assert err.unit_id == uid

    def test_unit_id_attribute_is_set(self):
        """unit_id 屬性應被正確設定"""
        err = ModbusCircuitBreakerError(unit_id=42)
        assert err.unit_id == 42

    def test_message_none_uses_default(self):
        """message=None 時應使用預設訊息"""
        err = ModbusCircuitBreakerError(unit_id=10, message=None)
        assert "Circuit breaker is open for unit_id=10" in str(err)

    def test_isinstance_of_modbus_error(self):
        """實例應為 ModbusError 的 isinstance"""
        err = ModbusCircuitBreakerError(unit_id=1)
        assert isinstance(err, ModbusError)

    def test_raise_and_catch_by_parent(self):
        """可以用 ModbusError 捕捉"""
        with pytest.raises(ModbusError):
            raise ModbusCircuitBreakerError(unit_id=7)

    def test_raise_and_catch_specific(self):
        """可以用 ModbusCircuitBreakerError 精確捕捉"""
        with pytest.raises(ModbusCircuitBreakerError) as exc_info:
            raise ModbusCircuitBreakerError(unit_id=99, message="breaker open")
        assert exc_info.value.unit_id == 99
        assert "breaker open" in str(exc_info.value)

    def test_not_instance_of_sibling(self):
        """不應為兄弟類別的 isinstance"""
        err = ModbusCircuitBreakerError(unit_id=1)
        assert not isinstance(err, ModbusEncodeError)
        assert not isinstance(err, ModbusDecodeError)
        assert not isinstance(err, ModbusConfigError)
        assert not isinstance(err, ModbusQueueFullError)

    def test_args_tuple_contains_message(self):
        """Exception.args 應包含訊息字串"""
        err = ModbusCircuitBreakerError(unit_id=5)
        assert "Circuit breaker is open for unit_id=5" in err.args[0]

    def test_args_tuple_with_custom_message(self):
        """自訂訊息時 Exception.args 應包含自訂訊息"""
        err = ModbusCircuitBreakerError(unit_id=5, message="my message")
        assert "my message" in err.args[0]


# =============== ModbusQueueFullError Tests ===============


class TestModbusQueueFullError:
    """ModbusQueueFullError 佇列已滿錯誤測試"""

    def test_is_subclass_of_modbus_error(self):
        """應為 ModbusError 的子類別"""
        assert issubclass(ModbusQueueFullError, ModbusError)

    def test_is_subclass_of_exception(self):
        """應為 Exception 的子類別 (透過 ModbusError)"""
        assert issubclass(ModbusQueueFullError, Exception)

    def test_instantiate_with_message(self):
        """可以帶訊息實例化"""
        err = ModbusQueueFullError("queue capacity reached")
        assert str(err) == "queue capacity reached"

    def test_isinstance_of_modbus_error(self):
        """實例應為 ModbusError 的 isinstance"""
        err = ModbusQueueFullError("full")
        assert isinstance(err, ModbusError)

    def test_raise_and_catch_by_parent(self):
        """可以用 ModbusError 捕捉"""
        with pytest.raises(ModbusError):
            raise ModbusQueueFullError("queue full")

    def test_not_instance_of_sibling(self):
        """不應為兄弟類別的 isinstance"""
        err = ModbusQueueFullError("full")
        assert not isinstance(err, ModbusEncodeError)
        assert not isinstance(err, ModbusDecodeError)
        assert not isinstance(err, ModbusConfigError)
        assert not isinstance(err, ModbusCircuitBreakerError)


# =============== Hierarchy & Cross-Cutting Tests ===============


class TestExceptionHierarchy:
    """例外繼承結構交叉測試"""

    ALL_SUBCLASSES = [
        ModbusEncodeError,
        ModbusDecodeError,
        ModbusConfigError,
        ModbusCircuitBreakerError,
        ModbusQueueFullError,
    ]

    def test_all_are_subclass_of_modbus_error(self):
        """所有子類別都應是 ModbusError 的子類別"""
        for cls in self.ALL_SUBCLASSES:
            assert issubclass(cls, ModbusError), f"{cls.__name__} should be a subclass of ModbusError"

    def test_all_are_subclass_of_exception(self):
        """所有子類別都應是 Exception 的子類別"""
        for cls in self.ALL_SUBCLASSES:
            assert issubclass(cls, Exception), f"{cls.__name__} should be a subclass of Exception"

    def test_modbus_error_is_not_subclass_of_children(self):
        """ModbusError 不應為子類別的子類別"""
        for cls in self.ALL_SUBCLASSES:
            assert not issubclass(ModbusError, cls), f"ModbusError should not be a subclass of {cls.__name__}"

    def test_siblings_are_not_subclass_of_each_other(self):
        """兄弟類別之間不應有繼承關係"""
        for i, cls_a in enumerate(self.ALL_SUBCLASSES):
            for j, cls_b in enumerate(self.ALL_SUBCLASSES):
                if i != j:
                    assert not issubclass(cls_a, cls_b), (
                        f"{cls_a.__name__} should not be a subclass of {cls_b.__name__}"
                    )

    def test_catch_all_with_modbus_error(self):
        """所有子類別拋出時都能被 ModbusError 捕捉"""
        for cls in self.ALL_SUBCLASSES:
            if cls is ModbusCircuitBreakerError:
                exc = cls(unit_id=1)
            else:
                exc = cls("test")
            with pytest.raises(ModbusError):
                raise exc

    def test_modbus_error_does_not_catch_unrelated(self):
        """ModbusError 不應捕捉非相關例外"""
        with pytest.raises(ValueError):
            raise ValueError("unrelated")
