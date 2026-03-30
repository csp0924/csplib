"""Tests for AddressWhitelistValidator."""

from csp_lib.modbus_gateway.protocol import WriteValidator
from csp_lib.modbus_gateway.validators import AddressWhitelistValidator


class TestAddressWhitelistValidator:
    def test_satisfies_protocol(self):
        v = AddressWhitelistValidator({"power"})
        assert isinstance(v, WriteValidator)

    def test_allowed_register_accepted(self):
        v = AddressWhitelistValidator({"power", "voltage"})
        assert v.validate("power", 100) is True
        assert v.validate("voltage", 220) is True

    def test_disallowed_register_rejected(self):
        v = AddressWhitelistValidator({"power"})
        assert v.validate("firmware_version", 42) is False

    def test_empty_whitelist_rejects_all(self):
        v = AddressWhitelistValidator(set())
        assert v.validate("anything", 0) is False

    def test_value_does_not_affect_decision(self):
        """Whitelist only checks register name, not value."""
        v = AddressWhitelistValidator({"power"})
        assert v.validate("power", -999999) is True
        assert v.validate("power", None) is True
        assert v.validate("power", "string_value") is True

    def test_whitelist_is_frozen(self):
        """Modifying the original set should not affect the validator."""
        allowed = {"power"}
        v = AddressWhitelistValidator(allowed)
        allowed.add("secret")
        assert v.validate("secret", 0) is False
