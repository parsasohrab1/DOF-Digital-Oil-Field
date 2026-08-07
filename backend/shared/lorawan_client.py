"""
LoRaWAN Client for Low-Power Wireless Sensor Integration
پشتیبانی از LoRaWAN برای سنسورهای کم‌مصرف بی‌سیم
"""
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
import base64

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


class LoRaWANClient:
    """
    LoRaWAN Client for receiving data from LoRaWAN sensors
    Supports TTN (The Things Network) and ChirpStack
    """

    def __init__(
        self,
        network_type: str = "ttn",  # "ttn" or "chirpstack"
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        app_id: Optional[str] = None,
        device_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        self.network_type = network_type.lower()
        self.api_url = api_url
        self.api_key = api_key
        self.app_id = app_id
        self.device_id = device_id
        self.webhook_url = webhook_url

        # Default URLs based on network type
        if not self.api_url:
            if self.network_type == "ttn":
                self.api_url = "https://eu1.cloud.thethings.network/api/v3"
            elif self.network_type == "chirpstack":
                self.api_url = "http://localhost:8080/api"
            else:
                raise ValueError(f"Unknown network type: {network_type}")

        self.message_callbacks: List[Callable] = []
        self.message_count = 0
        self.error_count = 0

    def decode_payload(
        self, payload_base64: str, decoder: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Decode LoRaWAN payload

        Args:
            payload_base64: Base64 encoded payload
            decoder: Optional custom decoder function

        Returns:
            Decoded data dictionary
        """
        try:
            # Decode base64
            payload_bytes = base64.b64decode(payload_base64)

            if decoder:
                return decoder(payload_bytes)

            # Default decoder: try JSON first, then hex
            try:
                # Try as UTF-8 JSON
                payload_str = payload_bytes.decode("utf-8")
                return json.loads(payload_str)
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Try as hex string
                payload_hex = payload_bytes.hex()
                # Simple decoder: assume first 2 bytes are sensor type, next 4 bytes are value
                if len(payload_bytes) >= 6:
                    sensor_type = payload_bytes[0]
                    value_bytes = payload_bytes[2:6]
                    # Convert to float (assuming IEEE 754 format)
                    import struct

                    value = struct.unpack(">f", value_bytes)[0]
                    return {
                        "sensor_type": sensor_type,
                        "value": value,
                        "raw_hex": payload_hex,
                    }
                else:
                    return {"raw_hex": payload_hex}

        except Exception as e:
            logger.error(f"Failed to decode LoRaWAN payload: {e}")
            return {"error": str(e), "raw_base64": payload_base64}

    def handle_ttn_uplink(
        self, uplink_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Handle TTN (The Things Network) uplink message

        Expected format:
        {
            "end_device_ids": {
                "device_id": "sensor-001",
                "application_ids": {"application_id": "ogim-app"}
            },
            "received_at": "2025-01-15T10:30:00Z",
            "uplink_message": {
                "f_port": 1,
                "f_cnt": 123,
                "frm_payload": "base64_encoded_payload",
                "decoded_payload": {...},  # If decoder configured
                "rx_metadata": [...],
                "settings": {...}
            }
        }
        """
        try:
            self.message_count += 1

            end_device = uplink_data.get("end_device_ids", {})
            device_id = end_device.get("device_id")
            app_id = end_device.get("application_ids", {}).get("application_id")

            uplink_msg = uplink_data.get("uplink_message", {})
            f_port = uplink_msg.get("f_port", 1)
            f_cnt = uplink_msg.get("f_cnt", 0)

            # Get payload
            decoded_payload = uplink_msg.get("decoded_payload")
            if not decoded_payload:
                # Decode from frm_payload
                frm_payload = uplink_msg.get("frm_payload")
                if frm_payload:
                    decoded_payload = self.decode_payload(frm_payload)

            # Parse timestamp
            received_at = uplink_data.get("received_at")
            if received_at:
                try:
                    timestamp = datetime.fromisoformat(
                        received_at.replace("Z", "+00:00")
                    )
                except:
                    timestamp = datetime.utcnow()
            else:
                timestamp = datetime.utcnow()

            # Get RSSI and SNR from rx_metadata
            rx_metadata = uplink_msg.get("rx_metadata", [])
            rssi = None
            snr = None
            if rx_metadata:
                first_rx = rx_metadata[0]
                rssi = first_rx.get("rssi")
                snr = first_rx.get("snr")

            result = {
                "device_id": device_id,
                "app_id": app_id,
                "sensor_id": device_id,  # Use device_id as sensor_id
                "f_port": f_port,
                "f_cnt": f_cnt,
                "data": decoded_payload,
                "timestamp": timestamp,
                "rssi": rssi,
                "snr": snr,
                "source": "lorawan",
                "network_type": "ttn",
            }

            # Extract value if available
            if isinstance(decoded_payload, dict):
                if "value" in decoded_payload:
                    result["value"] = decoded_payload["value"]
                elif "temperature" in decoded_payload:
                    result["value"] = decoded_payload["temperature"]
                    result["sensor_type"] = "temperature"
                elif "pressure" in decoded_payload:
                    result["value"] = decoded_payload["pressure"]
                    result["sensor_type"] = "pressure"

            logger.debug(f"Processed LoRaWAN (TTN) message from device {device_id}")
            return result

        except Exception as e:
            logger.error(f"Error handling TTN uplink: {e}")
            self.error_count += 1
            return None

    def handle_chirpstack_uplink(
        self, uplink_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Handle ChirpStack uplink message

        Expected format:
        {
            "deviceInfo": {
                "devEui": "0102030405060708",
                "deviceName": "sensor-001"
            },
            "data": {
                "fPort": 1,
                "fCnt": 123,
                "data": "base64_encoded_payload"
            },
            "rxInfo": [...],
            "txInfo": {...}
        }
        """
        try:
            self.message_count += 1

            device_info = uplink_data.get("deviceInfo", {})
            device_id = device_info.get("deviceName") or device_info.get("devEui")
            dev_eui = device_info.get("devEui")

            data = uplink_data.get("data", {})
            f_port = data.get("fPort", 1)
            f_cnt = data.get("fCnt", 0)
            payload_base64 = data.get("data")

            # Decode payload
            decoded_payload = (
                self.decode_payload(payload_base64) if payload_base64 else {}
            )

            # Get RSSI and SNR from rxInfo
            rx_info = uplink_data.get("rxInfo", [])
            rssi = None
            snr = None
            if rx_info:
                first_rx = rx_info[0]
                rssi = first_rx.get("rssi")
                snr = first_rx.get("loRaSNR")

            result = {
                "device_id": device_id,
                "dev_eui": dev_eui,
                "sensor_id": device_id,
                "f_port": f_port,
                "f_cnt": f_cnt,
                "data": decoded_payload,
                "timestamp": datetime.utcnow(),
                "rssi": rssi,
                "snr": snr,
                "source": "lorawan",
                "network_type": "chirpstack",
            }

            # Extract value if available
            if isinstance(decoded_payload, dict):
                if "value" in decoded_payload:
                    result["value"] = decoded_payload["value"]

            logger.debug(
                f"Processed LoRaWAN (ChirpStack) message from device {device_id}"
            )
            return result

        except Exception as e:
            logger.error(f"Error handling ChirpStack uplink: {e}")
            self.error_count += 1
            return None

    def handle_uplink(self, uplink_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle uplink message based on network type"""
        if self.network_type == "ttn":
            return self.handle_ttn_uplink(uplink_data)
        elif self.network_type == "chirpstack":
            return self.handle_chirpstack_uplink(uplink_data)
        else:
            logger.error(f"Unknown network type: {self.network_type}")
            return None

    def add_message_callback(self, callback: Callable):
        """Add callback for processed messages"""
        self.message_callbacks.append(callback)

    def get_stats(self) -> Dict[str, Any]:
        """Get LoRaWAN client statistics"""
        return {
            "network_type": self.network_type,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "success_rate": (self.message_count - self.error_count) / self.message_count
            if self.message_count > 0
            else 0,
        }


# Global LoRaWAN client instance
_global_lorawan_client: Optional[LoRaWANClient] = None


def get_lorawan_client(**kwargs) -> LoRaWANClient:
    """Get or create global LoRaWAN client"""
    global _global_lorawan_client
    if _global_lorawan_client is None:
        _global_lorawan_client = LoRaWANClient(**kwargs)
    return _global_lorawan_client
