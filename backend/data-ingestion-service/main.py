"""
Data Ingestion Service
Manages connectors, schema validation, and DLQ handling
"""

import asyncio
import json
import os
import sys
import time
import httpx
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from dateutil.parser import parse as parse_date
except ImportError:
    # Fallback if dateutil not available
    def parse_date(s):
        from datetime import datetime

        return datetime.fromisoformat(s.replace("Z", "+00:00"))


from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field
import uvicorn

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import get_timescale_db, get_db
from shared.models import SensorData, Tag
from shared.config import settings
from shared.logging_config import setup_logging
from shared.kafka_utils import KafkaProducerWrapper, KafkaConsumerWrapper, KAFKA_TOPICS
from shared.opcua_client import OPCUAClient, ModbusTCPClient
from shared.industrial_security import industrial_firewall
from shared.offline_buffer import OfflineBufferManager
from shared.connection_monitor import ConnectionMonitor
from shared.edge_to_stream import edge_to_stream_bridge
from shared.sensor_health import sensor_health_monitor
from shared.mqtt_client import get_mqtt_client, MQTTMessageHandler
from shared.lorawan_client import get_lorawan_client
from shared.auth import require_authentication, require_roles
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from sqlalchemy.orm import Session

# Setup logging
logger = setup_logging("data-ingestion-service")

app = FastAPI(title="OGIM Data Ingestion Service", version="1.0.0")

