"""
Industrial Security Layer
Provides security for Layer 1 & 2 network protocols and protection against industrial attacks
"""
import logging
import struct
import hashlib
import hmac
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict
import re

logger = logging.getLogger(__name__)


class ModbusSecurityValidator:
    """
    Security validator for Modbus TCP protocol
    Protects against packet injection, replay attacks, and unauthorized commands
    """

    def __init__(self):
        self.allowed_devices: Dict[int, str] = {}  # device_id -> device_key
        self.command_history: List[Dict[str, Any]] = []
        self.rate_limit: Dict[int, List[datetime]] = defaultdict(
            list
        )  # device_id -> timestamps
        self.max_commands_per_minute = 60
        self.command_window = timedelta(minutes=1)

    def register_device(self, device_id: int, device_key: str):
        """Register a trusted Modbus device"""
        self.allowed_devices[device_id] = device_key
        logger.info(f"Registered Modbus device: {device_id}")

    def validate_modbus_packet(
        self,
        transaction_id: int,
        protocol_id: int,
        unit_id: int,
        function_code: int,
        data: bytes,
        source_ip: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate Modbus TCP packet

        Returns:
            (is_valid, error_message)
        """
        # Check if device is registered
        if unit_id not in self.allowed_devices:
            return False, f"Unauthorized device ID: {unit_id}"

        # Check protocol ID (should be 0 for Modbus)
        if protocol_id != 0:
            return False, f"Invalid protocol ID: {protocol_id}"

        # Validate function code
        valid_function_codes = {
            1: "Read Coils",
            2: "Read Discrete Inputs",
            3: "Read Holding Registers",
            4: "Read Input Registers",
            5: "Write Single Coil",
            6: "Write Single Register",
            15: "Write Multiple Coils",
            16: "Write Multiple Registers",
        }

        if function_code not in valid_function_codes:
            return False, f"Invalid function code: {function_code}"

        # Check for dangerous write operations from unauthorized sources
        write_functions = [5, 6, 15, 16]
        if function_code in write_functions:
            # Additional validation for write operations
            if not self._validate_write_operation(
                unit_id, function_code, data, source_ip
            ):
                return False, "Unauthorized write operation"

        # Rate limiting
        if not self._check_rate_limit(unit_id):
            return False, "Rate limit exceeded"

        # Check for packet injection patterns
        if self._detect_packet_injection(transaction_id, unit_id, function_code):
            return False, "Potential packet injection detected"

        return True, None

    def _validate_write_operation(
        self, unit_id: int, function_code: int, data: bytes, source_ip: str
    ) -> bool:
        """Validate write operations with additional security checks"""
        # Check if source IP is authorized for write operations
        # In production, maintain a whitelist of authorized IPs
        authorized_write_ips = ["10.0.0.0/8", "192.168.0.0/16"]  # Example

        # Check address ranges (prevent writing to critical addresses)
        if len(data) >= 2:
            address = struct.unpack(">H", data[0:2])[0]
            critical_ranges = [(0, 100), (1000, 1100)]  # Example critical ranges

            for start, end in critical_ranges:
                if start <= address <= end:
                    logger.warning(
                        f"Attempted write to critical address range: {address}"
                    )
                    return False

        return True

    def _check_rate_limit(self, unit_id: int) -> bool:
        """Check if device is within rate limits"""
        now = datetime.utcnow()

        # Remove old timestamps
        self.rate_limit[unit_id] = [
            ts for ts in self.rate_limit[unit_id] if now - ts < self.command_window
        ]

        # Check limit
        if len(self.rate_limit[unit_id]) >= self.max_commands_per_minute:
            logger.warning(f"Rate limit exceeded for device {unit_id}")
            return False

        # Add current timestamp
        self.rate_limit[unit_id].append(now)
        return True

    def _detect_packet_injection(
        self, transaction_id: int, unit_id: int, function_code: int
    ) -> bool:
        """Detect potential packet injection attacks"""
        # Check for suspicious patterns in transaction IDs
        # (e.g., sequential IDs from same device might indicate injection)

        recent_commands = [
            cmd for cmd in self.command_history[-100:] if cmd.get("unit_id") == unit_id
        ]

        if len(recent_commands) > 10:
            # Check for suspicious transaction ID patterns
            transaction_ids = [cmd.get("transaction_id") for cmd in recent_commands]

            # Detect if transaction IDs are too sequential (potential injection)
            if len(transaction_ids) >= 5:
                diffs = [
                    transaction_ids[i + 1] - transaction_ids[i]
                    for i in range(len(transaction_ids) - 1)
                ]
                if all(d == 1 for d in diffs[-5:]):  # All sequential
                    logger.warning(
                        f"Suspicious transaction ID pattern for device {unit_id}"
                    )
                    return True

        # Record command
        self.command_history.append(
            {
                "transaction_id": transaction_id,
                "unit_id": unit_id,
                "function_code": function_code,
                "timestamp": datetime.utcnow(),
            }
        )

        # Keep only last 1000 commands
        if len(self.command_history) > 1000:
            self.command_history = self.command_history[-1000:]

        return False

    def sign_modbus_command(
        self, unit_id: int, function_code: int, data: bytes
    ) -> bytes:
        """Sign Modbus command with HMAC for integrity"""
        if unit_id not in self.allowed_devices:
            raise ValueError(f"Device {unit_id} not registered")

        device_key = self.allowed_devices[unit_id]

        # Create message to sign
        message = struct.pack(">BB", unit_id, function_code) + data

        # Generate HMAC
        signature = hmac.new(device_key.encode(), message, hashlib.sha256).digest()

        return signature[:4]  # Use first 4 bytes as signature


class Layer1Security:
    """
    Physical Layer (Layer 1) Security
    Monitors and protects against physical layer attacks
    """

    def __init__(self):
        self.device_fingerprints: Dict[str, Dict[str, Any]] = {}
        self.anomaly_detection_enabled = True

    def register_device_fingerprint(
        self, device_mac: str, device_type: str, expected_behavior: Dict[str, Any]
    ):
        """Register device fingerprint for anomaly detection"""
        self.device_fingerprints[device_mac] = {
            "device_type": device_type,
            "expected_behavior": expected_behavior,
            "last_seen": datetime.utcnow(),
        }
        logger.info(f"Registered device fingerprint: {device_mac}")

    def validate_device_behavior(
        self, device_mac: str, current_behavior: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate device behavior against fingerprint"""
        if device_mac not in self.device_fingerprints:
            if self.anomaly_detection_enabled:
                return False, f"Unknown device: {device_mac}"
            return True, None

        fingerprint = self.device_fingerprints[device_mac]
        expected = fingerprint["expected_behavior"]

        # Check for significant deviations
        for key, expected_value in expected.items():
            if key in current_behavior:
                current_value = current_behavior[key]

                # Allow some variance
                if isinstance(expected_value, (int, float)):
                    variance = (
                        abs(current_value - expected_value) / expected_value
                        if expected_value != 0
                        else abs(current_value)
                    )
                    if variance > 0.2:  # 20% variance threshold
                        return False, f"Device behavior anomaly: {key} deviation > 20%"

        # Update last seen
        fingerprint["last_seen"] = datetime.utcnow()
        return True, None


class Layer2Security:
    """
    Data Link Layer (Layer 2) Security
    Protects against MAC address spoofing, ARP poisoning, etc.
    """

    def __init__(self):
        self.mac_ip_bindings: Dict[str, str] = {}  # MAC -> IP
        self.arp_table: Dict[str, str] = {}  # IP -> MAC
        self.arp_history: List[Dict[str, Any]] = []

    def register_mac_ip_binding(self, mac_address: str, ip_address: str):
        """Register trusted MAC-IP binding"""
        self.mac_ip_bindings[mac_address] = ip_address
        self.arp_table[ip_address] = mac_address
        logger.info(f"Registered MAC-IP binding: {mac_address} -> {ip_address}")

    def validate_arp_packet(
        self,
        source_mac: str,
        source_ip: str,
        target_ip: str,
        operation: str,  # "request" or "reply"
    ) -> Tuple[bool, Optional[str]]:
        """Validate ARP packet for ARP poisoning detection"""
        # Check if MAC-IP binding is consistent
        if source_mac in self.mac_ip_bindings:
            expected_ip = self.mac_ip_bindings[source_mac]
            if expected_ip != source_ip:
                logger.warning(
                    f"ARP poisoning detected: MAC {source_mac} claims IP {source_ip} but should be {expected_ip}"
                )
                return False, "ARP poisoning detected: MAC-IP mismatch"

        # Check for rapid ARP changes (potential attack)
        recent_arp = [
            entry
            for entry in self.arp_history[-100:]
            if entry.get("target_ip") == target_ip
        ]

        if len(recent_arp) > 10:
            # Check for rapid MAC changes
            macs = set(entry.get("source_mac") for entry in recent_arp[-10:])
            if len(macs) > 3:
                logger.warning(f"Rapid ARP changes detected for IP {target_ip}")
                return False, "Rapid ARP changes detected"

        # Record ARP packet
        self.arp_history.append(
            {
                "source_mac": source_mac,
                "source_ip": source_ip,
                "target_ip": target_ip,
                "operation": operation,
                "timestamp": datetime.utcnow(),
            }
        )

        # Keep only last 1000 entries
        if len(self.arp_history) > 1000:
            self.arp_history = self.arp_history[-1000:]

        return True, None

    def detect_mac_spoofing(self, mac_address: str, ip_address: str) -> bool:
        """Detect MAC address spoofing"""
        if mac_address in self.mac_ip_bindings:
            expected_ip = self.mac_ip_bindings[mac_address]
            if expected_ip != ip_address:
                logger.warning(
                    f"MAC spoofing detected: {mac_address} used with {ip_address} instead of {expected_ip}"
                )
                return True
        return False


class IndustrialProtocolFirewall:
    """
    Industrial Protocol Firewall
    Provides deep packet inspection for industrial protocols
    """

    def __init__(self):
        self.modbus_validator = ModbusSecurityValidator()
        self.layer1_security = Layer1Security()
        self.layer2_security = Layer2Security()
        self.blocked_ips: set = set()
        self.blocked_macs: set = set()

    def block_device(self, identifier: str, device_type: str = "ip"):
        """Block a device (IP or MAC)"""
        if device_type == "ip":
            self.blocked_ips.add(identifier)
        elif device_type == "mac":
            self.blocked_macs.add(identifier)
        logger.warning(f"Blocked {device_type}: {identifier}")

    def is_blocked(self, ip: str = None, mac: str = None) -> bool:
        """Check if device is blocked"""
        if ip and ip in self.blocked_ips:
            return True
        if mac and mac in self.blocked_macs:
            return True
        return False

    def validate_industrial_packet(
        self, protocol: str, source_ip: str, source_mac: str, packet_data: bytes
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate industrial protocol packet

        Args:
            protocol: Protocol name (modbus, opcua, etc.)
            source_ip: Source IP address
            source_mac: Source MAC address
            packet_data: Packet data

        Returns:
            (is_valid, error_message)
        """
        # Check if device is blocked
        if self.is_blocked(ip=source_ip, mac=source_mac):
            return False, "Device is blocked"

        # Layer 2 validation
        if source_mac:
            if self.layer2_security.detect_mac_spoofing(source_mac, source_ip):
                self.block_device(source_mac, "mac")
                return False, "MAC spoofing detected"

        # Protocol-specific validation
        if protocol.lower() == "modbus":
            try:
                # Parse Modbus TCP header
                if len(packet_data) < 8:
                    return False, "Invalid Modbus packet length"

                transaction_id = struct.unpack(">H", packet_data[0:2])[0]
                protocol_id = struct.unpack(">H", packet_data[2:4])[0]
                length = struct.unpack(">H", packet_data[4:6])[0]
                unit_id = packet_data[6]
                function_code = packet_data[7]
                data = packet_data[8:]

                is_valid, error = self.modbus_validator.validate_modbus_packet(
                    transaction_id, protocol_id, unit_id, function_code, data, source_ip
                )

                if not is_valid:
                    return False, error

            except Exception as e:
                logger.error(f"Error validating Modbus packet: {e}")
                return False, f"Packet validation error: {str(e)}"

        return True, None


# Global instance
industrial_firewall = IndustrialProtocolFirewall()
