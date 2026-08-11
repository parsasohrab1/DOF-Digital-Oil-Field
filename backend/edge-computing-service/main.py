"""
Edge Computing Service
Provides local processing and analysis at the edge for remote oil field locations
Reduces latency and bandwidth requirements by processing data locally
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.config import settings
from shared.logging_config import setup_logging
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from shared.auth import require_authentication, require_roles
from shared.disconnected_operation import get_disconnected_op_manager
from shared.connection_monitor import ConnectionMonitor

# Setup logging
logger = setup_logging("edge-computing-service")

app = FastAPI(title="OGIM Edge Computing Service", version="1.0.0")
setup_metrics(app, "edge-computing-service")
setup_tracing(app, "edge-computing-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Edge processing modules
edge_ml_models = {}
edge_cache = {}

# Initialize disconnected operation manager
disconnected_op = get_disconnected_op_manager(
    data_dir=os.getenv("EDGE_DATA_DIR", "./data/edge"),
    sync_interval=int(os.getenv("EDGE_SYNC_INTERVAL", "60")),
)


class SensorDataPoint(BaseModel):
    sensor_id: str
    value: float
    timestamp: datetime
    sensor_type: str
    unit: str


class EdgeAnalysisRequest(BaseModel):
    sensor_data: List[SensorDataPoint]
    analysis_type: str = Field(
        ..., description="Type of analysis: anomaly, threshold, trend, aggregation"
    )
    well_name: Optional[str] = None
    equipment_id: Optional[str] = None


class EdgeAnalysisResponse(BaseModel):
    analysis_id: str
    analysis_type: str
    results: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    recommendations: List[str]
    processed_locally: bool = True
    timestamp: datetime


class EdgeMLModelRequest(BaseModel):
    sensor_id: str
    features: Dict[str, float]
    model_type: str = (
        "anomaly_detection"  # anomaly_detection, threshold_check, trend_analysis
    )


class EdgeMLModelResponse(BaseModel):
    sensor_id: str
    prediction: float
    confidence: float
    anomaly_detected: bool
    processed_locally: bool = True
    timestamp: datetime


def simple_anomaly_detection(sensor_data: List[SensorDataPoint]) -> Dict[str, Any]:
    """Simple anomaly detection at edge"""
    results = {"anomalies": [], "statistics": {}}

    # Group by sensor
    by_sensor = {}
    for point in sensor_data:
        if point.sensor_id not in by_sensor:
            by_sensor[point.sensor_id] = []
        by_sensor[point.sensor_id].append(point.value)

    # Detect anomalies using statistical methods
    for sensor_id, values in by_sensor.items():
        if len(values) < 3:
            continue

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = variance**0.5

        # Z-score based anomaly detection
        for i, value in enumerate(values):
            z_score = abs((value - mean) / std_dev) if std_dev > 0 else 0
            if z_score > 3:  # 3 standard deviations
                results["anomalies"].append(
                    {
                        "sensor_id": sensor_id,
                        "value": value,
                        "z_score": z_score,
                        "timestamp": sensor_data[i].timestamp.isoformat(),
                    }
                )

        results["statistics"][sensor_id] = {
            "mean": mean,
            "std_dev": std_dev,
            "min": min(values),
            "max": max(values),
        }

    return results


def threshold_check(
    sensor_data: List[SensorDataPoint], thresholds: Dict[str, Dict[str, float]]
) -> Dict[str, Any]:
    """Check sensor values against thresholds"""
    alerts = []

    for point in sensor_data:
        sensor_thresholds = thresholds.get(point.sensor_id, {})

        if (
            "critical_high" in sensor_thresholds
            and point.value > sensor_thresholds["critical_high"]
        ):
            alerts.append(
                {
                    "sensor_id": point.sensor_id,
                    "severity": "critical",
                    "message": f"Value {point.value} exceeds critical high threshold {sensor_thresholds['critical_high']}",
                    "timestamp": point.timestamp.isoformat(),
                }
            )
        elif (
            "warning_high" in sensor_thresholds
            and point.value > sensor_thresholds["warning_high"]
        ):
            alerts.append(
                {
                    "sensor_id": point.sensor_id,
                    "severity": "warning",
                    "message": f"Value {point.value} exceeds warning high threshold {sensor_thresholds['warning_high']}",
                    "timestamp": point.timestamp.isoformat(),
                }
            )
        elif (
            "critical_low" in sensor_thresholds
            and point.value < sensor_thresholds["critical_low"]
        ):
            alerts.append(
                {
                    "sensor_id": point.sensor_id,
                    "severity": "critical",
                    "message": f"Value {point.value} below critical low threshold {sensor_thresholds['critical_low']}",
                    "timestamp": point.timestamp.isoformat(),
                }
            )
        elif (
            "warning_low" in sensor_thresholds
            and point.value < sensor_thresholds["warning_low"]
        ):
            alerts.append(
                {
                    "sensor_id": point.sensor_id,
                    "severity": "warning",
                    "message": f"Value {point.value} below warning low threshold {sensor_thresholds['warning_low']}",
                    "timestamp": point.timestamp.isoformat(),
                }
            )

    return {"alerts": alerts, "checked_count": len(sensor_data)}


def trend_analysis(sensor_data: List[SensorDataPoint]) -> Dict[str, Any]:
    """Simple trend analysis at edge"""
    results = {}

    # Group by sensor
    by_sensor = {}
    for point in sensor_data:
        if point.sensor_id not in by_sensor:
            by_sensor[point.sensor_id] = []
        by_sensor[point.sensor_id].append((point.timestamp, point.value))

    for sensor_id, points in by_sensor.items():
        if len(points) < 2:
            continue

        # Sort by timestamp
        points.sort(key=lambda x: x[0])

        # Calculate trend (simple linear regression)
        values = [p[1] for p in points]
        n = len(values)

        if n >= 2:
            # Simple slope calculation
            first_half = values[: n // 2]
            second_half = values[n // 2 :]
            first_avg = sum(first_half) / len(first_half)
            second_avg = sum(second_half) / len(second_half)

            trend = (
                "increasing"
                if second_avg > first_avg * 1.05
                else "decreasing" if second_avg < first_avg * 0.95 else "stable"
            )

            results[sensor_id] = {
                "trend": trend,
                "rate_of_change": (
                    (second_avg - first_avg) / first_avg if first_avg != 0 else 0
                ),
                "current_value": values[-1],
                "first_value": values[0],
            }

    return results


def aggregation_analysis(
    sensor_data: List[SensorDataPoint], interval: str = "1h"
) -> Dict[str, Any]:
    """Aggregate sensor data at edge"""
    results = {}

    # Group by sensor
    by_sensor = {}
    for point in sensor_data:
        if point.sensor_id not in by_sensor:
            by_sensor[point.sensor_id] = []
        by_sensor[point.sensor_id].append(point.value)

    for sensor_id, values in by_sensor.items():
        if values:
            results[sensor_id] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "sum": sum(values),
            }

    return results


@app.post("/analyze", response_model=EdgeAnalysisResponse)
async def analyze_at_edge(
    request: EdgeAnalysisRequest, _: Dict[str, Any] = Depends(require_authentication)
):
    """
    Perform analysis at edge without sending to cloud
    Works in both online and disconnected modes
    """
    analysis_id = f"EDGE-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    try:
        if request.analysis_type == "anomaly":
            results = simple_anomaly_detection(request.sensor_data)
            alerts = results.get("anomalies", [])
            recommendations = []
            if alerts:
                recommendations.append("Review sensor calibration")
                recommendations.append("Check for equipment malfunction")

                # Store critical alerts in disconnected mode
                for anomaly in alerts:
                    if anomaly.get("z_score", 0) > 4:  # Very critical
                        disconnected_op.add_critical_alert(
                            alert_id=f"{analysis_id}-{anomaly['sensor_id']}",
                            sensor_id=anomaly["sensor_id"],
                            alert_type="anomaly",
                            severity="critical",
                            message=f"Critical anomaly detected: z-score={anomaly.get('z_score', 0):.2f}",
                            data=anomaly,
                        )

        elif request.analysis_type == "threshold":
            # Get thresholds from cache or default
            thresholds = edge_cache.get("thresholds", {})
            results = threshold_check(request.sensor_data, thresholds)
            alerts = results.get("alerts", [])
            recommendations = []
            if alerts:
                recommendations.append("Immediate action required for critical alerts")

                # Store critical threshold alerts
                for alert in alerts:
                    if alert.get("severity") == "critical":
                        disconnected_op.add_critical_alert(
                            alert_id=f"{analysis_id}-{alert['sensor_id']}",
                            sensor_id=alert["sensor_id"],
                            alert_type="threshold",
                            severity="critical",
                            message=alert.get("message", "Threshold exceeded"),
                            data=alert,
                        )

        elif request.analysis_type == "trend":
            results = trend_analysis(request.sensor_data)
            alerts = []
            recommendations = []
            for sensor_id, trend_data in results.items():
                if (
                    trend_data.get("trend") == "increasing"
                    and trend_data.get("rate_of_change", 0) > 0.1
                ):
                    recommendations.append(
                        f"Sensor {sensor_id} shows rapid increase - monitor closely"
                    )

                    # Record local decision for rapid changes
                    disconnected_op.record_local_decision(
                        decision_id=f"{analysis_id}-{sensor_id}",
                        decision_type="trend_monitoring",
                        action_taken="alert_operator",
                        reason=f"Rapid increase detected: {trend_data.get('rate_of_change', 0):.2%}",
                        sensor_id=sensor_id,
                        data=trend_data,
                    )

        elif request.analysis_type == "aggregation":
            results = aggregation_analysis(request.sensor_data)
            alerts = []
            recommendations = []

            # Cache aggregated results
            cache_key = f"aggregation:{request.well_name or 'default'}:{datetime.utcnow().strftime('%Y%m%d%H')}"
            disconnected_op.cache_processed_data(cache_key, results, ttl_seconds=3600)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown analysis type: {request.analysis_type}",
            )

        response = EdgeAnalysisResponse(
            analysis_id=analysis_id,
            analysis_type=request.analysis_type,
            results=results,
            alerts=alerts,
            recommendations=recommendations,
            processed_locally=True,
            timestamp=datetime.utcnow(),
        )

        logger.info(
            f"Edge analysis completed: {analysis_id}, type: {request.analysis_type}, "
            f"online={disconnected_op.is_online}"
        )
        return response

    except Exception as e:
        logger.error(f"Edge analysis error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@app.post("/ml/infer", response_model=EdgeMLModelResponse)
async def edge_ml_inference(
    request: EdgeMLModelRequest, _: Dict[str, Any] = Depends(require_authentication)
):
    """Perform ML inference at edge using lightweight models"""
    try:
        # Load or use cached lightweight model
        if request.model_type not in edge_ml_models:
            # Initialize lightweight model (simplified version)
            edge_ml_models[request.model_type] = "loaded"

        # Simple edge inference (can be replaced with actual lightweight model)
        if request.model_type == "anomaly_detection":
            # Simple threshold-based anomaly detection
            values = list(request.features.values())
            mean = sum(values) / len(values) if values else 0
            std = (
                (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5
                if len(values) > 1
                else 1
            )

            anomaly_score = 0.0
            for value in values:
                if abs(value - mean) > 2 * std:
                    anomaly_score += 0.3

            anomaly_score = min(1.0, anomaly_score)
            anomaly_detected = anomaly_score > 0.5

        elif request.model_type == "threshold_check":
            # Simple threshold check
            anomaly_score = 0.0
            for value in request.features.values():
                if value > 100 or value < -100:
                    anomaly_score = 1.0
                    break
            anomaly_detected = anomaly_score > 0.5

        else:
            anomaly_score = 0.0
            anomaly_detected = False

        return EdgeMLModelResponse(
            sensor_id=request.sensor_id,
            prediction=anomaly_score,
            confidence=0.85 if anomaly_detected else 0.15,
            anomaly_detected=anomaly_detected,
            processed_locally=True,
            timestamp=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Edge ML inference error: {e}")
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


@app.post("/cache/thresholds")
async def cache_thresholds(
    thresholds: Dict[str, Dict[str, float]],
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Cache thresholds locally for edge processing"""
    edge_cache["thresholds"] = thresholds
    logger.info(f"Cached {len(thresholds)} sensor thresholds")
    return {"message": "Thresholds cached", "count": len(thresholds)}


