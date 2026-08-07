"""
Kafka producer and consumer utilities
"""
from typing import Dict, Any, Optional, Callable
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import (
    SerializationContext,
    MessageField,
    StringSerializer,
)
import json
import logging

from .config import settings

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:
    """Kafka producer wrapper with error handling"""

    def __init__(
        self, topic: str, schema: Optional[str] = None, low_latency: bool = False
    ):
        self.topic = topic
        self.low_latency = low_latency or settings.KAFKA_LOW_LATENCY_MODE

        # Producer config - optimized based on latency requirements
        if self.low_latency:
            # Low-latency configuration for critical controls
            conf = {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "client.id": f"{settings.APP_NAME}-producer-lowlatency",
                "acks": settings.KAFKA_PRODUCER_ACKS
                if settings.KAFKA_PRODUCER_ACKS in ["0", "1", "all"]
                else "1",
                "retries": 1,  # Reduced retries for lower latency
                "max.in.flight.requests.per.connection": 5,  # Higher for throughput
                "linger.ms": settings.KAFKA_PRODUCER_LINGER_MS,  # 0 for immediate send
                "batch.size": settings.KAFKA_PRODUCER_BATCH_SIZE,  # Small batch for low latency
                "compression.type": settings.KAFKA_PRODUCER_COMPRESSION_TYPE,  # 'none' for lowest latency
                "request.timeout.ms": 5000,  # Lower timeout
                "delivery.timeout.ms": 10000,  # Lower delivery timeout
            }
        else:
            # Standard configuration for reliability
            conf = {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "client.id": f"{settings.APP_NAME}-producer",
                "acks": settings.KAFKA_PRODUCER_ACKS
                if settings.KAFKA_PRODUCER_ACKS in ["0", "1", "all"]
                else "all",
                "retries": 3,
                "max.in.flight.requests.per.connection": 1,  # For exactly-once semantics
                "linger.ms": settings.KAFKA_PRODUCER_LINGER_MS,
                "batch.size": settings.KAFKA_PRODUCER_BATCH_SIZE,
                "compression.type": settings.KAFKA_PRODUCER_COMPRESSION_TYPE,
            }

        self.producer = Producer(conf)

        # Schema registry (if schema provided)
        if schema:
            schema_registry_conf = {"url": settings.KAFKA_SCHEMA_REGISTRY_URL}
            schema_registry_client = SchemaRegistryClient(schema_registry_conf)
            self.serializer = AvroSerializer(
                schema_registry_client, schema, lambda obj, ctx: obj
            )
        else:
            self.serializer = None

    def delivery_callback(self, err, msg):
        """Callback for delivery reports"""
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(
                f"Message delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}"
            )

    def send(self, key: str, value: Dict[str, Any], flush_immediately: bool = None):
        """
        Send message to Kafka

        Args:
            key: Message key
            value: Message value
            flush_immediately: If True, flush immediately (for critical controls).
                              If None, uses low_latency setting
        """
        try:
            if self.serializer:
                serialized_value = self.serializer(
                    value, SerializationContext(self.topic, MessageField.VALUE)
                )
            else:
                serialized_value = json.dumps(value).encode("utf-8")

            self.producer.produce(
                topic=self.topic,
                key=key.encode("utf-8"),
                value=serialized_value,
                callback=self.delivery_callback,
            )
            self.producer.poll(0)

            # For low-latency mode, optionally flush immediately
            if flush_immediately is None:
                flush_immediately = self.low_latency

            if flush_immediately:
                self.producer.poll(0)  # Trigger delivery callbacks
                # Note: We don't call flush() here to avoid blocking
                # The producer will send immediately due to linger.ms=0

        except Exception as e:
            logger.error(f"Error sending message to Kafka: {e}")
            raise

    def flush(self, timeout: float = 10):
        """
        Flush pending messages

        Note: For low-latency mode, avoid calling flush() in critical path
        as it blocks until all messages are delivered.
        """
        self.producer.flush(timeout)

    def close(self):
        """Close producer"""
        self.producer.flush()