setup_tracing(app, "data-ingestion-service", instrument_requests=True)
setup_metrics(app, "data-ingestion-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Kafka producer
kafka_producer = None
opcua_client = None

# Offline buffer and connection monitor
offline_buffer = None
connection_monitor = None
retry_task = None

VALIDATION_SUCCESS = Counter(
    "ingest_validation_success_total",
    "Successful records ingested",
    ["source"],
)
VALIDATION_FAILURE = Counter(
    "ingest_validation_failure_total",
    "Records rejected during ingestion",
    ["source", "reason"],
)

INGEST_LATENCY = Histogram(
    "ingest_request_latency_seconds",
    "Latency of ingest request processing",
    ["source"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20),
)
INGEST_RECORDS_PER_REQUEST = Histogram(
    "ingest_records_per_request",
    "Number of records processed per ingestion request",
    ["source"],
    buckets=(1, 5, 10, 20, 50, 100, 200, 500, 1000),
)
INGEST_PAYLOAD_BYTES = Counter(
    "ingest_payload_bytes_total",
    "Total bytes of sensor payload persisted",
    ["source"],
)

BUFFERED_RECORDS = Counter(
    "ingest_buffered_records_total",
    "Records buffered due to offline status",
    ["source"],
)

RETRY_ATTEMPTS = Counter(
    "ingest_retry_attempts_total",
    "Total retry attempts for buffered records",
    ["source", "status"],  # status: success, failure
)

CONNECTION_STATUS = Counter(
    "ingest_connection_status_changes_total",
    "Connection status changes (online/offline)",
    ["status"],
)


def _record_validation(source: str, success: bool, reason: str = ""):
    if success:
        VALIDATION_SUCCESS.labels(source=source).inc()
    else:
        VALIDATION_FAILURE.labels(source=source, reason=reason or "unknown").inc()


class SensorDataModel(BaseModel):
    timestamp: datetime
    well_name: str
    equipment_type: str
    sensor_type: str
    value: float
    unit: str
    sensor_id: str
    data_quality: Optional[str] = "good"


class IngestRequest(BaseModel):
    records: List[SensorDataModel]
    source: str = Field(..., description="Data source identifier")


class IngestResponse(BaseModel):
    status: str
    records_ingested: int
    source: str


# Role dependencies
require_ingest_read = require_roles({"system_admin", "data_engineer"})
require_ingest_admin = require_roles({"system_admin"})


class ConnectorConfig(BaseModel):
    connector_id: str
    connector_type: str  # opcua, modbus, kafka
    config: dict


@app.on_event("startup")
async def startup_event():
    """Initialize database and Kafka on startup"""
    global kafka_producer, opcua_client, offline_buffer, connection_monitor, retry_task
    global mqtt_client, mqtt_handler, lorawan_client
    logger.info("Starting data ingestion service...")
    try:
        kafka_producer = KafkaProducerWrapper(KAFKA_TOPICS["RAW_SENSOR_DATA"])

        # Initialize offline buffer if enabled
        if settings.OFFLINE_BUFFER_ENABLED:
            offline_buffer = OfflineBufferManager(
                buffer_path=settings.OFFLINE_BUFFER_PATH,
                max_buffer_size=settings.OFFLINE_BUFFER_MAX_SIZE,
                max_buffer_size_mb=settings.OFFLINE_BUFFER_MAX_SIZE_MB,
                cleanup_interval=settings.OFFLINE_BUFFER_CLEANUP_INTERVAL,
            )
            logger.info("Offline buffer initialized")

        # Initialize Edge-to-Stream bridge
        if settings.EDGE_COMPUTING_ENABLED:
            edge_to_stream_bridge.initialize()
            asyncio.create_task(edge_to_stream_bridge.periodic_flush())
            logger.info("Edge-to-Stream bridge initialized")

        # Initialize connection monitor if enabled
        if settings.CONNECTION_MONITOR_ENABLED:
            check_hosts = []
            if settings.CONNECTION_CHECK_HOSTS:
                check_hosts = [
                    h.strip() for h in settings.CONNECTION_CHECK_HOSTS.split(",")
                ]

            check_urls = []
            if settings.CONNECTION_CHECK_URLS:
                check_urls = [
                    u.strip() for u in settings.CONNECTION_CHECK_URLS.split(",")
                ]

            # Add Kafka and TimescaleDB to check hosts if not specified
            if not check_hosts and not check_urls:
                # Parse Kafka bootstrap servers
                for server in settings.KAFKA_BOOTSTRAP_SERVERS.split(","):
                    server = server.strip()
                    if ":" in server:
                        check_hosts.append(server)
                    else:
                        check_hosts.append(f"{server}:9092")

            connection_monitor = ConnectionMonitor(
                check_interval=settings.CONNECTION_CHECK_INTERVAL,
                timeout=settings.CONNECTION_CHECK_TIMEOUT,
                check_urls=check_urls,
                check_hosts=check_hosts,
            )

            # Add callback for connection status changes
            def on_connection_change(is_online: bool):
                status = "online" if is_online else "offline"
                CONNECTION_STATUS.labels(status=status).inc()
                logger.info(f"Connection status changed: {status}")
                if is_online and offline_buffer:
                    # Start retry task when connection is restored
                    asyncio.create_task(retry_buffered_records())

            connection_monitor.add_callback(on_connection_change)
            connection_monitor.start_monitoring()
            logger.info("Connection monitor started")

        # Initialize OPC-UA client if configured
        if settings.OPCUA_SERVER_URL:
            opcua_client = OPCUAClient()
            opcua_client.connect()

        # Initialize MQTT client if enabled
        if settings.MQTT_ENABLED:
            try:
                mqtt_client = get_mqtt_client(
                    broker_host=settings.MQTT_BROKER_HOST,
                    broker_port=settings.MQTT_BROKER_PORT,
                    username=settings.MQTT_USERNAME,
                    password=settings.MQTT_PASSWORD,
                    qos=settings.MQTT_QOS,
                )

                if mqtt_client.connect():
                    mqtt_handler = MQTTMessageHandler(mqtt_client)

                    # Subscribe to configured topics
                    topics = [t.strip() for t in settings.MQTT_TOPICS.split(",")]
                    for topic in topics:
                        mqtt_client.subscribe(
                            topic, callback=mqtt_handler.handle_sensor_data
                        )

                    logger.info(
                        f"MQTT client connected and subscribed to {len(topics)} topics"
                    )
                else:
                    logger.warning("Failed to connect to MQTT broker")
            except Exception as e:
                logger.error(f"Failed to initialize MQTT client: {e}")

        # Initialize LoRaWAN client if enabled
        if settings.LORAWAN_ENABLED:
            try:
                lorawan_client = get_lorawan_client(
                    network_type=settings.LORAWAN_NETWORK_TYPE,
                    api_url=settings.LORAWAN_API_URL,
                    api_key=settings.LORAWAN_API_KEY,
                    app_id=settings.LORAWAN_APP_ID,
                    webhook_url=settings.LORAWAN_WEBHOOK_URL,
                )
                logger.info(
                    f"LoRaWAN client initialized (network: {settings.LORAWAN_NETWORK_TYPE})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize LoRaWAN client: {e}")

        # Start retry task
        if offline_buffer:
            retry_task = asyncio.create_task(retry_buffered_records_loop())

        logger.info(
            "Data ingestion service ready. Ensure TimescaleDB migrations are applied."
        )
    except Exception as e:
        logger.error(f"Failed to initialize data ingestion service: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if retry_task:
        retry_task.cancel()
        try:
            await retry_task
        except asyncio.CancelledError:
            pass

    # Disconnect MQTT client
    if mqtt_client:
        mqtt_client.disconnect()
        logger.info("MQTT client disconnected")

    if connection_monitor:
        connection_monitor.stop_monitoring()

    if offline_buffer:
        offline_buffer.shutdown()

    if kafka_producer:
        kafka_producer.close()
    if opcua_client:
        opcua_client.disconnect()


@app.post("/ingest")
async def ingest_data(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    tsdb: Session = Depends(get_timescale_db),
    meta_db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_ingest_read),
) -> IngestResponse:
    """Ingest sensor data"""
    start_time = time.perf_counter()
    payload_bytes = 0
    try:
        validated_records = []

        # Load tag metadata once
        sensor_ids = {r.sensor_id for r in request.records}
        tags = {
            tag.tag_id: tag
            for tag in meta_db.query(Tag).filter(Tag.tag_id.in_(sensor_ids)).all()
        }

        for record in request.records:
            tag = tags.get(record.sensor_id)
            if not tag:
                _record_validation(request.source, False, "missing_tag")
                raise HTTPException(
                    status_code=422, detail=f"Unknown sensor_id '{record.sensor_id}'"
                )

            # Validate types
            if record.sensor_type != tag.sensor_type:
                _record_validation(request.source, False, "sensor_type_mismatch")
                raise HTTPException(
                    status_code=422,
                    detail=f"Sensor type mismatch for {record.sensor_id}",
                )

            if record.unit != tag.unit:
                _record_validation(request.source, False, "unit_mismatch")
                raise HTTPException(
                    status_code=422, detail=f"Unit mismatch for {record.sensor_id}"
                )

            if tag.valid_range_min is not None and record.value < tag.valid_range_min:
                _record_validation(request.source, False, "below_range")
                raise HTTPException(
                    status_code=422,
                    detail=f"Value below valid range for {record.sensor_id}",
                )

            if tag.valid_range_max is not None and record.value > tag.valid_range_max:
                _record_validation(request.source, False, "above_range")
                raise HTTPException(
                    status_code=422,
                    detail=f"Value above valid range for {record.sensor_id}",
                )

            if record.data_quality and record.data_quality not in {
                "good",
                "bad",
                "uncertain",
            }:
                _record_validation(request.source, False, "bad_quality")
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid data_quality for {record.sensor_id}",
                )

            # Sensor health monitoring and drift detection
            health_status = sensor_health_monitor.assess_health(
                sensor_id=record.sensor_id,
                value=record.value,
                timestamp=record.timestamp,
                expected_range=(
                    (tag.valid_range_min, tag.valid_range_max)
                    if tag.valid_range_min is not None
                    and tag.valid_range_max is not None
                    else None
                ),
            )

            # Use corrected value if drift detected
            final_value = record.value
            if (
                health_status.correction_applied
                and health_status.corrected_value is not None
            ):
                final_value = health_status.corrected_value
                record.data_quality = health_status.data_quality

            db_record = SensorData(
                timestamp=record.timestamp,
                tag_id=record.sensor_id,
                value=final_value,
                data_quality=(
                    health_status.data_quality
                    if health_status.correction_applied
                    else record.data_quality
                ),
            )
            tsdb.add(db_record)
            validated_records.append(record.dict())
            _record_validation(request.source, True)
            payload_bytes += len(json.dumps(record.dict(), default=str).encode("utf-8"))

        tsdb.commit()

        # Push straight to the Gateway's realtime WebSocket stream so
        # dashboards see new readings within one HTTP hop instead of waiting
        # for the Gateway's next poll cycle (previously up to 1s).
        if validated_records:
            background_tasks.add_task(
                push_to_gateway_realtime,
                validated_records,
                request.source,
            )

        # Publish to Kafka or buffer if offline
        if validated_records:
            if connection_monitor and not connection_monitor.is_online:
                # System is offline - buffer records
                buffer_records(validated_records, request.source)
            elif kafka_producer:
                # System is online - publish to Kafka
                background_tasks.add_task(
                    publish_to_kafka, validated_records, request.source
                )
            else:
                # No Kafka producer - buffer records
                if offline_buffer:
                    buffer_records(validated_records, request.source)
                else:
                    logger.warning(
                        "No Kafka producer and no buffer - records may be lost"
                    )

        logger.info(f"Ingested {len(validated_records)} records from {request.source}")

        duration = time.perf_counter() - start_time
        INGEST_LATENCY.labels(source=request.source).observe(duration)
        INGEST_RECORDS_PER_REQUEST.labels(source=request.source).observe(
            len(validated_records)
        )
        if payload_bytes:
            INGEST_PAYLOAD_BYTES.labels(source=request.source).inc(payload_bytes)

        return IngestResponse(
            status="success",
            records_ingested=len(validated_records),
            source=request.source,
        )
    except HTTPException:
        # Preserve the specific status code/detail from the validation checks
        # above (422 unknown sensor, mismatch, out-of-range, ...) instead of
        # falling through to the generic 400 handler below.
        duration = time.perf_counter() - start_time
        INGEST_LATENCY.labels(source=request.source).observe(duration)
        INGEST_RECORDS_PER_REQUEST.labels(source=request.source).observe(
            len(validated_records)
        )
        if payload_bytes:
            INGEST_PAYLOAD_BYTES.labels(source=request.source).inc(payload_bytes)
        raise
    except Exception as e:
        duration = time.perf_counter() - start_time
        INGEST_LATENCY.labels(source=request.source).observe(duration)
        INGEST_RECORDS_PER_REQUEST.labels(source=request.source).observe(
            len(validated_records)
        )
        if payload_bytes:
            INGEST_PAYLOAD_BYTES.labels(source=request.source).inc(payload_bytes)
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")


