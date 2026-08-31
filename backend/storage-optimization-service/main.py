"""
Storage Optimization Service
مدیریت بهینه‌سازی ذخیره‌سازی: Compression, Partitioning, Retention
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException
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
from shared.database import get_timescale_db
from shared.compression_manager import compression_manager
from shared.timescale_cluster import cluster_manager
from shared.sql_safety import validate_hypertable_name, validate_interval_literal
from sqlalchemy.orm import Session
from sqlalchemy import text

# Setup logging
logger = setup_logging("storage-optimization-service")

app = FastAPI(title="OGIM Storage Optimization Service", version="1.0.0")
setup_metrics(app, "storage-optimization-service")
setup_tracing(app, "storage-optimization-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompressionPolicyRequest(BaseModel):
    """Compression policy request"""

    table_name: str
    compress_after_days: int = Field(default=90, ge=1, le=365)
    segmentby_column: Optional[str] = None
    orderby_column: Optional[str] = None


class RetentionPolicyRequest(BaseModel):
    """Retention policy request"""

    table_name: str
    drop_after_days: int = Field(default=365, ge=1)
    cascade: bool = False


class PartitioningConfig(BaseModel):
    """Partitioning configuration"""

    table_name: str
    chunk_time_interval: str = "1 day"
    number_partitions: Optional[int] = None
    partitioning_column: Optional[str] = None


class StorageStats(BaseModel):
    """Storage statistics"""

    table_name: str
    total_size: str
    compressed_size: str
    uncompressed_size: str
    compression_ratio: Optional[str]
    total_chunks: int
    compressed_chunks: int
    uncompressed_chunks: int
    oldest_chunk_date: Optional[str]
    newest_chunk_date: Optional[str]


@app.post("/compression/enable")
async def enable_compression(
    request: CompressionPolicyRequest,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Enable compression on a hypertable"""
    success = compression_manager.enable_compression(
        table_name=request.table_name,
        segmentby_column=request.segmentby_column,
        orderby_column=request.orderby_column,
        session=tsdb,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to enable compression")

    # Add compression policy
    policy_success = compression_manager.add_compression_policy(
        table_name=request.table_name,
        compress_after_days=request.compress_after_days,
        session=tsdb,
    )

    return {
        "status": "success",
        "message": f"Compression enabled for {request.table_name}",
        "compress_after_days": request.compress_after_days,
        "policy_added": policy_success,
    }


@app.get("/compression/status/{table_name}", response_model=StorageStats)
async def get_compression_status(
    table_name: str,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get compression status for a hypertable"""
    status = compression_manager.get_compression_status(table_name, session=tsdb)

    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])

    # Get chunk date range
    chunks = compression_manager.get_chunk_statistics(table_name, session=tsdb)
    oldest_date = None
    newest_date = None

    if chunks:
        dates = [c["range_start"] for c in chunks if c["range_start"]]
        if dates:
            oldest_date = min(dates)
            newest_date = max(dates)

    return StorageStats(
        table_name=status["hypertable_name"],
        total_size=status["total_size"],
        compressed_size=status["compressed_size"],
        uncompressed_size=status["uncompressed_size"],
        compression_ratio=status.get("compression_ratio"),
        total_chunks=status["total_chunks"],
        compressed_chunks=status["compressed_chunks"],
        uncompressed_chunks=status["uncompressed_chunks"],
        oldest_chunk_date=oldest_date,
        newest_chunk_date=newest_date,
    )


@app.post("/compression/compress-now")
async def compress_chunks_now(
    table_name: str,
    older_than_days: int = 90,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Manually compress chunks older than specified days"""
    result = compression_manager.compress_chunks_manually(
        table_name=table_name, older_than_days=older_than_days, session=tsdb
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@app.post("/retention/add")
async def add_retention_policy(
    request: RetentionPolicyRequest,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_roles({"system_admin"})),
):
    """Add retention policy to drop old chunks"""
    try:
        conn = tsdb.connection()
        table_name = validate_hypertable_name(conn, request.table_name)
        query = """
            SELECT add_retention_policy(
                :table_name,
                make_interval(days => :drop_after_days),
                if_not_exists => true
            );
        """
        conn.execute(
            text(query),
            {"table_name": table_name, "drop_after_days": request.drop_after_days},
        )
        conn.commit()

        return {
            "status": "success",
            "message": f"Retention policy added for {request.table_name}",
            "drop_after_days": request.drop_after_days,
        }
    except Exception as e:
        logger.error(f"Failed to add retention policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/partitioning/config/{table_name}")
async def get_partitioning_config(
    table_name: str,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get partitioning configuration for a hypertable"""
    try:
        conn = tsdb.connection()
        query = """
            SELECT
                hypertable_name,
                num_dimensions,
                num_chunks,
                compression_enabled,
                is_distributed
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = :table_name;
        """
        result = conn.execute(text(query), {"table_name": table_name})
        row = result.fetchone()

        if not row:
            raise HTTPException(
                status_code=404, detail=f"Hypertable {table_name} not found"
            )

        # Get chunk interval
        chunk_query = """
            SELECT
                d.dimension_type,
                d.time_interval,
                d.integer_interval
            FROM timescaledb_information.dimensions d
            WHERE d.hypertable_name = :table_name
            ORDER BY d.dimension_number;
        """
        chunk_result = conn.execute(text(chunk_query), {"table_name": table_name})
        dimensions = []
        for dim_row in chunk_result:
            dimensions.append(
                {
                    "type": dim_row.dimension_type,
                    "time_interval": (
                        str(dim_row.time_interval) if dim_row.time_interval else None
                    ),
                    "integer_interval": dim_row.integer_interval,
                }
            )

        return {
            "hypertable_name": row.hypertable_name,
            "num_dimensions": row.num_dimensions,
            "num_chunks": row.num_chunks,
            "compression_enabled": row.compression_enabled,
            "is_distributed": row.is_distributed,
            "dimensions": dimensions,
        }
    except Exception as e:
        logger.error(f"Failed to get partitioning config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/partitioning/optimize")
async def optimize_partitioning(
    config: PartitioningConfig,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Optimize partitioning configuration"""
    try:
        conn = tsdb.connection()

        # chunk_time_interval can't be bound as a plain parameter inside INTERVAL '...',
        # so it's checked against a strict allowlist pattern before interpolation.
        safe_interval = validate_interval_literal(config.chunk_time_interval)

        # Set chunk time interval
        query = f"""
            SELECT set_chunk_time_interval(:table_name, INTERVAL '{safe_interval}');
        """
        conn.execute(text(query), {"table_name": config.table_name})
        conn.commit()

        return {
            "status": "success",
            "message": f"Partitioning optimized for {config.table_name}",
            "chunk_time_interval": config.chunk_time_interval,
        }
    except Exception as e:
        logger.error(f"Failed to optimize partitioning: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chunks/{table_name}")
async def get_chunks(
    table_name: str,
    limit: int = 100,
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get chunk statistics for a hypertable"""
    chunks = compression_manager.get_chunk_statistics(table_name, session=tsdb)
    return {"chunks": chunks[:limit], "total": len(chunks)}


@app.get("/cluster/status")
async def get_cluster_status(
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get cluster status and statistics"""
    status = cluster_manager.get_cluster_status(session=tsdb)
    return status


@app.get("/storage/stats")
async def get_storage_stats(
    tsdb: Session = Depends(get_timescale_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get overall storage statistics"""
    try:
        conn = tsdb.connection()

        # Get all hypertables
        query = """
            SELECT hypertable_name
            FROM timescaledb_information.hypertables;
        """
        result = conn.execute(text(query))
        hypertables = [row.hypertable_name for row in result]

        stats = []
        for table_name in hypertables:
            status = compression_manager.get_compression_status(
                table_name, session=tsdb
            )
            if "error" not in status:
                stats.append(status)

        # Calculate totals
        total_chunks = sum(s.get("total_chunks", 0) for s in stats)
        compressed_chunks = sum(s.get("compressed_chunks", 0) for s in stats)

        return {
            "hypertables": stats,
            "summary": {
                "total_hypertables": len(stats),
                "total_chunks": total_chunks,
                "compressed_chunks": compressed_chunks,
                "compression_rate": (
                    (compressed_chunks / total_chunks * 100) if total_chunks > 0 else 0
                ),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "storage-optimization"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8014)