@app.get("/cache/thresholds")
async def get_cached_thresholds(_: Dict[str, Any] = Depends(require_authentication)):
    """Get cached thresholds"""
    return {"thresholds": edge_cache.get("thresholds", {})}


@app.get("/health")
async def health():
    """Health check"""
    disconnected_status = disconnected_op.get_status()
    return {
        "status": "healthy",
        "service": "edge-computing",
        "cached_models": len(edge_ml_models),
        "cached_thresholds": len(edge_cache.get("thresholds", {})),
        "disconnected_operation": {
            "is_online": disconnected_status.get("is_online", True),
            "pending_alerts": disconnected_status.get("pending_alerts", 0),
            "pending_decisions": disconnected_status.get("pending_decisions", 0),
            "last_sync_time": disconnected_status.get("last_sync_time"),
            "storage_size_mb": disconnected_status.get("storage_size_mb", 0),
        },
    }


@app.get("/disconnected/status")
async def get_disconnected_status(_: Dict[str, Any] = Depends(require_authentication)):
    """Get disconnected operation status"""
    return disconnected_op.get_status()


@app.get("/disconnected/pending-alerts")
async def get_pending_alerts(
    limit: int = 100, _: Dict[str, Any] = Depends(require_authentication)
):
    """Get pending critical alerts"""
    return {
        "alerts": disconnected_op.get_pending_critical_alerts(limit=limit),
        "count": len(disconnected_op.get_pending_critical_alerts(limit=limit)),
    }


@app.get("/disconnected/pending-decisions")
async def get_pending_decisions(
    limit: int = 100, _: Dict[str, Any] = Depends(require_authentication)
):
    """Get pending local decisions"""
    return {
        "decisions": disconnected_op.get_pending_local_decisions(limit=limit),
        "count": len(disconnected_op.get_pending_local_decisions(limit=limit)),
    }


@app.post("/disconnected/sync")
async def trigger_sync(
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"}))
):
    """Manually trigger sync of pending data"""
    if not disconnected_op.is_online:
        raise HTTPException(status_code=503, detail="System is offline, cannot sync")

    disconnected_op._trigger_sync()
    return {
        "message": "Sync triggered",
        "pending_alerts": len(disconnected_op.get_pending_critical_alerts()),
        "pending_decisions": len(disconnected_op.get_pending_local_decisions()),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8009)
