"""
Connection Monitor for detecting online/offline status
"""
import logging
import socket
import time
import threading
from typing import Callable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ConnectionMonitor:
    """
    Monitors network connectivity to detect online/offline status
    """

    def __init__(
        self,
        check_interval: int = 5,  # Check interval in seconds
        timeout: int = 3,  # Connection timeout in seconds
        check_urls: Optional[list] = None,  # URLs to check
        check_hosts: Optional[list] = None,  # Hosts to check (host:port)
    ):
        self.check_interval = check_interval
        self.timeout = timeout
        self.check_urls = check_urls or []
        self.check_hosts = check_hosts or []
        self.is_online = True
        self.last_check_time = None
        self.last_success_time = None
        self.consecutive_failures = 0
        self.lock = threading.RLock()
        self.callbacks: list[Callable[[bool], None]] = []

        # Start monitoring thread
        self._monitoring_thread = None
        self._running = False

    def add_callback(self, callback: Callable[[bool], None]):
        """Add callback to be called when connection status changes"""
        with self.lock:
            self.callbacks.append(callback)

    def remove_callback(self, callback: Callable[[bool], None]):
        """Remove callback"""
        with self.lock:
            if callback in self.callbacks:
                self.callbacks.remove(callback)

    def _notify_callbacks(self, is_online: bool):
        """Notify all callbacks of status change"""
        with self.lock:
            for callback in self.callbacks:
                try:
                    callback(is_online)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    def check_connection(self) -> bool:
        """
        Check if connection is available

        Returns:
            True if online, False if offline
        """
        # Check hosts first (faster)
        for host_port in self.check_hosts:
            if ":" in host_port:
                host, port = host_port.split(":", 1)
                port = int(port)
            else:
                host = host_port
                port = 80

            if self._check_host(host, port):
                return True

        # Check URLs
        for url in self.check_urls:
            if self._check_url(url):
                return True

        return False

    def _check_host(self, host: str, port: int) -> bool:
        """Check if host:port is reachable"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.debug(f"Host check failed for {host}:{port}: {e}")
            return False

    def _check_url(self, url: str) -> bool:
        """Check if URL is reachable"""
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return self._check_host(host, port)
        except Exception as e:
            logger.debug(f"URL check failed for {url}: {e}")
            return False

    def start_monitoring(self):
        """Start continuous monitoring"""
        if self._running:
            return

        self._running = True

        def monitor_worker():
            while self._running:
                try:
                    is_online = self.check_connection()
                    self.last_check_time = time.time()

                    with self.lock:
                        previous_status = self.is_online

                        if is_online:
                            self.consecutive_failures = 0
                            self.last_success_time = time.time()
                            if not previous_status:
                                # Status changed from offline to online
                                logger.info(
                                    "Connection restored - system is now ONLINE"
                                )
                                self.is_online = True
                                self._notify_callbacks(True)
                        else:
                            self.consecutive_failures += 1
                            if previous_status:
                                # Status changed from online to offline
                                logger.warning(
                                    f"Connection lost - system is now OFFLINE (failures: {self.consecutive_failures})"
                                )
                                self.is_online = False
                                self._notify_callbacks(False)

                except Exception as e:
                    logger.error(f"Monitoring error: {e}")

                time.sleep(self.check_interval)

        self._monitoring_thread = threading.Thread(target=monitor_worker, daemon=True)
        self._monitoring_thread.start()
        logger.info("Connection monitoring started")

    def stop_monitoring(self):
        """Stop continuous monitoring"""
        self._running = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("Connection monitoring stopped")

    def get_status(self) -> dict:
        """Get current connection status"""
        with self.lock:
            return {
                "is_online": self.is_online,
                "last_check_time": self.last_check_time,
                "last_success_time": self.last_success_time,
                "consecutive_failures": self.consecutive_failures,
                "check_interval": self.check_interval,
            }
