"""
Tests for shared.mtls_manager: certificate discovery and SSL context / httpx
client kwargs construction for inter-service mTLS.
"""

import ssl

import pytest

from shared.mtls_manager import MTLSManager


def _write_fake_pem(path, marker: str):
    path.write_text(
        f"-----BEGIN {marker}-----\nnot-a-real-cert\n-----END {marker}-----\n"
    )


class TestCertificateDiscovery:
    def test_mtls_disabled_when_certificates_are_missing(self, tmp_path):
        manager = MTLSManager(cert_dir=str(tmp_path))
        assert manager.mtls_enabled is False

    def test_mtls_enabled_when_all_three_certificates_present(self, tmp_path):
        _write_fake_pem(tmp_path / "ca.crt", "CERTIFICATE")
        _write_fake_pem(tmp_path / "client.crt", "CERTIFICATE")
        _write_fake_pem(tmp_path / "client.key", "PRIVATE KEY")

        manager = MTLSManager(cert_dir=str(tmp_path))
        assert manager.mtls_enabled is True

    def test_mtls_disabled_when_only_some_certificates_present(self, tmp_path):
        _write_fake_pem(tmp_path / "ca.crt", "CERTIFICATE")
        # client.crt / client.key intentionally missing

        manager = MTLSManager(cert_dir=str(tmp_path))
        assert manager.mtls_enabled is False

    def test_cert_dir_is_created_if_missing(self, tmp_path):
        target = tmp_path / "nested" / "certs"
        assert not target.exists()
        MTLSManager(cert_dir=str(target))
        assert target.exists()


class TestSSLContextAndClientKwargs:
    def test_create_ssl_context_returns_none_when_mtls_disabled(self, tmp_path):
        manager = MTLSManager(cert_dir=str(tmp_path))
        assert manager.create_ssl_context() is None

    def test_get_httpx_client_kwargs_empty_when_mtls_disabled(self, tmp_path):
        manager = MTLSManager(cert_dir=str(tmp_path))
        assert manager.get_httpx_client_kwargs() == {}

    def test_get_httpx_sync_client_kwargs_delegates_to_async_variant(self, tmp_path):
        manager = MTLSManager(cert_dir=str(tmp_path))
        assert (
            manager.get_httpx_sync_client_kwargs() == manager.get_httpx_client_kwargs()
        )

    def test_create_ssl_context_with_invalid_pem_content_fails_closed(self, tmp_path):
        """The fake PEMs above aren't real certs, so loading them into an
        actual ssl.SSLContext must fail -- and the manager must catch that
        and return None (fail closed) rather than raising or silently
        producing a context nothing was actually verified against."""
        _write_fake_pem(tmp_path / "ca.crt", "CERTIFICATE")
        _write_fake_pem(tmp_path / "client.crt", "CERTIFICATE")
        _write_fake_pem(tmp_path / "client.key", "PRIVATE KEY")

        manager = MTLSManager(cert_dir=str(tmp_path))
        assert manager.mtls_enabled is True
        assert manager.create_ssl_context() is None

    def test_get_httpx_client_kwargs_empty_when_ssl_context_creation_fails(
        self, tmp_path
    ):
        _write_fake_pem(tmp_path / "ca.crt", "CERTIFICATE")
        _write_fake_pem(tmp_path / "client.crt", "CERTIFICATE")
        _write_fake_pem(tmp_path / "client.key", "PRIVATE KEY")

        manager = MTLSManager(cert_dir=str(tmp_path))
        assert manager.get_httpx_client_kwargs() == {}
