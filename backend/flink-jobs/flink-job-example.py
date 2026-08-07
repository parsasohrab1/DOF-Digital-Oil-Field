"""
Apache Flink Stream Processing Job Example
Processes sensor data streams for real-time analytics
"""
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import FlinkKafkaConsumer, FlinkKafkaProducer
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.datastream.functions import (
    MapFunction,
    FilterFunction,
    KeyedProcessFunction,
)
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common.time import Time
from datetime import datetime
import json
import sys
import os
import logging

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from config import settings

logger = logging.getLogger(__name__)


class SensorDataProcessor(MapFunction):
    """Process and enrich sensor data"""

    def map(self, value):
        try:
            data = json.loads(value)

            # Data cleansing
            if data.get("value") is None:
                return None

            # Data validation
            required_fields = ["timestamp", "sensor_id", "value", "sensor_type"]
            if not all(field in data for field in required_fields):
                return None

            # Data enrichment
            data["processed_timestamp"] = datetime.now().isoformat()
            data["data_quality"] = "good"

            # Add anomaly flag based on thresholds
            sensor_type = data.get("sensor_type", "")
            value = data.get("value", 0)

            thresholds = {
                "pressure": {"max": 500, "min": 0},
                "temperature": {"max": 150, "min": -40},
                "flow_rate": {"max": 1000, "min": 0},
                "vibration": {"max": 10, "min": 0},
            }

            if sensor_type in thresholds:
                thresh = thresholds[sensor_type]
                if (
                    value > thresh["max"] * 0.9
                    or value < thresh["min"] + thresh["max"] * 0.1
                ):
                    data["anomaly_flag"] = True
                    data["data_quality"] = "warning"
                elif value > thresh["max"] or value < thresh["min"]:
                    data["anomaly_flag"] = True
                    data["data_quality"] = "critical"
                else:
                    data["anomaly_flag"] = False

            return json.dumps(data)
        except Exception as e:
            print(f"Error processing record: {e}")
            return None


class AnomalyDetector(KeyedProcessFunction):
    """Complex Event Processing for anomaly detection"""

    def process_element(self, value, ctx):
        data = json.loads(value)

        # Generate alert if anomaly detected
        if data.get("anomaly_flag"):
            alert = {
                "alert_id": f"ALERT-{ctx.timestamp()}-{data['sensor_id']}",
                "timestamp": datetime.now().isoformat(),
                "severity": "critical"
                if data.get("data_quality") == "critical"
                else "warning",
                "status": "open",
                "well_name": data.get("well_name"),
                "sensor_id": data.get("sensor_id"),
                "message": f"{data['sensor_type']} anomaly detected: {data['value']} {data.get('unit')}",
                "rule_name": "flink_cep_anomaly",
            }
            yield json.dumps(alert)

        yield value


def create_flink_job(low_latency: bool = False):
    """
    Create and configure Flink streaming job

    Args:
        low_latency: If True, optimize for millisecond latency (for critical controls)
    """
    env = StreamExecutionEnvironment.get_execution_environment()

    if low_latency:
        # Low-latency configuration for critical controls
        # Disable checkpointing for lowest latency (trade-off: no exactly-once guarantee)
        # env.enable_checkpointing(1000)  # Very frequent checkpoints if needed
        # Or disable completely for absolute lowest latency:
        # Checkpointing disabled - use at-most-once semantics for critical controls

        # Set higher parallelism for better throughput
        env.set_parallelism(4)

        # Set buffer timeout to 0 for immediate processing
        env.set_buffer_timeout(0)  # Process immediately, no buffering

        # Use processing time instead of event time for lower latency
        # (Event time requires watermarks which add latency)

        logger.info(
            "Flink job configured for LOW-LATENCY mode (millisecond processing)"
        )
    else:
        # Standard configuration for reliability
        # Enable checkpointing for exactly-once semantics
        env.enable_checkpointing(60000)  # Checkpoint every 60 seconds
        env.get_checkpoint_config().set_checkpoint_timeout(120000)
        env.get_checkpoint_config().set_min_pause_between_checkpoints(30000)

        # Set parallelism
        env.set_parallelism(2)

        # Standard buffer timeout
        env.set_buffer_timeout(100)  # 100ms buffer timeout

    # Kafka consumer properties - optimized for latency
    kafka_props = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": "flink-sensor-processor" + ("-lowlatency" if low_latency else ""),
        "auto.offset.reset": "latest"
        if low_latency
        else "earliest",  # Latest for real-time
    }

    # Add low-latency consumer settings
    if low_latency:
        kafka_props.update(
            {
                "fetch.min.bytes": "1",  # Minimum bytes to fetch
                "fetch.max.wait.ms": "0",  # No wait for immediate fetch
                "max.partition.fetch.bytes": "1048576",  # 1MB - smaller for lower latency
            }
        )

    # Kafka consumer for raw sensor data
    kafka_consumer = FlinkKafkaConsumer(
        topics=["raw-sensor-data"],
        deserialization_schema=SimpleStringSchema(),
        properties=kafka_props,
    )

    # Read from Kafka with watermarks for event time processing
    stream = env.add_source(kafka_consumer)

    # Process data: cleanse, validate, enrich
    processed_stream = stream.map(SensorDataProcessor()).filter(lambda x: x is not None)

    # Kafka producer configuration - optimized for latency
    producer_base_config = {"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS}

    if low_latency:
        # Low-latency producer settings
        producer_base_config.update(
            {
                "acks": "1",  # Leader acknowledgment only (faster than "all")
                "linger.ms": "0",  # No batching delay
                "batch.size": "1",  # Small batch size
                "compression.type": "none",  # No compression for lower latency
                "request.timeout.ms": "5000",  # Lower timeout
            }
        )

    # Kafka producer for processed data
    processed_producer = FlinkKafkaProducer(
        topic="processed-data",
        serialization_schema=SimpleStringSchema(),
        producer_config=producer_base_config.copy(),
    )

    # Write processed data to Kafka
    processed_stream.add_sink(processed_producer)

    # Kafka producer for alerts
    alert_producer = FlinkKafkaProducer(
        topic="alerts",
        serialization_schema=SimpleStringSchema(),
        producer_config=producer_base_config.copy(),
    )

    # Detect anomalies and generate alerts
    alert_stream = (
        processed_stream.key_by(lambda x: json.loads(x).get("sensor_id"))
        .process(AnomalyDetector())
        .filter(lambda x: "alert_id" in json.loads(x))
    )

    alert_stream.add_sink(alert_producer)

    return env


def create_critical_control_job():
    """Create Flink job optimized for critical control commands (low-latency)"""
    return create_flink_job(low_latency=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Flink Stream Processing Job")
    parser.add_argument(
        "--low-latency",
        action="store_true",
        help="Enable low-latency mode for critical controls (millisecond processing)",
    )
    args = parser.parse_args()

    env = create_flink_job(low_latency=args.low_latency)
    job_name = (
        "Critical Control Processing Job"
        if args.low_latency
        else "Sensor Data Processing Job"
    )
    env.execute(job_name)
