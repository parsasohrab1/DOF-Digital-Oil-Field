"""
Digital Twin Service
Hosts engineering calculations, process simulations, and 3D BIM models
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Optional, List, Any
from datetime import datetime
import time
import random
import uvicorn
import sys
import os
import json

from prometheus_client import Counter, Histogram

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.logging_config import setup_logging  # type: ignore
from shared.metrics import setup_metrics  # type: ignore
from shared.tracing import setup_tracing  # type: ignore
from shared.config import settings
from shared.auth import require_authentication
from shared.database import get_timescale_db
from sqlalchemy.orm import Session

logger = setup_logging("digital-twin-service")
app = FastAPI(title="OGIM Digital Twin Service", version="1.0.0")
setup_metrics(app, "digital-twin-service")
setup_tracing(app, "digital-twin-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SIMULATION_RUNS = Counter(
    "digital_twin_simulations_total",
    "Number of simulations executed",
    ["simulation_type"],
)
SIMULATION_DURATION = Histogram(
    "digital_twin_simulation_duration_seconds",
    "Duration of simulation execution",
)


class SimulationRequest(BaseModel):
    well_name: str
    parameters: Dict[str, float]
    simulation_type: str  # production_optimization, pressure_analysis, etc.


class SimulationResponse(BaseModel):
    simulation_id: str
    well_name: str
    results: Dict[str, float]
    timestamp: datetime
    recommendations: Optional[list] = None


class BIM3DModel(BaseModel):
    """3D BIM Model representation"""

    model_id: str
    well_name: str
    equipment_id: str
    model_type: str  # "pump", "valve", "pipeline", "wellhead", etc.
    geometry: Dict[str, Any]  # 3D geometry data (vertices, faces, etc.)
    position: Dict[str, float]  # x, y, z coordinates
    rotation: Dict[str, float]  # rotation angles
    scale: Dict[str, float]  # scale factors
    metadata: Dict[str, Any]  # Additional metadata


class BIM3DState(BaseModel):
    """Real-time state of 3D BIM component"""

    model_id: str
    sensor_id: Optional[str] = None
    current_value: Optional[float] = None
    status: str  # "normal", "warning", "critical", "offline"
    color: str  # Color representation for visualization
    animation: Optional[str] = None  # Animation state
    timestamp: datetime


class BIM3DScene(BaseModel):
    """Complete 3D scene with all models and states"""

    scene_id: str
    well_name: str
    models: List[BIM3DModel]
    states: List[BIM3DState]
    camera_position: Optional[Dict[str, float]] = None
    timestamp: datetime


class WhatIfScenarioRequest(BaseModel):
    well_name: str
    base_conditions: Dict[str, float]
    adjustments: Dict[str, float]  # e.g. {"choke_pct": -10, "pump_speed_pct": +5}
    horizon_hours: int = 24


simulations_db = []
_well_3d_cache: Dict[str, Dict[str, Any]] = {}


@app.post("/simulate", response_model=SimulationResponse)
async def run_simulation(request: SimulationRequest):
    """Run engineering simulation"""
    start = time.perf_counter()
    simulation_id = f"SIM-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    results = {
        "optimal_flow_rate": 450.5,
        "predicted_pressure": 325.2,
        "efficiency": 0.92,
    }

    recommendations = [
        "Optimize pump speed to 85% for maximum efficiency",
        "Consider maintenance in next 30 days",
    ]

    simulation = SimulationResponse(
        simulation_id=simulation_id,
        well_name=request.well_name,
        results=results,
        timestamp=datetime.now(),
        recommendations=recommendations,
    )

    simulations_db.append(simulation.dict())
    duration = time.perf_counter() - start
    SIMULATION_RUNS.labels(simulation_type=request.simulation_type).inc()
    SIMULATION_DURATION.observe(duration)
    logger.info(
        "Simulation executed",
        extra={
            "simulation_id": simulation_id,
            "simulation_type": request.simulation_type,
            "duration": duration,
        },
    )
    return simulation


@app.get("/simulations")
async def list_simulations(well_name: Optional[str] = None):
    """List simulations"""
    filtered = simulations_db
    if well_name:
        filtered = [s for s in simulations_db if s.get("well_name") == well_name]
    return {"simulations": filtered, "count": len(filtered)}


# 3D BIM Endpoints
@app.post("/bim3d/models")
async def create_bim_model(
    model: BIM3DModel, _: Dict[str, Any] = Depends(require_authentication)
):
    """Create or update a 3D BIM model"""
    # In production, store in database
    # For now, return the model
    logger.info(f"Created 3D BIM model: {model.model_id} for {model.well_name}")
    return {"model_id": model.model_id, "status": "created"}


@app.get("/well/{well_name}/3d")
async def get_well_3d_data(
    well_name: str,
    db: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """
    Get well data for 3D visualization with depth-based sensor readings
    Returns data organized by depth segments for 3D rendering
    """
    from models import SensorData, Tag

    cache_ttl = max(1, settings.CACHE_TTL_SECONDS)
    cached = _well_3d_cache.get(well_name)
    now_ts = time.time()
    if cached and cached["expires_at"] > now_ts:
        return cached["data"]

    # Get all tags for this well
    tags = db.query(Tag).filter(Tag.well_name == well_name).all()

    if not tags:
        # Return mock data if no tags found
        total_depth = 3000  # meters
        num_segments = 20

        depth_data = []
        for i in range(num_segments):
            depth = (i / num_segments) * total_depth
            # Simulate pressure increase with depth
            pressure = 1000 + (depth / total_depth) * 2000 + random.uniform(-50, 50)
            # Simulate temperature increase with depth
            temperature = 25 + (depth / total_depth) * 100 + random.uniform(-5, 5)
            # Flow rate varies
            flow_rate = 100 + random.uniform(-20, 30)

            # Determine status based on values
            status = "normal"
            if pressure > 2800 or temperature > 110:
                status = "critical"
            elif pressure > 2500 or temperature > 95:
                status = "warning"

            depth_data.append(
                {
                    "depth": depth,
                    "pressure": round(pressure, 2),
                    "temperature": round(temperature, 1),
                    "flowRate": round(flow_rate, 2),
                    "status": status,
                }
            )

        # Get surface data from latest sensor readings
        surface_tags = [
            t
            for t in tags
            if "wellhead" in t.equipment_type.lower()
            or "surface" in t.equipment_type.lower()
        ]

        wellhead_pressure = 500.0
        wellhead_temperature = 30.0
        flow_rate = 150.0

        if surface_tags:
            for tag in surface_tags[:3]:  # Get first 3 surface sensors
                latest = (
                    db.query(SensorData)
                    .filter(SensorData.tag_id == tag.tag_id)
                    .order_by(SensorData.timestamp.desc())
                    .first()
                )

                if latest:
                    if "pressure" in tag.sensor_type.lower():
                        wellhead_pressure = latest.value
                    elif "temperature" in tag.sensor_type.lower():
                        wellhead_temperature = latest.value
                    elif "flow" in tag.sensor_type.lower():
                        flow_rate = latest.value

        result = {
            "wellName": well_name,
            "totalDepth": total_depth,
            "depthData": depth_data,
            "trajectory": {
                "md_points": [
                    {
                        "md": i * 150,
                        "inclination": round(5 + i * 0.8, 2),
                        "azimuth": round((i * 11) % 360, 2),
                    }
                    for i in range(20)
                ]
            },
            "riskZones": [
                {
                    "name": "High pressure zone",
                    "fromDepth": 2300,
                    "toDepth": 2800,
                    "severity": "warning",
                },
                {
                    "name": "Thermal hotspot",
                    "fromDepth": 2700,
                    "toDepth": 3000,
                    "severity": "critical",
                },
            ],
            "surfaceData": {
                "wellheadPressure": round(wellhead_pressure, 2),
                "wellheadTemperature": round(wellhead_temperature, 1),
                "flowRate": round(flow_rate, 2),
            },
        }
        _well_3d_cache[well_name] = {"expires_at": now_ts + cache_ttl, "data": result}
        return result

    # Calculate total depth from tags (assume max depth from location metadata)
    total_depth = 3000  # Default, could be from well metadata
    for tag in tags:
        if tag.location:
            # Try to extract depth from location
            try:
                if "depth" in tag.location.lower():
                    depth_str = tag.location.split("depth")[1].split()[0]
                    depth_val = float(depth_str)
                    total_depth = max(total_depth, depth_val)
            except (ValueError, IndexError):
                pass

    # Group sensors by depth ranges
    num_segments = 20
    segment_depth = total_depth / num_segments

    depth_data = []
    for i in range(num_segments):
        depth_start = i * segment_depth
        depth_end = (i + 1) * segment_depth
        depth_center = (depth_start + depth_end) / 2

        # Find sensors in this depth range
        segment_tags = []
        for tag in tags:
            tag_depth = 0
            if tag.location:
                try:
                    if "depth" in tag.location.lower():
                        depth_str = tag.location.split("depth")[1].split()[0]
                        tag_depth = float(depth_str)
                except (ValueError, IndexError):
                    pass

            if depth_start <= tag_depth < depth_end:
                segment_tags.append(tag)

        # Get average values for this segment
        pressures = []
        temperatures = []
        flow_rates = []

        for tag in segment_tags:
            latest = (
                db.query(SensorData)
                .filter(SensorData.tag_id == tag.tag_id)
                .order_by(SensorData.timestamp.desc())
                .first()
            )

            if latest:
                if "pressure" in tag.sensor_type.lower():
                    pressures.append(latest.value)
                elif "temperature" in tag.sensor_type.lower():
                    temperatures.append(latest.value)
                elif "flow" in tag.sensor_type.lower():
                    flow_rates.append(latest.value)

        # Calculate averages or use defaults
        pressure = (
            sum(pressures) / len(pressures)
            if pressures
            else 1000 + (depth_center / total_depth) * 2000
        )
        temperature = (
            sum(temperatures) / len(temperatures)
            if temperatures
            else 25 + (depth_center / total_depth) * 100
        )
        flow_rate = sum(flow_rates) / len(flow_rates) if flow_rates else 100

        # Determine status
        status = "normal"
        if pressure > 2800 or temperature > 110:
            status = "critical"
        elif pressure > 2500 or temperature > 95:
            status = "warning"

        depth_data.append(
            {
                "depth": round(depth_center, 1),
                "pressure": round(pressure, 2),
                "temperature": round(temperature, 1),
                "flowRate": round(flow_rate, 2),
                "status": status,
            }
        )

    # Get surface data
    surface_tags = [
        t
        for t in tags
        if "wellhead" in t.equipment_type.lower()
        or "surface" in t.equipment_type.lower()
    ]

    wellhead_pressure = 500.0
    wellhead_temperature = 30.0
    flow_rate = 150.0

    for tag in surface_tags[:3]:
        latest = (
            db.query(SensorData)
            .filter(SensorData.tag_id == tag.tag_id)
            .order_by(SensorData.timestamp.desc())
            .first()
        )

        if latest:
            if "pressure" in tag.sensor_type.lower():
                wellhead_pressure = latest.value
            elif "temperature" in tag.sensor_type.lower():
                wellhead_temperature = latest.value
            elif "flow" in tag.sensor_type.lower():
                flow_rate = latest.value

    result = {
        "wellName": well_name,
        "totalDepth": total_depth,
        "depthData": depth_data,
        "trajectory": {
            "md_points": [
                {
                    "md": i * 150,
                    "inclination": round(3 + i * 0.7, 2),
                    "azimuth": round((i * 9) % 360, 2),
                }
                for i in range(20)
            ]
        },
        "riskZones": [
            {
                "name": "Scale risk",
                "fromDepth": 1500,
                "toDepth": 1900,
                "severity": "warning",
            },
            {
                "name": "Gas breakthrough risk",
                "fromDepth": 2400,
                "toDepth": 2900,
                "severity": "critical",
            },
        ],
        "surfaceData": {
            "wellheadPressure": round(wellhead_pressure, 2),
            "wellheadTemperature": round(wellhead_temperature, 1),
            "flowRate": round(flow_rate, 2),
        },
    }
    _well_3d_cache[well_name] = {"expires_at": now_ts + cache_ttl, "data": result}
    return result


@app.get("/wells")
async def get_wells_list(
    db: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get list of all wells"""
    from models import Tag

    wells = db.query(Tag.well_name).distinct().all()
    well_list = (
        [w[0] for w in wells]
        if wells
        else ["PROD-001", "PROD-002", "INJ-001", "OBS-001"]
    )

    return {"wells": well_list}


