"""
MQTT Client for Wireless Sensor Integration
پشتیبانی از MQTT برای سنسورهای بی‌سیم
"""
import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

try:
    import paho.mqtt.client as mqtt

    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("paho-mqtt not available. MQTT support disabled.")

logger = logging.getLogger(__name__)


class MQTTClient:
    """
    MQTT Client for receiving sensor data from wireless sensors
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        keepalive: int = 60,
        qos: int = 1,
    ):
        if not MQTT_AVAILABLE:
            raise RuntimeError(
                "paho-mqtt is required for MQTT support. Install with: pip install paho-mqtt"
            )

        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id or f"ogim-mqtt-{int(time.time())}"
        self.username = username
        self.password = password
        self.keepalive = keepalive
        self.qos = qos

        self.client = mqtt.Client(client_id=self.client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        self.is_connected = False
        self.subscribed_topics: List[str] = []
        self.message_callbacks: Dict[str, List[Callable]] = {}
        self.loop_thread = None
        self.running = False

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to broker"""
        if rc == 0:
            self.is_connected = True
            logger.info(
                f"MQTT client connected to {self.broker_host}:{self.broker_port}"
            )

            # Resubscribe to all topics
            for topic in self.subscribed_topics:
                client.subscribe(topic, qos=self.qos)
        else:
            logger.error(f"MQTT connection failed with code {rc}")
            self.is_connected = False

    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from broker"""
        self.is_connected = False
        logger.warning(f"MQTT client disconnected (rc={rc})")

    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")

            # Parse JSON payload
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {"raw": payload}

            # Call registered callbacks
            if topic in self.message_callbacks:
                for callback in self.message_callbacks[topic]:
                    try:
                        callback(topic, data, msg)
                    except Exception as e:
                        logger.error(f"Error in MQTT callback for topic {topic}: {e}")

            # Also call wildcard callbacks
            for pattern, callbacks in self.message_callbacks.items():
                if pattern.endswith("/#") and topic.startswith(pattern[:-2]):
                    for callback in callbacks:
                        try:
                            callback(topic, data, msg)
                        except Exception as e:
                            logger.error(f"Error in MQTT wildcard callback: {e}")

        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """Callback when subscription confirmed"""
        logger.debug(f"MQTT subscription confirmed: mid={mid}, qos={granted_qos}")

    def connect(self) -> bool:
        """Connect to MQTT broker"""
        try:
            self.client.connect(self.broker_host, self.broker_port, self.keepalive)
            self.client.loop_start()
            self.running = True

            # Wait for connection
            timeout = 5
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            if self.is_connected:
                logger.info("MQTT client connected successfully")
                return True
            else:
                logger.error("MQTT connection timeout")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.running:
            self.client.loop_stop()
            self.client.disconnect()
            self.running = False
            self.is_connected = False
            logger.info("MQTT client disconnected")

    def subscribe(
        self, topic: str, callback: Optional[Callable] = None, qos: Optional[int] = None
    ):
        """
        Subscribe to MQTT topic

        Args:
            topic: MQTT topic (supports wildcards: +, #)
            callback: Optional callback function(topic, data, msg)
            qos: Quality of Service level (0, 1, or 2)
        """
        qos_level = qos if qos is not None else self.qos

        if topic not in self.subscribed_topics:
            self.subscribed_topics.append(topic)
            if self.is_connected:
                self.client.subscribe(topic, qos=qos_level)
            logger.info(f"Subscribed to MQTT topic: {topic} (QoS: {qos_level})")

        if callback:
            if topic not in self.message_callbacks:
                self.message_callbacks[topic] = []
            self.message_callbacks[topic].append(callback)

    def unsubscribe(self, topic: str):
        """Unsubscribe from MQTT topic"""
        if topic in self.subscribed_topics:
            self.subscribed_topics.remove(topic)
            if self.is_connected:
                self.client.unsubscribe(topic)
            logger.info(f"Unsubscribed from MQTT topic: {topic}")

        if topic in self.message_callbacks:
            del self.message_callbacks[topic]

    def publish(
        self, topic: str, payload: Any, qos: Optional[int] = None, retain: bool = False
    ) -> bool:
        """
        Publish message to MQTT topic

        Args:
            topic: MQTT topic
            payload: Message payload (dict, list, or string)
            qos: Quality of Service level
            retain: Retain message flag
        """
        if not self.is_connected:
            logger.warning("MQTT client not connected, cannot publish")
            return False

        try:
            # Convert payload to JSON if dict/list
            if isinstance(payload, (dict, list)):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)

            qos_level = qos if qos is not None else self.qos
            result = self.client.publish(
                topic, payload_str, qos=qos_level, retain=retain
            )

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Published to MQTT topic {topic}: {payload_str[:100]}")
                return True
            else:
                logger.error(f"Failed to publish to MQTT topic {topic}: {result.rc}")
                return False
        except Exception as e:
            logger.error(f"Error publishing to MQTT topic {topic}: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get MQTT client status"""
        return {
            "is_connected": self.is_connected,
            "broker_host": self.broker_host,
            "broker_port": self.broker_port,
            "client_id": self.client_id,
            "subscribed_topics": self.subscribed_topics,
            "subscribed_count": len(self.subscribed_topics),
        }


class MQTTMessageHandler:
    """
    Handler for processing MQTT messages from wireless sensors
    """

    def __init__(self, mqtt_client: MQTTClient):
        self.mqtt_client = mqtt_client
        self.message_count = 0
        self.error_count = 0
        self.last_message_time = None

    def handle_sensor_data(
        self, topic: str, data: Dict[str, Any], msg
    ) -> Optional[Dict[str, Any]]:
        """
        Handle sensor data from MQTT message

        Expected topic format: sensors/{sensor_id}/data
        Expected payload: {
            "sensor_id": "SENSOR-001",
            "value": 123.45,
            "timestamp": "2025-01-15T10:30:00Z",
            "unit": "bar",
            "sensor_type": "pressure"
        }
        """
        try:
            self.message_count += 1
            self.last_message_time = time.time()

            # Extract sensor ID from topic if not in payload
            if "sensor_id" not in data:
                # Try to extract from topic: sensors/{sensor_id}/data
                topic_parts = topic.split("/")
                if len(topic_parts) >= 2:
                    data["sensor_id"] = topic_parts[1]

            # Validate required fields
            if "value" not in data:
                logger.warning(f"Missing 'value' in MQTT message from topic {topic}")
                self.error_count += 1
                return None

            # Parse timestamp
            if "timestamp" in data:
                try:
                    if isinstance(data["timestamp"], str):
                        data["timestamp"] = datetime.fromisoformat(
                            data["timestamp"].replace("Z", "+00:00")
                        )
                    elif isinstance(data["timestamp"], (int, float)):
                        data["timestamp"] = datetime.fromtimestamp(data["timestamp"])
                except Exception as e:
                    logger.warning(
                        f"Failed to parse timestamp: {e}, using current time"
                    )
                    data["timestamp"] = datetime.utcnow()
            else:
                data["timestamp"] = datetime.utcnow()

            # Add metadata
            data["source"] = "mqtt"
            data["topic"] = topic
            data["qos"] = msg.qos

            logger.debug(
                f"Processed MQTT message from {topic}: sensor_id={data.get('sensor_id')}, value={data.get('value')}"
            )
            return data

        except Exception as e:
            logger.error(f"Error handling MQTT sensor data: {e}")
            self.error_count += 1
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get message handler statistics"""
        return {
            "message_count": self.message_count,
            "error_count": self.error_count,
            "last_message_time": self.last_message_time,
            "success_rate": (self.message_count - self.error_count) / self.message_count
            if self.message_count > 0
            else 0,
        }


# Global MQTT client instance
_global_mqtt_client: Optional[MQTTClient] = None


def get_mqtt_client(**kwargs) -> MQTTClient:
    """Get or create global MQTT client"""
    global _global_mqtt_client
    if _global_mqtt_client is None:
        _global_mqtt_client = MQTTClient(**kwargs)
    return _global_mqtt_client
