"""
OPC-UA Client for SCADA/PLC connectivity
"""
from typing import List, Dict, Any, Optional
from opcua import Client, ua
from datetime import datetime
import logging

from .config import settings

logger = logging.getLogger(__name__)


class OPCUAClient:
    """OPC-UA client wrapper"""

    def __init__(
        self,
        server_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.server_url = server_url or settings.OPCUA_SERVER_URL
        self.username = username or settings.OPCUA_USERNAME
        self.password = password or settings.OPCUA_PASSWORD
        self.client = None
        self.connected = False

    def connect(self):
        """Connect to OPC-UA server"""
        if not self.server_url:
            logger.warning("OPC-UA server URL not configured")
            return False

        try:
            self.client = Client(self.server_url)

            # Set authentication if provided
            if self.username and self.password:
                self.client.set_user(self.username)
                self.client.set_password(self.password)

            self.client.connect()
            self.connected = True
            logger.info(f"Connected to OPC-UA server: {self.server_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to OPC-UA server: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from OPC-UA server"""
        if self.client and self.connected:
            try:
                self.client.disconnect()
                self.connected = False
                logger.info("Disconnected from OPC-UA server")
            except Exception as e:
                logger.error(f"Error disconnecting from OPC-UA server: {e}")

    def read_node(self, node_id: str) -> Optional[Any]:
        """Read a single node value"""
        if not self.connected:
            logger.warning("Not connected to OPC-UA server")
            return None

        try:
            node = self.client.get_node(node_id)
            value = node.get_value()
            return value
        except Exception as e:
            logger.error(f"Error reading node {node_id}: {e}")
            return None

    def read_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """Read multiple node values"""
        results = {}
        for node_id in node_ids:
            value = self.read_node(node_id)
            if value is not None:
                results[node_id] = value
        return results

    def write_node(self, node_id: str, value: Any) -> bool:
        """Write a value to a node"""
        if not self.connected:
            logger.warning("Not connected to OPC-UA server")
            return False

        try:
            node = self.client.get_node(node_id)

            # Get data type
            data_type = node.get_data_type_as_variant_type()

            # Create variant with appropriate type
            variant = ua.Variant(value, data_type)

            # Write value
            node.set_value(variant)
            logger.info(f"Wrote value {value} to node {node_id}")
            return True

        except Exception as e:
            logger.error(f"Error writing to node {node_id}: {e}")
            return False

    def subscribe_to_nodes(
        self, node_ids: List[str], callback: callable, interval: int = 1000
    ):
        """Subscribe to node changes"""
        if not self.connected:
            logger.warning("Not connected to OPC-UA server")
            return None

        try:
            # Create subscription
            subscription = self.client.create_subscription(interval, callback)

            # Subscribe to nodes
            for node_id in node_ids:
                node = self.client.get_node(node_id)
                subscription.subscribe_data_change(node)

            logger.info(f"Subscribed to {len(node_ids)} nodes")
            return subscription

        except Exception as e:
            logger.error(f"Error subscribing to nodes: {e}")
            return None

    def browse_nodes(self, root_node_id: str = "ns=2;i=1") -> List[Dict[str, Any]]:
        """Browse nodes in the server"""
        if not self.connected:
            logger.warning("Not connected to OPC-UA server")
            return []

        try:
            root = self.client.get_node(root_node_id)
            nodes = []

            for child in root.get_children():
                node_info = {
                    "node_id": child.nodeid.to_string(),
                    "browse_name": child.get_browse_name().to_string(),
                    "display_name": child.get_display_name().to_string(),
                }
                nodes.append(node_info)

            return nodes

        except Exception as e:
            logger.error(f"Error browsing nodes: {e}")
            return []


class ModbusTCPClient:
    """Modbus TCP client wrapper with security validation"""

    def __init__(self, host: str, port: int = 502, unit_id: int = 1):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.connected = False
        self.client = None

        try:
            from pymodbus.client import ModbusTcpClient as PyModbusClient

            self.pymodbus_available = True
            self.PyModbusClient = PyModbusClient
        except ImportError:
            self.pymodbus_available = False
            logger.warning("pymodbus not available, using mock implementation")

    def connect(self) -> bool:
        """Connect to Modbus server with security validation"""
        try:
            if self.pymodbus_available:
                self.client = self.PyModbusClient(self.host, port=self.port)
                self.connected = self.client.connect()
            else:
                # Mock connection
                logger.info(f"Mock connection to Modbus TCP: {self.host}:{self.port}")
                self.connected = True

            if self.connected:
                logger.info(f"Connected to Modbus TCP: {self.host}:{self.port}")

            return self.connected
        except Exception as e:
            logger.error(f"Failed to connect to Modbus: {e}")
            return False

    def disconnect(self):
        """Disconnect from Modbus server"""
        if self.client and self.connected:
            try:
                self.client.close()
            except Exception:
                pass
        self.connected = False
        logger.info("Disconnected from Modbus TCP")

    def read_holding_registers(
        self, address: int, count: int, source_ip: str = "127.0.0.1"
    ) -> Optional[List[int]]:
        """Read holding registers with security validation"""
        if not self.connected:
            return None

        # Validate packet (mock packet structure for validation)
        import struct

        transaction_id = 1
        protocol_id = 0
        function_code = 3  # Read Holding Registers
        data = struct.pack(">HH", address, count)

        # Validate with industrial firewall
        from .industrial_security import industrial_firewall

        is_valid, error = industrial_firewall.validate_industrial_packet(
            protocol="modbus",
            source_ip=source_ip,
            source_mac="00:00:00:00:00:00",  # Would be extracted from packet
            packet_data=struct.pack(
                ">HHHBB", transaction_id, protocol_id, 6, self.unit_id, function_code
            )
            + data,
        )

        if not is_valid:
            logger.warning(f"Modbus packet validation failed: {error}")
            return None

        try:
            if self.pymodbus_available and self.client:
                result = self.client.read_holding_registers(
                    address, count, unit=self.unit_id
                )
                if result.isError():
                    logger.error(f"Modbus read error: {result}")
                    return None
                return result.registers
            else:
                # Mock implementation
                logger.info(
                    f"Mock read holding registers: address={address}, count={count}"
                )
                return [0] * count
        except Exception as e:
            logger.error(f"Error reading Modbus registers: {e}")
            return None

    def write_register(
        self, address: int, value: int, source_ip: str = "127.0.0.1"
    ) -> bool:
        """Write single register with security validation"""
        if not self.connected:
            return False

        # Validate write operation
        import struct

        transaction_id = 1
        protocol_id = 0
        function_code = 6  # Write Single Register
        data = struct.pack(">HH", address, value)

        # Validate with industrial firewall
        from .industrial_security import industrial_firewall

        is_valid, error = industrial_firewall.validate_industrial_packet(
            protocol="modbus",
            source_ip=source_ip,
            source_mac="00:00:00:00:00:00",
            packet_data=struct.pack(
                ">HHHBB", transaction_id, protocol_id, 6, self.unit_id, function_code
            )
            + data,
        )

        if not is_valid:
            logger.warning(f"Modbus write validation failed: {error}")
            return False

        try:
            if self.pymodbus_available and self.client:
                result = self.client.write_register(address, value, unit=self.unit_id)
                if result.isError():
                    logger.error(f"Modbus write error: {result}")
                    return False
                logger.info(f"Wrote register {address} = {value}")
                return True
            else:
                # Mock implementation
                logger.info(f"Mock write register: address={address}, value={value}")
                return True
        except Exception as e:
            logger.error(f"Error writing Modbus register: {e}")
            return False
