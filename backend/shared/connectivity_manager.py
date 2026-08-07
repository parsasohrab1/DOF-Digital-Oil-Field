"""
Connectivity Manager for 5G and Satellite connections
Manages multiple connectivity options for remote oil field locations
"""
import logging
import asyncio
import socket
import time
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    """Connection type enumeration"""

    ETHERNET = "ethernet"
    WIFI = "wifi"
    CELLULAR_4G = "cellular_4g"
    CELLULAR_5G = "cellular_5g"
    SATELLITE = "satellite"
    MESH = "mesh"


class ConnectionStatus(Enum):
    """Connection status"""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ERROR = "error"


class ConnectivityManager:
    """
    Manages multiple connectivity options with automatic failover
    """

    def __init__(self):
        self.connections: Dict[str, Dict[str, any]] = {}
        self.active_connection: Optional[str] = None
        self.connection_priority = [
            ConnectionType.ETHERNET,
            ConnectionType.CELLULAR_5G,
            ConnectionType.CELLULAR_4G,
            ConnectionType.SATELLITE,
            ConnectionType.WIFI,
        ]
        self.monitoring_task = None
        self.monitoring_interval = 30  # seconds

    def register_connection(
        self,
        connection_id: str,
        connection_type: ConnectionType,
        config: Dict[str, any],
    ):
        """Register a connection option"""
        self.connections[connection_id] = {
            "type": connection_type,
            "config": config,
            "status": ConnectionStatus.DISCONNECTED,
            "last_check": None,
            "latency": None,
            "bandwidth": None,
            "cost_per_mb": config.get("cost_per_mb", 0),
            "priority": self.connection_priority.index(connection_type)
            if connection_type in self.connection_priority
            else 999,
        }
        logger.info(f"Registered connection: {connection_id} ({connection_type.value})")

    async def check_connection(
        self, connection_id: str
    ) -> Tuple[bool, Optional[float]]:
        """Check if connection is available and measure latency"""
        if connection_id not in self.connections:
            return False, None

        conn = self.connections[connection_id]
        conn_type = conn["type"]
        config = conn["config"]

        try:
            if conn_type == ConnectionType.ETHERNET:
                return await self._check_ethernet(config)
            elif (
                conn_type == ConnectionType.CELLULAR_5G
                or conn_type == ConnectionType.CELLULAR_4G
            ):
                return await self._check_cellular(config)
            elif conn_type == ConnectionType.SATELLITE:
                return await self._check_satellite(config)
            elif conn_type == ConnectionType.WIFI:
                return await self._check_wifi(config)
            else:
                return False, None
        except Exception as e:
            logger.error(f"Error checking connection {connection_id}: {e}")
            return False, None

    async def _check_ethernet(self, config: Dict[str, any]) -> Tuple[bool, float]:
        """Check Ethernet connection"""
        host = config.get("host", "8.8.8.8")
        port = config.get("port", 53)

        start = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            latency = (time.time() - start) * 1000  # ms

            return result == 0, latency
        except Exception:
            return False, None

    async def _check_cellular(self, config: Dict[str, any]) -> Tuple[bool, float]:
        """Check cellular (4G/5G) connection"""
        # Similar to Ethernet but may have different endpoints
        host = config.get("test_host", "8.8.8.8")
        port = config.get("test_port", 53)

        start = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)  # Longer timeout for cellular
            result = sock.connect_ex((host, port))
            sock.close()
            latency = (time.time() - start) * 1000  # ms

            return result == 0, latency
        except Exception:
            return False, None

    async def _check_satellite(self, config: Dict[str, any]) -> Tuple[bool, float]:
        """Check satellite connection"""
        # Satellite connections typically have higher latency
        host = config.get("satellite_gateway", "8.8.8.8")
        port = config.get("port", 53)

        start = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)  # Longer timeout for satellite
            result = sock.connect_ex((host, port))
            sock.close()
            latency = (time.time() - start) * 1000  # ms

            return result == 0, latency
        except Exception:
            return False, None

    async def _check_wifi(self, config: Dict[str, any]) -> Tuple[bool, float]:
        """Check WiFi connection"""
        return await self._check_ethernet(config)

    async def select_best_connection(self) -> Optional[str]:
        """Select best available connection based on priority, latency, and cost"""
        available_connections = []

        for conn_id, conn in self.connections.items():
            is_available, latency = await self.check_connection(conn_id)

            if is_available:
                conn["status"] = ConnectionStatus.CONNECTED
                conn["latency"] = latency
                conn["last_check"] = datetime.utcnow()

                # Score based on priority, latency, and cost
                score = (
                    (1000 - conn["priority"] * 100)
                    + (1000 - min(latency or 1000, 1000))  # Priority (lower is better)
                    + (  # Latency (lower is better)
                        1000 - min(conn["cost_per_mb"] * 100, 1000)
                    )  # Cost (lower is better)
                )

                available_connections.append((conn_id, score, latency))
            else:
                conn["status"] = ConnectionStatus.DISCONNECTED

        if not available_connections:
            return None

        # Sort by score (higher is better)
        available_connections.sort(key=lambda x: x[1], reverse=True)
        best_connection = available_connections[0][0]

        if best_connection != self.active_connection:
            logger.info(
                f"Switching to connection: {best_connection} (latency: {available_connections[0][2]:.2f}ms)"
            )
            self.active_connection = best_connection

        return best_connection

    async def start_monitoring(self):
        """Start continuous monitoring of connections"""
        while True:
            try:
                await self.select_best_connection()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"Error in connection monitoring: {e}")
                await asyncio.sleep(self.monitoring_interval)

    def get_active_connection(self) -> Optional[Dict[str, any]]:
        """Get information about active connection"""
        if self.active_connection and self.active_connection in self.connections:
            conn = self.connections[self.active_connection].copy()
            conn["connection_id"] = self.active_connection
            return conn
        return None

    def get_all_connections(self) -> List[Dict[str, any]]:
        """Get status of all connections"""
        result = []
        for conn_id, conn in self.connections.items():
            conn_info = conn.copy()
            conn_info["connection_id"] = conn_id
            conn_info["is_active"] = conn_id == self.active_connection
            result.append(conn_info)
        return result


# Global instance
connectivity_manager = ConnectivityManager()
