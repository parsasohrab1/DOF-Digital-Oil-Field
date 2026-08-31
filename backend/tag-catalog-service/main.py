"""
Tag Catalog Service
Central repository for well/tag metadata, units, and valid ranges
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import uvicorn
import sys
import os

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import get_db
from shared.models import Tag
from shared.config import settings
from shared.logging_config import setup_logging
from sqlalchemy.orm import Session
from shared.auth import require_authentication, require_roles
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing

# Role-based dependencies
require_tag_read = require_authentication
require_tag_write = require_roles({"system_admin", "data_engineer"})
require_tag_admin = require_roles({"system_admin"})

# Setup logging
logger = setup_logging("tag-catalog-service")

app = FastAPI(title="OGIM Tag Catalog Service", version="1.0.0")

setup_tracing(app, "tag-catalog-service")
setup_metrics(app, "tag-catalog-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TagMetadata(BaseModel):
    tag_id: str
    well_name: str
    equipment_type: str
    sensor_type: str
    unit: str
    valid_range_min: float
    valid_range_max: float
    critical_threshold_min: Optional[float] = None
    critical_threshold_max: Optional[float] = None
    warning_threshold_min: Optional[float] = None
    warning_threshold_max: Optional[float] = None
    description: Optional[str] = None
    location: Optional[str] = None
    status: str = "active"
    last_calibration: Optional[datetime] = None


class TagResponse(BaseModel):
    tag_id: str
    well_name: str
    equipment_type: str
    sensor_type: str
    unit: str
    valid_range_min: float
    valid_range_max: float
    critical_threshold_min: Optional[float] = None
    critical_threshold_max: Optional[float] = None
    warning_threshold_min: Optional[float] = None
    warning_threshold_max: Optional[float] = None
    description: Optional[str] = None
    location: Optional[str] = None
    status: str
    last_calibration: Optional[datetime] = None

    class Config:
        from_attributes = True


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Starting tag catalog service...")
    try:
        logger.info(
            "Tag catalog service ready. Ensure database migrations are applied."
        )
    except Exception as e:
        logger.error(f"Startup error: {e}")


@app.get("/tags")
async def list_tags(
    well_name: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_tag_read),
):
    """List all tags with optional filtering"""
    query = db.query(Tag)

    if well_name:
        query = query.filter(Tag.well_name == well_name)
    if status:
        query = query.filter(Tag.status == status)

    tags = query.all()
    return {
        "tags": [TagResponse.model_validate(tag).model_dump() for tag in tags],
        "count": len(tags),
    }


@app.get("/tags/{tag_id}")
async def get_tag(
    tag_id: str,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_tag_read),
):
    """Get tag metadata by ID"""
    tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return TagResponse.model_validate(tag)


@app.post("/tags", status_code=201)
async def create_tag(
    tag: TagMetadata,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_tag_write),
):
    """Create or update tag metadata"""
    # Check if tag exists
    existing_tag = db.query(Tag).filter(Tag.tag_id == tag.tag_id).first()

    if existing_tag:
        # Update existing tag
        for key, value in tag.dict(exclude_unset=True).items():
            setattr(existing_tag, key, value)
        db.commit()
        db.refresh(existing_tag)
        logger.info(f"Tag updated: {tag.tag_id}")
        return {"message": "Tag updated", "tag_id": tag.tag_id}
    else:
        # Create new tag
        db_tag = Tag(**tag.dict())
        db.add(db_tag)
        db.commit()
        db.refresh(db_tag)
        logger.info(f"Tag created: {tag.tag_id}")
        return {"message": "Tag created", "tag_id": tag.tag_id}


@app.put("/tags/{tag_id}")
async def update_tag(
    tag_id: str,
    tag: TagMetadata,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_tag_write),
):
    """Update tag metadata"""
    db_tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()
    if not db_tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    for key, value in tag.dict(exclude_unset=True).items():
        setattr(db_tag, key, value)

    db.commit()
    db.refresh(db_tag)
    logger.info(f"Tag updated: {tag_id}")
    return {"message": "Tag updated", "tag_id": tag_id}


@app.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: str,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_tag_admin),
):
    """Delete tag (soft delete by setting status)"""
    db_tag = db.query(Tag).filter(Tag.tag_id == tag_id).first()
    if not db_tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    db_tag.status = "deleted"
    db.commit()
    logger.info(f"Tag deleted: {tag_id}")
    return {"message": "Tag deleted", "tag_id": tag_id}


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Health check"""
    total_tags = db.query(Tag).count()
    return {"status": "healthy", "total_tags": total_tags}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8007)
