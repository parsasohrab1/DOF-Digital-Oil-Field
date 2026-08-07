"""
Data Variables Service
Manages 65+ data variables with different sampling rates
"""
import os
import sys
from typing import List, Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Add backend directory to path
backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, backend_dir)

from shared.config import settings
from shared.logging_config import setup_logging
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from shared.auth import require_authentication
from shared.data_variables import (
    DATA_VARIABLES,
    get_variables_by_category,
    get_variables_by_sampling_rate,
    get_all_variables,
    get_variable_by_name,
    DataCategory,
)
from shared.database import get_timescale_db
from shared.models import SensorData
from sqlalchemy.orm import Session

# Setup logging
logger = setup_logging("data-variables-service")

app = FastAPI(title="OGIM Data Variables Service", version="1.0.0")
setup_metrics(app, "data-variables-service")
setup_tracing(app, "data-variables-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def get_all_variables_endpoint(_: dict = Depends(require_authentication)):
    """Get all data variables"""
    variables = get_all_variables()
    return [
        {
            "name": v.name,
            "category": v.category.value,
            "unit": v.unit,
            "sampling_rate_ms": v.sampling_rate_ms,
            "valid_range_min": v.valid_range_min,
            "valid_range_max": v.valid_range_max,
            "description": v.description,
            "equipment_location": v.equipment_location,
        }
        for v in variables
    ]


@app.get("/category/{category}")
async def get_variables_by_category_endpoint(
    category: str, _: dict = Depends(require_authentication)
):
    """Get variables by category"""
    try:
        data_category = DataCategory(category.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    variables = get_variables_by_category(data_category)
    return [
        {
            "name": v.name,
            "category": v.category.value,
            "unit": v.unit,
            "sampling_rate_ms": v.sampling_rate_ms,
            "valid_range_min": v.valid_range_min,
            "valid_range_max": v.valid_range_max,
            "description": v.description,
            "equipment_location": v.equipment_location,
        }
        for v in variables
    ]


@app.get("/sampling-rate/{rate_ms}")
async def get_variables_by_sampling_rate_endpoint(
    rate_ms: int, _: dict = Depends(require_authentication)
):
    """Get variables by sampling rate"""
    variables = get_variables_by_sampling_rate(rate_ms)
    return [
        {
            "name": v.name,
            "category": v.category.value,
            "unit": v.unit,
            "sampling_rate_ms": v.sampling_rate_ms,
            "valid_range_min": v.valid_range_min,
            "valid_range_max": v.valid_range_max,
            "description": v.description,
            "equipment_location": v.equipment_location,
        }
        for v in variables
    ]


@app.get("/{variable_name}/data")
async def get_variable_data(
    variable_name: str,
    limit: int = 100,
    tsdb: Session = Depends(get_timescale_db),
    _: dict = Depends(require_authentication),
):
    """Get real-time data for a variable"""
    # Find variable
    variable = get_variable_by_name(variable_name)
    if not variable:
        raise HTTPException(
            status_code=404, detail=f"Variable not found: {variable_name}"
        )

    # Get sensor data (assuming tag_id matches variable name)
    data = (
        tsdb.query(SensorData)
        .filter(SensorData.tag_id.like(f"%{variable_name}%"))
        .order_by(SensorData.timestamp.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "timestamp": d.timestamp.isoformat(),
            "value": d.value,
            "data_quality": d.data_quality,
        }
        for d in reversed(data)  # Reverse to show chronological order
    ]


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "data-variables",
        "total_variables": len(DATA_VARIABLES),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8013)