class KafkaConsumerWrapper:
    """Kafka consumer wrapper with error handling"""

    def __init__(
        self,
        topics: list,
        group_id: str,
        schema: Optional[str] = None,
        auto_offset_reset: str = "earliest",
        low_latency: bool = False,
    ):
        self.topics = topics
        self.low_latency = low_latency or settings.KAFKA_LOW_LATENCY_MODE

        # Consumer config - optimized for latency
        if self.low_latency:
            # Low-latency configuration
            conf = {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": True,  # Auto-commit for lower latency
                "auto.commit.interval.ms": 100,  # Commit frequently
                "fetch.min.bytes": settings.KAFKA_CONSUMER_FETCH_MIN_BYTES,  # 1 byte for immediate fetch
                "fetch.max.wait.ms": settings.KAFKA_CONSUMER_FETCH_MAX_WAIT_MS,  # 0 for no wait
                "max.partition.fetch.bytes": 1048576,  # 1MB - smaller for lower latency
                "session.timeout.ms": 10000,  # Lower session timeout
                "heartbeat.interval.ms": 3000,  # More frequent heartbeats
            }
        else:
            # Standard configuration
            conf = {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": False,  # Manual commit for reliability
                "fetch.min.bytes": settings.KAFKA_CONSUMER_FETCH_MIN_BYTES,
                "fetch.max.wait.ms": settings.KAFKA_CONSUMER_FETCH_MAX_WAIT_MS,
            }

        self.consumer = Consumer(conf)
        self.consumer.subscribe(topics)

        # Schema registry (if schema provided)
        if schema:
            schema_registry_conf = {"url": settings.KAFKA_SCHEMA_REGISTRY_URL}
            schema_registry_client = SchemaRegistryClient(schema_registry_conf)
            self.deserializer = AvroDeserializer(
                schema_registry_client, schema, lambda obj, ctx: obj
            )
        else:
            self.deserializer = None

    def consume_messages(
        self, callback: Callable[[str, Dict[str, Any]], None], timeout: float = None
    ):
        """
        Consume messages with callback

        Args:
            callback: Function to process messages
            timeout: Poll timeout in seconds. If None, uses 0 for low-latency mode
        """
        if timeout is None:
            timeout = 0.0 if self.low_latency else 1.0

        try:
            while True:
                msg = self.consumer.poll(timeout)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug(f"Reached end of partition {msg.partition()}")
                    else:
                        raise KafkaException(msg.error())
                else:
                    # Deserialize message
                    key = msg.key().decode("utf-8") if msg.key() else None

                    if self.deserializer:
                        value = self.deserializer(
                            msg.value(),
                            SerializationContext(msg.topic(), MessageField.VALUE),
                        )
                    else:
                        value = json.loads(msg.value().decode("utf-8"))

                    # Process message
                    try:
                        callback(key, value)
                        # Only manual commit if auto-commit is disabled
                        if not self.low_latency:
                            self.consumer.commit(message=msg)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        # Send to DLQ
                        self.send_to_dlq(msg, str(e))

        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
        finally:
            self.close()

    def send_to_dlq(self, msg, error: str):
        """Send failed message to Dead Letter Queue"""
        dlq_topic = f"{msg.topic()}.dlq"
        dlq_producer = KafkaProducerWrapper(dlq_topic)

        try:
            dlq_message = {
                "original_topic": msg.topic(),
                "original_partition": msg.partition(),
                "original_offset": msg.offset(),
                "error": error,
                "value": msg.value().decode("utf-8") if msg.value() else None,
            }
            dlq_producer.send(
                msg.key().decode("utf-8") if msg.key() else "null", dlq_message
            )
            dlq_producer.flush()
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")

    def close(self):
        """Close consumer"""
        self.consumer.close()


# Kafka topics
KAFKA_TOPICS = {
    "RAW_SENSOR_DATA": "raw-sensor-data",
    "PROCESSED_DATA": "processed-data",
    "ALERTS": "alerts",
    "CONTROL_COMMANDS": "control-commands",
    "CRITICAL_CONTROL_COMMANDS": "critical-control-commands",  # Low-latency topic
    "ML_PREDICTIONS": "ml-predictions",
    "DLQ": "dlq",
}


# Convenience function for low-latency producer
def create_low_latency_producer(
    topic: str, schema: Optional[str] = None
) -> KafkaProducerWrapper:
    """Create a low-latency Kafka producer for critical controls"""
    return KafkaProducerWrapper(topic=topic, schema=schema, low_latency=True)


# Convenience function for low-latency consumer
def create_low_latency_consumer(
    topics: list,
    group_id: str,
    schema: Optional[str] = None,
    auto_offset_reset: str = "latest",  # 'latest' for real-time processing
) -> KafkaConsumerWrapper:
    """Create a low-latency Kafka consumer for critical controls"""
    return KafkaConsumerWrapper(
        topics=topics,
        group_id=group_id,
        schema=schema,
        auto_offset_reset=auto_offset_reset,
        low_latency=True,
    )
