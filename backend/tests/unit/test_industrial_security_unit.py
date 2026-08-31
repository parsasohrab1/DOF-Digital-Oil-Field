"""
Tests for shared.industrial_security: the Modbus TCP / ARP / MAC layer
firewall that sits in front of SCADA-facing traffic. This module had zero
test coverage prior to this file despite being the primary defense against
packet injection, unauthorized writes to critical registers, ARP poisoning
and MAC spoofing on the OT network.
"""

import struct

import pytest

from shared.industrial_security import (
    IndustrialProtocolFirewall,
    Layer1Security,
    Layer2Security,
    ModbusSecurityValidator,
)


class TestModbusSecurityValidator:
    @pytest.fixture
    def validator(self):
        v = ModbusSecurityValidator()
        v.register_device(1, "device-1-secret")
        return v

    def test_rejects_unregistered_device(self, validator):
        ok, err = validator.validate_modbus_packet(1, 0, 99, 3, b"", "10.0.0.5")
        assert ok is False
        assert "Unauthorized device" in err

    def test_rejects_non_zero_protocol_id(self, validator):
        ok, err = validator.validate_modbus_packet(1, 7, 1, 3, b"", "10.0.0.5")
        assert ok is False
        assert "protocol ID" in err

    def test_rejects_unknown_function_code(self, validator):
        ok, err = validator.validate_modbus_packet(1, 0, 1, 99, b"", "10.0.0.5")
        assert ok is False
        assert "function code" in err

    def test_accepts_valid_read_request(self, validator):
        ok, err = validator.validate_modbus_packet(1, 0, 1, 3, b"\x00\x00", "10.0.0.5")
        assert ok is True
        assert err is None

    def test_blocks_write_to_critical_address_range(self, validator):
        # write-single-register (function 6) targeting address 50, inside
        # the (0, 100) critical range
        data = struct.pack(">H", 50) + struct.pack(">H", 1234)
        ok, err = validator.validate_modbus_packet(1, 0, 1, 6, data, "10.0.0.5")
        assert ok is False
        assert "Unauthorized write" in err

    def test_allows_write_outside_critical_address_range(self, validator):
        data = struct.pack(">H", 500) + struct.pack(">H", 1234)
        ok, err = validator.validate_modbus_packet(1, 0, 1, 6, data, "10.0.0.5")
        assert ok is True

    def test_rate_limit_blocks_after_threshold(self, validator):
        validator.max_commands_per_minute = 3
        for i in range(3):
            ok, _ = validator.validate_modbus_packet(
                i, 0, 1, 3, b"\x00\x00", "10.0.0.5"
            )
            assert ok is True
        ok, err = validator.validate_modbus_packet(99, 0, 1, 3, b"\x00\x00", "10.0.0.5")
        assert ok is False
        assert "Rate limit" in err

    def test_detects_sequential_transaction_id_injection_pattern(self, validator):
        validator.max_commands_per_minute = 1000
        # Seed >10 recorded commands with strictly sequential transaction IDs
        # for this unit_id, which is the injection heuristic under test.
        for tid in range(1, 17):
            validator.command_history.append(
                {"transaction_id": tid, "unit_id": 1, "function_code": 3}
            )
        ok, err = validator.validate_modbus_packet(17, 0, 1, 3, b"\x00\x00", "10.0.0.5")
        assert ok is False
        assert "injection" in err

    def test_sign_modbus_command_rejects_unregistered_device(self, validator):
        with pytest.raises(ValueError):
            validator.sign_modbus_command(42, 3, b"\x00\x00")

    def test_sign_modbus_command_is_deterministic_and_device_specific(self, validator):
        validator.register_device(2, "device-2-secret")
        sig_a = validator.sign_modbus_command(1, 6, b"\x00\x32\x04\xd2")
        sig_a_again = validator.sign_modbus_command(1, 6, b"\x00\x32\x04\xd2")
        sig_b = validator.sign_modbus_command(2, 6, b"\x00\x32\x04\xd2")

        assert sig_a == sig_a_again
        assert sig_a != sig_b
        assert len(sig_a) == 4


class TestLayer1Security:
    def test_unknown_device_rejected_when_anomaly_detection_enabled(self):
        layer1 = Layer1Security()
        ok, err = layer1.validate_device_behavior("AA:BB:CC:DD:EE:FF", {"temp": 50})
        assert ok is False
        assert "Unknown device" in err

    def test_unknown_device_allowed_when_anomaly_detection_disabled(self):
        layer1 = Layer1Security()
        layer1.anomaly_detection_enabled = False
        ok, err = layer1.validate_device_behavior("AA:BB:CC:DD:EE:FF", {"temp": 50})
        assert ok is True

    def test_behavior_within_variance_is_accepted(self):
        layer1 = Layer1Security()
        layer1.register_device_fingerprint("AA:BB:CC:DD:EE:FF", "sensor", {"temp": 50})
        ok, err = layer1.validate_device_behavior("AA:BB:CC:DD:EE:FF", {"temp": 55})
        assert ok is True

    def test_behavior_exceeding_variance_threshold_is_flagged(self):
        layer1 = Layer1Security()
        layer1.register_device_fingerprint("AA:BB:CC:DD:EE:FF", "sensor", {"temp": 50})
        ok, err = layer1.validate_device_behavior("AA:BB:CC:DD:EE:FF", {"temp": 100})
        assert ok is False
        assert "anomaly" in err


