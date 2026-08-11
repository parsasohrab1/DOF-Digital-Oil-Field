"""
Edge-to-Stream Architecture
Direct integration from Edge Computing to Apache Flink with sub-second latency
Optimized data path from OPC UA/Modbus to stream processing
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import deque

from .kafka_utils import create_low_latency_producer
from .config import settings

logger = logging.getLogger(__name__)


class EdgeToStreamBridge:
    """
    Bridge between Edge Computing and Apache Flink
    Optimized for sub-second latency (< 1 second end-to-end)
    """

    def __init__(self):
        self.kafka_producer = None
        self.edge_cache = {}
        self.latency_metrics = deque(maxlen=1000)  # Track last 1000 latencies
        self.batch_buffer = []
        self.batch_size = 10  # Small batches for low latency
        self.batch_timeout = 0.1  # 100ms max batch wait

    def initialize(self):
        """Initialize Kafka producer with low-latency settings"""
        try:
            self.kafka_producer = create_low_latency_producer(topic="raw-sensor-data")
            logger.info("Edge-to-Stream bridge initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Edge-to-Stream bridge: {e}")

    async def stream_from_edge(
        self, edge_data: Dict[str, Any], source_protocol: str = "opcua"  # opcua, modbus
    ) -> bool:
        """
        Stream data from Edge Computing directly to Flink via Kafka

        Args:
            edge_data: Processed data from Edge Computing
            source_protocol: Source protocol (opcua, modbus)

        Returns:
            True if successfully streamed
        """
        start_time = time.perf_counter()

        try:
            # Enrich with protocol metadata
            enriched_data = {
                **edge_data,
                "source_protocol": source_protocol,
                "edge_processed": True,
                "edge_timestamp": datetime.utcnow().isoformat(),
                "stream_timestamp": datetime.utcnow().isoformat(),
            }

            # Add to batch buffer
            self.batch_buffer.append(enriched_data)

            # Send immediately if batch is full or timeout reached
            if len(self.batch_buffer) >= self.batch_size:
                await self._flush_batch()

            # Calculate latency
            latency = (time.perf_counter() - start_time) * 1000  # ms
            self.latency_metrics.append(latency)

            if latency > 1000:  # Warn if > 1 second
                logger.warning(f"Edge-to-Stream latency exceeded 1s: {latency:.2f}ms")

            return True

        except Exception as e:
            logger.error(f"Error streaming from edge: {e}")
            return False

    async def _flush_batch(self):
        """Flush batch buffer to Kafka"""
        if not self.batch_buffer:
            return

        try:
            batch_data = self.batch_buffer.copy()
            self.batch_buffer.clear()

            # Send each record immediately (no batching for low latency)
            for record in batch_data:
                if self.kafka_producer:
                    self.kafka_producer.send(
                        key=record.get("sensor_id", "unknown"),
                        value=json.dumps(record),
                        flush_immediately=True,  # Immediate flush for low latency
                    )

            logger.debug(f"Flushed {len(batch_data)} records to Kafka")

        except Exception as e:
            logger.error(f"Error flushing batch: {e}")

    async def stream_from_opcua(
        self, node_id: str, value: Any, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Stream data directly from OPC UA to Flink

        Optimized path: OPC UA → Edge Processing → Kafka → Flink
        Target latency: < 500ms
        """
        edge_data = {
            "sensor_id": node_id,
            "value": value,
            "timestamp": datetime.utcnow().isoformat(),
            "protocol": "opcua",
            "metadata": metadata or {},
        }

        return await self.stream_from_edge(edge_data, source_protocol="opcua")

    async def stream_from_modbus(
        self,
        device_id: int,
        register_address: int,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Stream data directly from Modbus to Flink

        Optimized path: Modbus → Edge Processing → Kafka → Flink
        Target latency: < 500ms
        """
        edge_data = {
            "sensor_id": f"MODBUS-{device_id}-{register_address}",
            "value": value,
            "timestamp": datetime.utcnow().isoformat(),
            "protocol": "modbus",
            "device_id": device_id,
            "register_address": register_address,
            "metadata": metadata or {},
        }

        return await self.stream_from_edge(edge_data, source_protocol="modbus")

    def get_latency_stats(self) -> Dict[str, float]:
        """Get latency statistics"""
        if not self.latency_metrics:
            return {"avg": 0, "min": 0, "max": 0, "p95": 0, "p99": 0}

        metrics = sorted(self.latency_metrics)
        n = len(metrics)

        return {
            "avg": sum(metrics) / n,
            "min": min(metrics),
            "max": max(metrics),
            "p95": metrics[int(n * 0.95)] if n > 0 else 0,
            "p99": metrics[int(n * 0.99)] if n > 0 else 0,
            "count": n,
        }

    async def periodic_flush(self):
        """Periodic flush task to ensure low latency"""
        while True:
            await asyncio.sleep(self.batch_timeout)
            if self.batch_buffer:
                await self._flush_batch()

    def close(self):
        """Close the bridge"""
        if self.kafka_producer:
            self.kafka_producer.close()


# Global instance
edge_to_stream_bridge = EdgeToStreamBridge()