def buffer_records(records: List[dict], source: str):
    """Buffer records when offline"""
    if not offline_buffer:
        logger.warning("Offline buffer not available - records may be lost")
        return

    buffered_count = 0
    for record in records:
        record_id = f"{source}_{record['sensor_id']}_{record['timestamp']}"
        timestamp = record.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = parse_date(timestamp).timestamp()
        elif isinstance(timestamp, datetime):
            timestamp = timestamp.timestamp()
        else:
            timestamp = time.time()

        if offline_buffer.add_record(record_id, source, record, timestamp):
            buffered_count += 1
            BUFFERED_RECORDS.labels(source=source).inc()

    logger.info(f"Buffered {buffered_count}/{len(records)} records from {source}")


GATEWAY_REALTIME_PUSH_URL = (
    f"http://{os.getenv('SERVICE_HOST', 'localhost')}:8000/internal/realtime/publish"
)


async def push_to_gateway_realtime(records: List[dict], source: str):
    """Push freshly-ingested records straight to the Gateway's realtime
    WebSocket stream, instead of relying on the Gateway polling
    data-ingestion's REST endpoint once a second. Best-effort: a failure here
    must never affect the ingest response, since Kafka/the buffer remain the
    durable path for this data.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                GATEWAY_REALTIME_PUSH_URL,
                headers={"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN},
                json={
                    "type": "sensor_data",
                    "data": {"sensor_records": records, "source": source},
                },
            )
    except Exception as e:
        logger.debug(f"Realtime push to gateway failed (non-fatal): {e}")


def publish_to_kafka(records: List[dict], source: str):
    """Publish records to Kafka"""
    try:
        for record in records:
            kafka_producer.send(record["sensor_id"], record)
        kafka_producer.flush()
        logger.info(f"Published {len(records)} records to Kafka")
    except Exception as e:
        logger.error(f"Failed to publish to Kafka: {e}")
        # If publish fails and buffer is available, buffer the records
        if offline_buffer:
            logger.info("Buffering records due to Kafka publish failure")
            buffer_records(records, source)


async def retry_buffered_records():
    """Retry sending buffered records when connection is restored"""
    if not offline_buffer or not kafka_producer:
        return

    if not connection_monitor or not connection_monitor.is_online:
        return

    logger.info("Retrying buffered records...")
    pending = offline_buffer.get_pending_records(limit=1000)

    if not pending:
        return

    logger.info(f"Found {len(pending)} pending records to retry")

    success_count = 0
    failure_count = 0

    for record_info in pending:
        try:
            record = record_info["data"]
            source = record_info["source"]
            record_id = record_info["record_id"]

            # Try to publish
            kafka_producer.send(record["sensor_id"], record)
            kafka_producer.flush()

            # Mark as sent
            offline_buffer.mark_sent(record_id)
            success_count += 1
            RETRY_ATTEMPTS.labels(source=source, status="success").inc()

        except Exception as e:
            logger.warning(f"Failed to retry record {record_info['record_id']}: {e}")
            offline_buffer.mark_failed(record_info["record_id"])
            failure_count += 1
            RETRY_ATTEMPTS.labels(source=record_info["source"], status="failure").inc()

    if success_count > 0:
        logger.info(f"Successfully retried {success_count} buffered records")
    if failure_count > 0:
        logger.warning(f"Failed to retry {failure_count} buffered records")


async def retry_buffered_records_loop():
    """Background task to periodically retry buffered records"""
    import asyncio

    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            if connection_monitor and connection_monitor.is_online:
                await retry_buffered_records()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in retry loop: {e}")
            await asyncio.sleep(60)  # Wait longer on error


@app.get("/connectors")
async def list_connectors(_: Dict[str, Any] = Depends(require_ingest_admin)):
    """List all connectors"""
    connectors = []

    # OPC-UA connector
    if opcua_client:
        connectors.append(
            {
                "connector_id": "opcua-connector-1",
                "type": "OPC-UA",
                "status": "running" if opcua_client.connected else "stopped",
                "last_update": datetime.utcnow().isoformat(),
            }
        )

    return {"connectors": connectors}


@app.post("/connectors/{connector_id}/start")
async def start_connector(
    connector_id: str, _: Dict[str, Any] = Depends(require_ingest_admin)
):
    """Start a connector"""
    if connector_id.startswith("opcua") and opcua_client:
        success = opcua_client.connect()
        if success:
            return {"message": f"Connector {connector_id} started"}
        else:
            raise HTTPException(status_code=500, detail="Failed to start connector")

    raise HTTPException(status_code=404, detail="Connector not found")


@app.post("/connectors/{connector_id}/stop")
async def stop_connector(
    connector_id: str, _: Dict[str, Any] = Depends(require_ingest_admin)
):
    """Stop a connector"""
    if connector_id.startswith("opcua") and opcua_client:
        opcua_client.disconnect()
        return {"message": f"Connector {connector_id} stopped"}

    raise HTTPException(status_code=404, detail="Connector not found")


@app.get("/opcua/nodes")
async def list_opcua_nodes(_: Dict[str, Any] = Depends(require_ingest_admin)):
    """List available OPC-UA nodes"""
    if not opcua_client or not opcua_client.connected:
        raise HTTPException(status_code=503, detail="OPC-UA client not connected")

    nodes = opcua_client.browse_nodes()
    return {"nodes": nodes, "count": len(nodes)}


@app.post("/opcua/read")
async def read_opcua_node(
    node_id: str, _: Dict[str, Any] = Depends(require_ingest_admin)
):
    """Read OPC-UA node value"""
    if not opcua_client or not opcua_client.connected:
        raise HTTPException(status_code=503, detail="OPC-UA client not connected")

    value = opcua_client.read_node(node_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Failed to read node")

    return {
        "node_id": node_id,
        "value": value,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/opcua/write")
async def write_opcua_node(
    node_id: str, value: float, _: Dict[str, Any] = Depends(require_ingest_admin)
):
    """Write value to OPC-UA node"""
    if not opcua_client or not opcua_client.connected:
        raise HTTPException(status_code=503, detail="OPC-UA client not connected")

    success = opcua_client.write_node(node_id, value)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to write node")

    return {"message": "Value written successfully", "node_id": node_id, "value": value}


@app.post("/stream/opcua")
async def stream_from_opcua(
    node_id: str,
    value: float,
    metadata: Optional[Dict[str, Any]] = None,
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Stream data directly from OPC UA to Flink via Edge-to-Stream bridge"""
    if not settings.EDGE_COMPUTING_ENABLED:
        raise HTTPException(status_code=503, detail="Edge Computing not enabled")

    success = await edge_to_stream_bridge.stream_from_opcua(
        node_id=node_id, value=value, metadata=metadata
    )

    if success:
        return {"status": "streamed", "node_id": node_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to stream data")


@app.post("/stream/modbus")
async def stream_from_modbus(
    device_id: int,
    register_address: int,
    value: float,
    metadata: Optional[Dict[str, Any]] = None,
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Stream data directly from Modbus to Flink via Edge-to-Stream bridge"""
    if not settings.EDGE_COMPUTING_ENABLED:
        raise HTTPException(status_code=503, detail="Edge Computing not enabled")

    success = await edge_to_stream_bridge.stream_from_modbus(
        device_id=device_id,
        register_address=register_address,
        value=value,
        metadata=metadata,
    )

    if success:
        return {
            "status": "streamed",
            "device_id": device_id,
            "register": register_address,
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to stream data")


@app.get("/sensor-health/{sensor_id}")
async def get_sensor_health(
    sensor_id: str, _: Dict[str, Any] = Depends(require_authentication)
):
    """Get sensor health status and drift information"""
    summary = sensor_health_monitor.get_health_summary()
    if sensor_id not in summary:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return summary[sensor_id]


@app.get("/sensor-health")
async def get_all_sensor_health(_: Dict[str, Any] = Depends(require_authentication)):
    """Get health summary for all sensors"""
    return sensor_health_monitor.get_health_summary()


@app.get("/edge-stream/stats")
async def get_edge_stream_stats(_: Dict[str, Any] = Depends(require_authentication)):
    """Get Edge-to-Stream latency statistics"""
    if not settings.EDGE_COMPUTING_ENABLED:
        raise HTTPException(status_code=503, detail="Edge Computing not enabled")

    return edge_to_stream_bridge.get_latency_stats()


@app.get("/health")
async def health(tsdb: Session = Depends(get_timescale_db)):
    """Health check"""
    records_count = tsdb.query(SensorData).count()

    health_data = {
        "status": "healthy",
        "records_in_db": records_count,
        "kafka_connected": kafka_producer is not None,
        "opcua_connected": opcua_client.connected if opcua_client else False,
    }

    # Add connection status
    if connection_monitor:
        conn_status = connection_monitor.get_status()
        health_data["connection_status"] = conn_status
        health_data["is_online"] = conn_status["is_online"]

    # Add buffer stats
    if offline_buffer:
        buffer_stats = offline_buffer.get_buffer_stats()
        health_data["buffer_stats"] = buffer_stats
        health_data["buffered_records"] = buffer_stats.get("total_records", 0)

    # Add MQTT status
    if mqtt_client:
        mqtt_status = mqtt_client.get_status()
        if mqtt_handler:
            mqtt_status.update(mqtt_handler.get_stats())
        health_data["mqtt"] = mqtt_status

    # Add LoRaWAN status
    if lorawan_client:
        health_data["lorawan"] = lorawan_client.get_stats()

    return health_data


@app.get("/buffer/stats")
async def get_buffer_stats(_: Dict[str, Any] = Depends(require_ingest_admin)):
    """Get offline buffer statistics"""
    if not offline_buffer:
        raise HTTPException(status_code=404, detail="Offline buffer not enabled")

    return offline_buffer.get_buffer_stats()


@app.post("/buffer/retry")
async def manual_retry(_: Dict[str, Any] = Depends(require_ingest_admin)):
    """Manually trigger retry of buffered records"""
    if not offline_buffer:
        raise HTTPException(status_code=404, detail="Offline buffer not enabled")

    await retry_buffered_records()
    stats = offline_buffer.get_buffer_stats()

    return {
        "message": "Retry triggered",
        "buffered_records": stats.get("total_records", 0),
    }


@app.delete("/buffer/clear")
async def clear_buffer(
    source: Optional[str] = None, _: Dict[str, Any] = Depends(require_ingest_admin)
):
    """Clear buffered records (optionally for a specific source)"""
    if not offline_buffer:
        raise HTTPException(status_code=404, detail="Offline buffer not enabled")

    deleted = offline_buffer.clear_buffer(source=source)
    return {
        "message": f"Cleared {deleted} records from buffer",
        "deleted_count": deleted,
    }


@app.post("/mqtt/ingest")
async def ingest_mqtt_data(
    topic: str,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    _: Dict[str, Any] = Depends(require_authentication),
):
    """
    Ingest data received from MQTT
    This endpoint can be called by MQTT message handler
    """
    try:
        # Process MQTT message
        if mqtt_handler:
            # Create a mock message object for handler
            class MockMessage:
                def __init__(self):
                    self.qos = 1
                    self.topic = topic

            mock_msg = MockMessage()
            sensor_data = mqtt_handler.handle_sensor_data(topic, payload, mock_msg)
        else:
            # Fallback processing
            sensor_data = {
                "sensor_id": payload.get(
                    "sensor_id", topic.split("/")[1] if "/" in topic else "unknown"
                ),
                "value": payload.get("value"),
                "timestamp": datetime.utcnow(),
                "source": "mqtt",
                "topic": topic,
            }

        if not sensor_data or "value" not in sensor_data:
            raise HTTPException(status_code=400, detail="Invalid MQTT payload")

        # Create sensor data record
        sensor_record = SensorDataModel(
            timestamp=sensor_data.get("timestamp", datetime.utcnow()),
            well_name=sensor_data.get("well_name", "unknown"),
            equipment_type=sensor_data.get("equipment_type", "sensor"),
            sensor_type=sensor_data.get("sensor_type", "unknown"),
            value=sensor_data["value"],
            unit=sensor_data.get("unit", ""),
            sensor_id=sensor_data.get("sensor_id", "unknown"),
            data_quality=sensor_data.get("data_quality", "good"),
        )

        # Ingest the record
        ingest_request = IngestRequest(records=[sensor_record], source="mqtt")
        tsdb = next(get_timescale_db())
        meta_db = next(get_db())
        await ingest_data(ingest_request, background_tasks, tsdb, meta_db, _)

        return {
            "status": "success",
            "message": "MQTT data ingested successfully",
            "sensor_id": sensor_data.get("sensor_id"),
            "topic": topic,
        }
    except Exception as e:
        logger.error(f"Error ingesting MQTT data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/lorawan/webhook")
async def lorawan_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    _: Dict[str, Any] = Depends(require_authentication),
):
    """
    Webhook endpoint for LoRaWAN network servers (TTN, ChirpStack)
    Receives uplink messages from LoRaWAN sensors
    """
    try:
        if not lorawan_client:
            raise HTTPException(
                status_code=503, detail="LoRaWAN client not initialized"
            )

        # Get request data
        uplink_data = await request.json()

        # Process uplink message
        sensor_data = lorawan_client.handle_uplink(uplink_data)

        if not sensor_data:
            raise HTTPException(
                status_code=400, detail="Failed to process LoRaWAN uplink"
            )

        # Create sensor data record
        sensor_record = SensorDataModel(
            timestamp=sensor_data.get("timestamp", datetime.utcnow()),
            well_name=sensor_data.get("well_name", "unknown"),
            equipment_type=sensor_data.get("equipment_type", "lorawan_sensor"),
            sensor_type=sensor_data.get("sensor_type", "unknown"),
            value=sensor_data.get("value", 0.0),
            unit=sensor_data.get("unit", ""),
            sensor_id=sensor_data.get(
                "sensor_id", sensor_data.get("device_id", "unknown")
            ),
            data_quality="good",
        )

        # Ingest the record
        ingest_request = IngestRequest(records=[sensor_record], source="lorawan")
        tsdb = next(get_timescale_db())
        meta_db = next(get_db())
        await ingest_data(ingest_request, background_tasks, tsdb, meta_db, _)

        # Call registered callbacks
        for callback in lorawan_client.message_callbacks:
            try:
                callback(sensor_data)
            except Exception as e:
                logger.error(f"Error in LoRaWAN callback: {e}")

        return {
            "status": "success",
            "message": "LoRaWAN data ingested successfully",
            "device_id": sensor_data.get("device_id"),
            "network_type": lorawan_client.network_type,
        }
    except Exception as e:
        logger.error(f"Error processing LoRaWAN webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/wireless/status")
async def get_wireless_status(_: Dict[str, Any] = Depends(require_authentication)):
    """Get status of wireless protocol clients"""
    status = {"mqtt": None, "lorawan": None}

    if mqtt_client:
        mqtt_status = mqtt_client.get_status()
        if mqtt_handler:
            mqtt_status.update(mqtt_handler.get_stats())
        status["mqtt"] = mqtt_status

    if lorawan_client:
        status["lorawan"] = lorawan_client.get_stats()

    return status


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