class TestLayer2Security:
    def test_valid_arp_packet_from_known_binding_is_accepted(self):
        layer2 = Layer2Security()
        layer2.register_mac_ip_binding("AA:BB:CC:DD:EE:FF", "10.0.0.5")
        ok, err = layer2.validate_arp_packet(
            "AA:BB:CC:DD:EE:FF", "10.0.0.5", "10.0.0.1", "request"
        )
        assert ok is True

    def test_arp_poisoning_detected_on_mac_ip_mismatch(self):
        layer2 = Layer2Security()
        layer2.register_mac_ip_binding("AA:BB:CC:DD:EE:FF", "10.0.0.5")
        ok, err = layer2.validate_arp_packet(
            "AA:BB:CC:DD:EE:FF", "10.0.0.99", "10.0.0.1", "reply"
        )
        assert ok is False
        assert "poisoning" in err

    def test_rapid_mac_changes_for_same_target_ip_flagged(self):
        layer2 = Layer2Security()
        for i in range(11):
            mac = f"AA:BB:CC:DD:EE:{i:02X}"
            layer2.validate_arp_packet(mac, f"10.0.0.{i}", "10.0.0.1", "reply")
        # by now >3 distinct MACs claimed to be at target_ip 10.0.0.1 recently
        ok, err = layer2.validate_arp_packet(
            "AA:BB:CC:DD:EE:FF", "10.0.0.50", "10.0.0.1", "reply"
        )
        assert ok is False
        assert "Rapid ARP" in err

    def test_detect_mac_spoofing_true_on_mismatch(self):
        layer2 = Layer2Security()
        layer2.register_mac_ip_binding("AA:BB:CC:DD:EE:FF", "10.0.0.5")
        assert layer2.detect_mac_spoofing("AA:BB:CC:DD:EE:FF", "10.0.0.99") is True

    def test_detect_mac_spoofing_false_for_consistent_binding(self):
        layer2 = Layer2Security()
        layer2.register_mac_ip_binding("AA:BB:CC:DD:EE:FF", "10.0.0.5")
        assert layer2.detect_mac_spoofing("AA:BB:CC:DD:EE:FF", "10.0.0.5") is False


class TestIndustrialProtocolFirewall:
    @pytest.fixture
    def firewall(self):
        fw = IndustrialProtocolFirewall()
        fw.modbus_validator.register_device(1, "secret")
        return fw

    def _modbus_packet(
        self,
        transaction_id=1,
        protocol_id=0,
        unit_id=1,
        function_code=3,
        data=b"\x00\x00",
    ):
        return (
            struct.pack(">H", transaction_id)
            + struct.pack(">H", protocol_id)
            + b"\x00\x00"  # length field (unused by the validator)
            + bytes([unit_id, function_code])
            + data
        )

    def test_blocked_ip_is_rejected_before_protocol_parsing(self, firewall):
        firewall.block_device("10.0.0.66", "ip")
        ok, err = firewall.validate_industrial_packet(
            "modbus", "10.0.0.66", None, self._modbus_packet()
        )
        assert ok is False
        assert "blocked" in err.lower()

    def test_mac_spoofing_blocks_and_registers_device(self, firewall):
        firewall.layer2_security.register_mac_ip_binding(
            "AA:BB:CC:DD:EE:FF", "10.0.0.5"
        )
        ok, err = firewall.validate_industrial_packet(
            "modbus", "10.0.0.99", "AA:BB:CC:DD:EE:FF", self._modbus_packet()
        )
        assert ok is False
        assert "spoofing" in err.lower()
        assert firewall.is_blocked(mac="AA:BB:CC:DD:EE:FF") is True

    def test_valid_modbus_packet_passes_through(self, firewall):
        ok, err = firewall.validate_industrial_packet(
            "modbus", "10.0.0.5", None, self._modbus_packet()
        )
        assert ok is True
        assert err is None

    def test_undersized_modbus_packet_rejected(self, firewall):
        ok, err = firewall.validate_industrial_packet(
            "modbus", "10.0.0.5", None, b"\x00\x01\x00\x00"
        )
        assert ok is False
        assert "Invalid Modbus packet length" in err

    def test_modbus_write_to_critical_register_blocked_end_to_end(self, firewall):
        data = struct.pack(">H", 10) + struct.pack(">H", 9999)
        packet = self._modbus_packet(function_code=6, data=data)
        ok, err = firewall.validate_industrial_packet(
            "modbus", "10.0.0.5", None, packet
        )
        assert ok is False

    def test_unknown_protocol_name_is_not_rejected_by_default(self, firewall):
        # Only modbus gets deep packet inspection today; anything else
        # currently passes the firewall's protocol-specific stage untouched.
        # This test pins that behavior so a future protocol addition is a
        # deliberate change, not a silent gap.
        ok, err = firewall.validate_industrial_packet(
            "opcua", "10.0.0.5", None, b"\x00\x01\x02\x03"
        )
        assert ok is True