@app.get("/bim3d/scene/{well_name}")
async def get_bim_scene(
    well_name: str,
    db: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get complete 3D BIM scene for a well with real-time states"""
    # Fetch latest sensor data
    from models import SensorData, Tag

    # Get all tags for this well
    tags = db.query(Tag).filter(Tag.well_name == well_name).all()

    # Build 3D models from equipment
    models = []
    states = []

    for tag in tags:
        # Create model for equipment
        model = BIM3DModel(
            model_id=f"{tag.equipment_type}-{tag.tag_id}",
            well_name=well_name,
            equipment_id=tag.equipment_type,
            model_type=tag.equipment_type.lower(),
            geometry={
                "type": tag.equipment_type,
                "vertices": [],  # Would be loaded from BIM file
                "faces": [],
            },
            position={"x": 0, "y": 0, "z": 0},  # Would be from BIM
            rotation={"x": 0, "y": 0, "z": 0},
            scale={"x": 1, "y": 1, "z": 1},
            metadata={
                "sensor_type": tag.sensor_type,
                "unit": tag.unit,
                "location": tag.location,
            },
        )
        models.append(model)

        # Get latest sensor reading
        latest_data = (
            db.query(SensorData)
            .filter(SensorData.tag_id == tag.tag_id)
            .order_by(SensorData.timestamp.desc())
            .first()
        )

        if latest_data:
            # Determine status and color
            value = latest_data.value
            status = "normal"
            color = "#00ff00"  # Green

            if tag.critical_threshold_max and value > tag.critical_threshold_max:
                status = "critical"
                color = "#ff0000"  # Red
            elif tag.warning_threshold_max and value > tag.warning_threshold_max:
                status = "warning"
                color = "#ffaa00"  # Orange
            elif tag.critical_threshold_min and value < tag.critical_threshold_min:
                status = "critical"
                color = "#ff0000"
            elif tag.warning_threshold_min and value < tag.warning_threshold_min:
                status = "warning"
                color = "#ffaa00"

            state = BIM3DState(
                model_id=model.model_id,
                sensor_id=tag.tag_id,
                current_value=value,
                status=status,
                color=color,
                animation="pulse" if status != "normal" else None,
                timestamp=latest_data.timestamp,
            )
            states.append(state)

    scene = BIM3DScene(
        scene_id=f"scene-{well_name}",
        well_name=well_name,
        models=models,
        states=states,
        camera_position={"x": 0, "y": 10, "z": 20},
        timestamp=datetime.utcnow(),
    )

    return scene


@app.get("/bim3d/model/{model_id}/state")
async def get_model_state(
    model_id: str,
    db: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get real-time state of a specific 3D model"""
    # Fetch latest state from sensor data
    from models import SensorData, Tag

    # Find tag by model_id (assuming model_id contains tag_id)
    tag = db.query(Tag).filter(Tag.tag_id.like(f"%{model_id}%")).first()

    if not tag:
        raise HTTPException(status_code=404, detail="Model not found")

    latest_data = (
        db.query(SensorData)
        .filter(SensorData.tag_id == tag.tag_id)
        .order_by(SensorData.timestamp.desc())
        .first()
    )

    if not latest_data:
        raise HTTPException(status_code=404, detail="No sensor data available")

    # Determine status
    value = latest_data.value
    status = "normal"
    color = "#00ff00"

    if tag.critical_threshold_max and value > tag.critical_threshold_max:
        status = "critical"
        color = "#ff0000"
    elif tag.warning_threshold_max and value > tag.warning_threshold_max:
        status = "warning"
        color = "#ffaa00"

    state = BIM3DState(
        model_id=model_id,
        sensor_id=tag.tag_id,
        current_value=value,
        status=status,
        color=color,
        animation="pulse" if status != "normal" else None,
        timestamp=latest_data.timestamp,
    )

    return state


@app.post("/what-if")
async def run_what_if_scenario(
    request: WhatIfScenarioRequest, _: Dict[str, Any] = Depends(require_authentication)
):
    """
    Run what-if scenario on top of current base conditions.
    Returns projected KPI deltas and risk summary.
    """
    base_flow = request.base_conditions.get("flow_rate", 800.0)
    base_pressure = request.base_conditions.get("pressure", 2400.0)
    base_temp = request.base_conditions.get("temperature", 85.0)

    choke_adj = request.adjustments.get("choke_pct", 0.0)
    pump_adj = request.adjustments.get("pump_speed_pct", 0.0)
    inj_adj = request.adjustments.get("injection_pct", 0.0)

    projected_flow = base_flow * (1 + (pump_adj * 0.006) - (choke_adj * 0.002))
    projected_pressure = base_pressure * (1 + (choke_adj * 0.003) + (inj_adj * 0.002))
    projected_temp = base_temp * (1 + (pump_adj * 0.0015))

    production_gain_pct = ((projected_flow - base_flow) / max(base_flow, 1.0)) * 100
    integrity_risk = "low"
    if projected_pressure > 2800 or projected_temp > 105:
        integrity_risk = "high"
    elif projected_pressure > 2550 or projected_temp > 95:
        integrity_risk = "medium"

    scenario_id = f"WIF-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    result = {
        "scenario_id": scenario_id,
        "well_name": request.well_name,
        "horizon_hours": request.horizon_hours,
        "base": {
            "flow_rate": round(base_flow, 2),
            "pressure": round(base_pressure, 2),
            "temperature": round(base_temp, 2),
        },
        "projected": {
            "flow_rate": round(projected_flow, 2),
            "pressure": round(projected_pressure, 2),
            "temperature": round(projected_temp, 2),
            "production_gain_pct": round(production_gain_pct, 2),
            "integrity_risk": integrity_risk,
        },
        "recommendations": [
            (
                "Reduce choke adjustment if integrity risk is medium/high."
                if integrity_risk != "low"
                else "Scenario is operationally acceptable."
            ),
            "Monitor pressure transient in first 2 hours after applying setpoints.",
        ],
        "timeline": [
            {
                "hour": h,
                "flow_rate": round(
                    projected_flow * (1 + random.uniform(-0.015, 0.015)), 2
                ),
                "pressure": round(
                    projected_pressure * (1 + random.uniform(-0.01, 0.01)), 2
                ),
                "temperature": round(
                    projected_temp * (1 + random.uniform(-0.008, 0.008)), 2
                ),
            }
            for h in range(0, max(1, request.horizon_hours) + 1, 2)
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }
    return result


@app.get("/ar/overlay/{well_name}")
async def get_ar_overlay_payload(
    well_name: str, _: Dict[str, Any] = Depends(require_authentication)
):
    """Provide AR-friendly overlay payload with prioritized assets and labels."""
    return {
        "well_name": well_name,
        "anchors": [
            {"id": "wellhead_anchor", "position": {"x": 0, "y": 0, "z": 0}},
            {"id": "tree_anchor", "position": {"x": 0.2, "y": 2.0, "z": 0}},
        ],
        "overlay_components": [
            {
                "component_id": "PUMP-001",
                "label": "Main Production Pump",
                "status": "normal",
                "kpis": {"pressure": 2480, "temperature": 84, "flowRate": 845},
                "priority": 1,
            },
            {
                "component_id": "VALVE-003",
                "label": "Master Valve",
                "status": "warning",
                "kpis": {"pressure": 2620},
                "priority": 2,
            },
        ],
        "recommended_view": {"distance_m": 2.5, "yaw_deg": 35, "pitch_deg": -5},
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "total_simulations": len(simulations_db)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8008)
