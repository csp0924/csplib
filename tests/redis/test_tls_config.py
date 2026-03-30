"""Tests for TLSConfig ca_certs optional behavior."""

import pytest

from csp_lib.redis.client import TLSConfig


class TestTLSConfigCaCertsOptional:
    def test_cert_reqs_none_without_ca_certs_valid(self):
        """cert_reqs='none' should work without ca_certs."""
        config = TLSConfig(cert_reqs="none")
        assert config.ca_certs is None
        assert config.cert_reqs == "none"

    def test_cert_reqs_required_without_ca_certs_raises(self):
        """cert_reqs='required' without ca_certs should raise ValueError."""
        with pytest.raises(ValueError, match="ca_certs"):
            TLSConfig(cert_reqs="required")

    def test_cert_reqs_optional_without_ca_certs_raises(self):
        """cert_reqs='optional' without ca_certs should raise ValueError."""
        with pytest.raises(ValueError, match="ca_certs"):
            TLSConfig(cert_reqs="optional")

    def test_cert_reqs_required_with_ca_certs_valid(self):
        config = TLSConfig(ca_certs="/path/to/ca.crt", cert_reqs="required")
        assert config.ca_certs == "/path/to/ca.crt"

    def test_cert_reqs_none_with_ca_certs_valid(self):
        """cert_reqs='none' with ca_certs is also valid."""
        config = TLSConfig(ca_certs="/path/to/ca.crt", cert_reqs="none")
        assert config.ca_certs == "/path/to/ca.crt"

    def test_cert_reqs_none_with_mutual_tls(self):
        """cert_reqs='none' with client cert/key should work."""
        config = TLSConfig(
            cert_reqs="none",
            certfile="/path/to/client.crt",
            keyfile="/path/to/client.key",
        )
        assert config.certfile is not None
        assert config.keyfile is not None

    def test_to_ssl_context_none_mode(self):
        """TLSConfig with cert_reqs='none' should produce an SSLContext."""
        config = TLSConfig(cert_reqs="none")
        ssl_ctx = config.to_ssl_context()
        assert ssl_ctx is not None

    def test_default_cert_reqs_is_required(self):
        """Default cert_reqs should be 'required'."""
        # Without providing ca_certs, this must raise because default is "required"
        with pytest.raises(ValueError):
            TLSConfig()
