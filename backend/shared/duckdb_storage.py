"""
DuckDB-based Time-Series Storage for Edge Computing
Lightweight time-series database for offline resilience and fast data recovery
"""
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None

logger = logging.getLogger(__name__)


class DuckDBTimeSeriesStorage:
    """
    Lightweight time-series storage using DuckDB for edge devices
    Optimized for fast writes and time-range queries
    """

    def __init__(
        self,
        db_path: str = "./data/edge/timeseries.duckdb",
        max_size_mb: int = 1000,
        enable_compression: bool = True,
    ):
        if not DUCKDB_AVAILABLE:
            raise ImportError(
                "DuckDB is not available. Install it with: pip install duckdb"
            )

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_size_mb = max_size_mb
        self.enable_compression = enable_compression
        self.lock = threading.RLock()

        # Initialize database
        self._init_database()

        logger.info(f"DuckDBTimeSeriesStorage initialized at {self.db_path}")

    def _init_database(self):
        """Initialize DuckDB database with time-series optimized schema"""
        with self._get_connection() as conn:
            # Create time-series table with partitioning by time
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS time_series_data (
                    timestamp_us BIGINT NOT NULL,
                    sensor_id VARCHAR NOT NULL,
                    metric_name VARCHAR NOT NULL,
                    value DOUBLE NOT NULL,
                    quality INTEGER DEFAULT 100,
                    metadata VARCHAR,
                    PRIMARY KEY (timestamp_us, sensor_id, metric_name)
                )
            """
            )

            # Create index for fast time-range queries
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_time_sensor 
                ON time_series_data(timestamp_us, sensor_id)
            """
            )

            # Create index for metric queries
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_metric 
                ON time_series_data(metric_name, timestamp_us)
            """
            )

            # Create metadata table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_metadata (
                    key VARCHAR PRIMARY KEY,
                    value VARCHAR NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Enable compression if requested
            if self.enable_compression:
                conn.execute("PRAGMA enable_object_cache")

            logger.info("DuckDB time-series tables initialized")

    @contextmanager
    def _get_connection(self):
        """Get thread-safe DuckDB connection"""
        conn = duckdb.connect(str(self.db_path), read_only=False)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"DuckDB error: {e}")
            raise
        finally:
            conn.close()

    def insert_data_point(
        self,
        sensor_id: str,
        metric_name: str,
        value: float,
        timestamp: Optional[float] = None,
        quality: int = 100,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Insert a single time-series data point

        Args:
            sensor_id: Sensor identifier
            metric_name: Metric name (e.g., 'pressure', 'temperature')
            value: Metric value
            timestamp: Unix timestamp in seconds (default: current time)
            quality: Data quality score (0-100)
            metadata: Additional metadata as dictionary

        Returns:
            True if successful
        """
        if timestamp is None:
            timestamp = time.time()

        timestamp_us = int(timestamp * 1_000_000)  # Convert to microseconds

        metadata_str = json.dumps(metadata, default=str) if metadata else None

        with self.lock:
            try:
                with self._get_connection() as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO time_series_data
                        (timestamp_us, sensor_id, metric_name, value, quality, metadata)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            timestamp_us,
                            sensor_id,
                            metric_name,
                            value,
                            quality,
                            metadata_str,
                        ),
                    )

                return True
            except Exception as e:
                logger.error(f"Failed to insert data point: {e}")
                return False

    def insert_batch(self, data_points: List[Dict[str, Any]]) -> int:
        """
        Insert multiple data points in a single transaction

        Args:
            data_points: List of dicts with keys: sensor_id, metric_name, value,
                       timestamp (optional), quality (optional), metadata (optional)

        Returns:
            Number of successfully inserted points
        """
        if not data_points:
            return 0

        with self.lock:
            try:
                with self._get_connection() as conn:
                    inserted = 0
                    for point in data_points:
                        timestamp = point.get("timestamp", time.time())
                        timestamp_us = int(timestamp * 1_000_000)

                        metadata_str = (
                            json.dumps(point.get("metadata"), default=str)
                            if point.get("metadata")
                            else None
                        )

                        try:
                            conn.execute(
                                """
                                INSERT OR REPLACE INTO time_series_data
                                (timestamp_us, sensor_id, metric_name, value, quality, metadata)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """,
                                (
                                    timestamp_us,
                                    point["sensor_id"],
                                    point["metric_name"],
                                    point["value"],
                                    point.get("quality", 100),
                                    metadata_str,
                                ),
                            )
                            inserted += 1
                        except Exception as e:
                            logger.warning(f"Failed to insert point: {e}")
                            continue

                    return inserted
            except Exception as e:
                logger.error(f"Failed to insert batch: {e}")
                return 0

    def query_time_range(
        self,
        sensor_id: str,
        metric_name: str,
        start_time: float,
        end_time: float,
        aggregation: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query time-series data for a specific sensor and metric within time range

        Args:
            sensor_id: Sensor identifier
            metric_name: Metric name
            start_time: Start timestamp (Unix seconds)
            end_time: End timestamp (Unix seconds)
            aggregation: Optional aggregation ('avg', 'min', 'max', 'count', 'sum')

        Returns:
            List of data points or aggregated results
        """
        start_us = int(start_time * 1_000_000)
        end_us = int(end_time * 1_000_000)

        with self.lock:
            try:
                with self._get_connection() as conn:
                    if aggregation:
                        # Aggregated query
                        agg_func = aggregation.upper()
                        result = conn.execute(
                            """
                            SELECT 
                                {agg}(value) as value,
                                MIN(timestamp_us) as start_timestamp_us,
                                MAX(timestamp_us) as end_timestamp_us,
                                COUNT(*) as count
                            FROM time_series_data
                            WHERE sensor_id = ? 
                                AND metric_name = ?
                                AND timestamp_us >= ?
                                AND timestamp_us <= ?
                        """.format(
                                agg=agg_func
                            ),
                            (sensor_id, metric_name, start_us, end_us),
                        )

                        row = result.fetchone()
                        if row:
                            return [
                                {
                                    "sensor_id": sensor_id,
                                    "metric_name": metric_name,
                                    "value": row[0],
                                    "start_timestamp": row[1] / 1_000_000,
                                    "end_timestamp": row[2] / 1_000_000,
                                    "count": row[3],
                                    "aggregation": aggregation,
                                }
                            ]
                        return []
                    else:
                        # Raw data query
                        result = conn.execute(
                            """
                            SELECT timestamp_us, value, quality, metadata
                            FROM time_series_data
                            WHERE sensor_id = ? 
                                AND metric_name = ?
                                AND timestamp_us >= ?
                                AND timestamp_us <= ?
                            ORDER BY timestamp_us ASC
                        """,
                            (sensor_id, metric_name, start_us, end_us),
                        )

                        rows = result.fetchall()
                        return [
                            {
                                "timestamp": row[0] / 1_000_000,
                                "value": row[1],
                                "quality": row[2],
                                "metadata": json.loads(row[3]) if row[3] else None,
                            }
                            for row in rows
                        ]
            except Exception as e:
                logger.error(f"Failed to query time range: {e}")
                return []

    def query_latest(
        self, sensor_id: str, metric_name: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get latest data points for a sensor

        Args:
            sensor_id: Sensor identifier
            metric_name: Optional metric name filter
            limit: Maximum number of points to return

        Returns:
            List of latest data points
        """
        with self.lock:
            try:
                with self._get_connection() as conn:
                    if metric_name:
                        result = conn.execute(
                            """
                            SELECT timestamp_us, metric_name, value, quality, metadata
                            FROM time_series_data
                            WHERE sensor_id = ? AND metric_name = ?
                            ORDER BY timestamp_us DESC
                            LIMIT ?
                        """,
                            (sensor_id, metric_name, limit),
                        )
                    else:
                        result = conn.execute(
                            """
                            SELECT timestamp_us, metric_name, value, quality, metadata
                            FROM time_series_data
                            WHERE sensor_id = ?
                            ORDER BY timestamp_us DESC
                            LIMIT ?
                        """,
                            (sensor_id, limit),
                        )

                    rows = result.fetchall()
                    return [
                        {
                            "timestamp": row[0] / 1_000_000,
                            "metric_name": row[1],
                            "value": row[2],
                            "quality": row[3],
                            "metadata": json.loads(row[4]) if row[4] else None,
                        }
                        for row in rows
                    ]
            except Exception as e:
                logger.error(f"Failed to query latest: {e}")
                return []

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    # Total records
                    result = conn.execute(
                        "SELECT COUNT(*) as count FROM time_series_data"
                    )
                    total_records = result.fetchone()[0]

                    # Unique sensors
                    result = conn.execute(
                        "SELECT COUNT(DISTINCT sensor_id) FROM time_series_data"
                    )
                    unique_sensors = result.fetchone()[0]

                    # Unique metrics
                    result = conn.execute(
                        "SELECT COUNT(DISTINCT metric_name) FROM time_series_data"
                    )
                    unique_metrics = result.fetchone()[0]

                    # Time range
                    result = conn.execute(
                        """
                        SELECT MIN(timestamp_us), MAX(timestamp_us) 
                        FROM time_series_data
                    """
                    )
                    time_range = result.fetchone()
                    min_time = time_range[0] / 1_000_000 if time_range[0] else None
                    max_time = time_range[1] / 1_000_000 if time_range[1] else None

                    # Database size
                    db_size = self.db_path.stat().st_size / (1024 * 1024)  # MB

                    return {
                        "total_records": total_records,
                        "unique_sensors": unique_sensors,
                        "unique_metrics": unique_metrics,
                        "time_range": {
                            "start": min_time,
                            "end": max_time,
                            "duration_seconds": max_time - min_time
                            if (min_time and max_time)
                            else None,
                        },
                        "storage_size_mb": round(db_size, 2),
                        "max_size_mb": self.max_size_mb,
                        "usage_percent": round((db_size / self.max_size_mb) * 100, 2)
                        if self.max_size_mb > 0
                        else 0,
                    }
            except Exception as e:
                logger.error(f"Failed to get storage stats: {e}")
                return {}

    def cleanup_old_data(
        self,
        max_age_seconds: int = 86400 * 30,  # 30 days
        sensor_id: Optional[str] = None,
    ) -> int:
        """
        Clean up old time-series data

        Args:
            max_age_seconds: Maximum age of data to keep
            sensor_id: Optional sensor ID filter

        Returns:
            Number of records deleted
        """
        cutoff_time_us = int((time.time() - max_age_seconds) * 1_000_000)

        with self.lock:
            try:
                with self._get_connection() as conn:
                    if sensor_id:
                        result = conn.execute(
                            """
                            DELETE FROM time_series_data
                            WHERE timestamp_us < ? AND sensor_id = ?
                        """,
                            (cutoff_time_us, sensor_id),
                        )
                    else:
                        result = conn.execute(
                            """
                            DELETE FROM time_series_data
                            WHERE timestamp_us < ?
                        """,
                            (cutoff_time_us,),
                        )

                    deleted = result.rowcount
                    return deleted
            except Exception as e:
                logger.error(f"Failed to cleanup old data: {e}")
                return 0

    def export_to_parquet(
        self,
        output_path: str,
        sensor_id: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> bool:
        """
        Export time-series data to Parquet format for fast recovery

        Args:
            output_path: Output file path
            sensor_id: Optional sensor filter
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            True if successful
        """
        try:
            with self._get_connection() as conn:
                query = "SELECT * FROM time_series_data WHERE 1=1"
                params = []

                if sensor_id:
                    query += " AND sensor_id = ?"
                    params.append(sensor_id)

                if start_time:
                    query += " AND timestamp_us >= ?"
                    params.append(int(start_time * 1_000_000))

                if end_time:
                    query += " AND timestamp_us <= ?"
                    params.append(int(end_time * 1_000_000))

                conn.execute(
                    f"COPY ({query}) TO '{output_path}' (FORMAT PARQUET)", params
                )
                logger.info(f"Exported data to {output_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to export to Parquet: {e}")
            return False

    def import_from_parquet(self, input_path: str) -> int:
        """
        Import time-series data from Parquet format

        Args:
            input_path: Input Parquet file path

        Returns:
            Number of records imported
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute(
                    f"""
                    INSERT INTO time_series_data
                    SELECT * FROM read_parquet('{input_path}')
                """
                )
                imported = result.rowcount
                logger.info(f"Imported {imported} records from {input_path}")
                return imported
        except Exception as e:
            logger.error(f"Failed to import from Parquet: {e}")
            return 0
