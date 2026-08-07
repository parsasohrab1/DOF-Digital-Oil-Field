"""
Mutual TLS (mTLS) Manager for Inter-Service Communication
مدیریت mTLS برای ارتباطات بین میکروسرویس‌ها
"""
import os
import ssl
import logging
from pathlib import Path
from typing import Optional, Dict
import httpx

logger = logging.getLogger(__name__)


class MTLSManager:
    """
    Manages mTLS certificates and SSL contexts for inter-service communication
    """

    def __init__(
        self,
        cert_dir: Optional[str] = None,
        ca_cert_path: Optional[str] = None,
        client_cert_path: Optional[str] = None,
        client_key_path: Optional[str] = None,
    ):
        self.cert_dir = (
            Path(cert_dir) if cert_dir else Path(__file__).parent.parent / "certs"
        )
        self.cert_dir.mkdir(parents=True, exist_ok=True)

        # Certificate paths
        self.ca_cert_path = (
            Path(ca_cert_path) if ca_cert_path else self.cert_dir / "ca.crt"
        )
        self.client_cert_path = (
            Path(client_cert_path) if client_cert_path else self.cert_dir / "client.crt"
        )
        self.client_key_path = (
            Path(client_key_path) if client_key_path else self.cert_dir / "client.key"
        )

        self.mtls_enabled = self._check_certificates()

    def _check_certificates(self) -> bool:
        """Check if all required certificates exist"""
        required = [self.ca_cert_path, self.client_cert_path, self.client_key_path]

        all_exist = all(path.exists() for path in required)

        if not all_exist:
            logger.warning(
                "mTLS certificates not found. mTLS disabled. "
                f"Required: {[str(p) for p in required]}"
            )
            return False

        logger.info("mTLS certificates found. mTLS enabled.")
        return True

    def create_ssl_context(self, verify: bool = True) -> Optional[ssl.SSLContext]:
        """
        Create SSL context for mTLS

        Args:
            verify: Whether to verify server certificates

        Returns:
            SSLContext or None if mTLS not enabled
        """
        if not self.mtls_enabled:
            return None

        try:
            context = ssl.create_default_context()

            # Load CA certificate for server verification
            if verify and self.ca_cert_path.exists():
                context.load_verify_locations(str(self.ca_cert_path))
            else:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            # Load client certificate and key
            if self.client_cert_path.exists() and self.client_key_path.exists():
                context.load_cert_chain(
                    str(self.client_cert_path), str(self.client_key_path)
                )

            return context
        except Exception as e:
            logger.error(f"Failed to create SSL context: {e}")
            return None

    def get_httpx_client_kwargs(self, verify: bool = True) -> Dict:
        """
        Get kwargs for httpx.AsyncClient with mTLS

        Args:
            verify: Whether to verify server certificates

        Returns:
            Dictionary with httpx client configuration
        """
        if not self.mtls_enabled:
            return {}

        ssl_context = self.create_ssl_context(verify=verify)

        if ssl_context:
            return {
                "verify": str(self.ca_cert_path) if verify else False,
                "cert": (str(self.client_cert_path), str(self.client_key_path)),
            }

        return {}

    def get_httpx_sync_client_kwargs(self, verify: bool = True) -> Dict:
        """Get kwargs for httpx.Client with mTLS"""
        return self.get_httpx_client_kwargs(verify=verify)


# Global mTLS manager instance
_global_mtls_manager: Optional[MTLSManager] = None


def get_mtls_manager(
    cert_dir: Optional[str] = None,
    ca_cert_path: Optional[str] = None,
    client_cert_path: Optional[str] = None,
    client_key_path: Optional[str] = None,
) -> MTLSManager:
    """Get or create global mTLS manager"""
    global _global_mtls_manager
    if _global_mtls_manager is None:
        _global_mtls_manager = MTLSManager(
            cert_dir=cert_dir,
            ca_cert_path=ca_cert_path,
            client_cert_path=client_cert_path,
            client_key_path=client_key_path,
        )
    return _global_mtls_manager
