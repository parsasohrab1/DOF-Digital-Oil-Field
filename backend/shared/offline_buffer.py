"""
Offline Buffer Manager for Data Ingestion Resilience
Handles data buffering when network connection is unavailable
Supports both SQLite (legacy) and DuckDB (time-series optimized) storage
"""
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

from .duckdb_storage import DuckDBTimeSeriesStorage, DUCKDB_AVAILABLE

logger = logging.getLogger(__name__)


class OfflineBufferManager:
    """
    Manages offline data buffering using SQLite for persistence
    Optionally uses DuckDB for time-series data for faster recovery
    """

    def __init__(
        self,
        buffer_path: str = "./data/buffer",
        max_buffer_size: int = 100000,  # Maximum number of records
        max_buffer_size_mb: int = 500,  # Maximum buffer size in MB
        cleanup_interval: int = 3600,  # Cleanup interval in seconds
        use_duckdb: bool = True,  # Use DuckDB for time-series data
    ):
        self.buffer_path = Path(buffer_path)
        self.buffer_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.buffer_path / "offline_buffer.db"
        self.max_buffer_size = max_buffer_size
        self.max_buffer_size_mb = max_buffer_size_mb
        self.cleanup_interval = cleanup_interval
        self.use_duckdb = use_duckdb and DUCKDB_AVAILABLE
        self.lock = threading.RLock()

        # Initialize SQLite database (for metadata and non-time-series data)
        self._init_database()

        # Initialize DuckDB for time-series data if available
        self.duckdb_storage = None
        if self.use_duckdb:
            try:
                self.duckdb_storage = DuckDBTimeSeriesStorage(
                    db_path=str(self.buffer_path / "timeseries.duckdb"),
                    max_size_mb=max_buffer_size_mb,
                    enable_compression=True,
                )
                logger.info(
                    "DuckDB time-series storage enabled for faster data recovery"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to initialize DuckDB, falling back to SQLite: {e}"
                )
                self.use_duckdb = False

        # Start cleanup thread
        self._cleanup_thread = None
        self._running = True
        self._start_cleanup_thread()

        logger.info(
            f"OfflineBufferManager initialized at {self.db_path} (DuckDB: {self.use_duckdb})"
        )

    def _init_database(self):
        """Initialize SQLite database for buffering"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS buffered_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    data TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    last_retry REAL,
                    created_at REAL NOT NULL
                )
            """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON buffered_records (timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_source ON buffered_records (source)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_retry_count ON buffered_records (retry_count)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS buffer_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """
            )
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get thread-safe database connection"""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def add_record(
        self,
        record_id: str,
        source: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> bool:
        """
        Add a record to the buffer
        If DuckDB is enabled and data contains time-series metrics, stores in DuckDB for faster recovery

        Returns:
            True if added successfully, False if buffer is full
        """
        if timestamp is None:
            timestamp = time.time()

        # Check buffer size
        if not self._check_buffer_capacity():
            logger.warning("Buffer is full, cannot add more records")
            return False

        # If DuckDB is enabled and data looks like time-series data, use DuckDB
        if self.use_duckdb and self._is_time_series_data(data):
            return self._add_time_series_record(record_id, source, data, timestamp)

        # Otherwise use SQLite
        return self._add_to_sqlite(record_id, source, data, timestamp)

    def _is_time_series_data(self, data: Dict[str, Any]) -> bool:
        """Check if data looks like time-series sensor data"""
        # Check for common time-series fields
        time_series_indicators = [
            "sensor_id",
            "metric_name",
            "value",
            "pressure",
            "temperature",
            "flow_rate",
            "flowRate",
            "timestamp",
            "well_name",
        ]
        return any(key in data for key in time_series_indicators)

    def _add_time_series_record(
        self, record_id: str, source: str, data: Dict[str, Any], timestamp: float
    ) -> bool:
        """Add time-series record to DuckDB for faster recovery"""
        if not self.duckdb_storage:
            return self._add_to_sqlite(record_id, source, data, timestamp)

        try:
            # Extract sensor_id and metric_name from data
            sensor_id = data.get("sensor_id") or data.get("well_name") or source
            metric_name = data.get("metric_name") or data.get("metric") or "unknown"

            # Extract value (could be nested)
            value = data.get("value")
            if value is None:
                # Try common metric names
                for key in ["pressure", "temperature", "flow_rate", "flowRate"]:
                    if key in data:
                        value = data[key]
                        metric_name = key
                        break

            if value is None:
                # Fallback to SQLite if we can't extract time-series data
                return self._add_to_sqlite(record_id, source, data, timestamp)

            # Store in DuckDB
            success = self.duckdb_storage.insert_data_point(
                sensor_id=str(sensor_id),
                metric_name=str(metric_name),
                value=float(value),
                timestamp=timestamp,
                quality=data.get("quality", 100),
                metadata={
                    "record_id": record_id,
                    "source": source,
                    "original_data": data,
                },
            )

            # Also store metadata in SQLite for record tracking
            if success:
                try:
                    with self._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO buffered_records
                            (record_id, source, data, timestamp, created_at)
                            VALUES (?, ?, ?, ?, ?)
                        """,
                            (
                                record_id,
                                source,
                                json.dumps(
                                    {
                                        "storage": "duckdb",
                                        "sensor_id": sensor_id,
                                        "metric": metric_name,
                                    },
                                    default=str,
                                ),
                                timestamp,
                                time.time(),
                            ),
                        )
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to store metadata in SQLite: {e}")

            return success
        except Exception as e:
            logger.error(f"Failed to add time-series record to DuckDB: {e}")
            # Fallback to SQLite
            return self._add_to_sqlite(record_id, source, data, timestamp)

    def _add_to_sqlite(
        self, record_id: str, source: str, data: Dict[str, Any], timestamp: float
    ) -> bool:
        """Fallback method to add record to SQLite"""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO buffered_records
                        (record_id, source, data, timestamp, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (
                            record_id,
                            source,
                            json.dumps(data, default=str),
                            timestamp,
                            time.time(),
                        ),
                    )
                    conn.commit()

                logger.debug(f"Record buffered: {record_id} from {source}")
                return True
            except sqlite3.IntegrityError:
                # Record already exists, update it
                logger.debug(f"Record already exists, updating: {record_id}")
                return self._update_record(record_id, data, timestamp)
            except Exception as e:
                logger.error(f"Failed to buffer record {record_id}: {e}")
                return False

    def _update_record(
        self, record_id: str, data: Dict[str, Any], timestamp: float
    ) -> bool:
        """Update existing buffered record"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE buffered_records
                    SET data = ?, timestamp = ?
                    WHERE record_id = ?
                """,
                    (json.dumps(data, default=str), timestamp, record_id),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update record {record_id}: {e}")
            return False

    def get_pending_records(
        self, source: Optional[str] = None, limit: int = 1000, max_retries: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get pending records from buffer

        Args:
            source: Filter by source (optional)
            limit: Maximum number of records to return
            max_retries: Maximum retry count before skipping

        Returns:
            List of records with metadata
        """
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    if source:
                        cursor.execute(
                            """
                            SELECT * FROM buffered_records
                            WHERE source = ? AND retry_count < ?
                            ORDER BY timestamp ASC, created_at ASC
                            LIMIT ?
                        """,
                            (source, max_retries, limit),
                        )
                    else:
                        cursor.execute(
                            """
                            SELECT * FROM buffered_records
                            WHERE retry_count < ?
                            ORDER BY timestamp ASC, created_at ASC
                            LIMIT ?
                        """,
                            (max_retries, limit),
                        )

                    rows = cursor.fetchall()
                    records = []
                    for row in rows:
                        records.append(
                            {
                                "id": row["id"],
                                "record_id": row["record_id"],
                                "source": row["source"],
                                "data": json.loads(row["data"]),
                                "timestamp": row["timestamp"],
                                "retry_count": row["retry_count"],
                                "last_retry": row["last_retry"],
                                "created_at": row["created_at"],
                            }
                        )

                    return records
            except Exception as e:
                logger.error(f"Failed to get pending records: {e}")
                return []

    def mark_sent(self, record_id: str) -> bool:
        """Mark a record as successfully sent and remove from buffer"""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM buffered_records WHERE record_id = ?", (record_id,)
                    )
                    conn.commit()
                logger.debug(f"Record marked as sent and removed: {record_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to mark record as sent {record_id}: {e}")
                return False

    def mark_failed(self, record_id: str, increment_retry: bool = True) -> bool:
        """Mark a record as failed and increment retry count"""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    if increment_retry:
                        cursor.execute(
                            """
                            UPDATE buffered_records
                            SET retry_count = retry_count + 1,
                                last_retry = ?
                            WHERE record_id = ?
                        """,
                            (time.time(), record_id),
                        )
                    else:
                        cursor.execute(
                            """
                            UPDATE buffered_records
                            SET last_retry = ?
                            WHERE record_id = ?
                        """,
                            (time.time(), record_id),
                        )
                    conn.commit()
                logger.debug(f"Record marked as failed: {record_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to mark record as failed {record_id}: {e}")
                return False

    def get_buffer_stats(self) -> Dict[str, Any]:
        """Get buffer statistics including DuckDB stats if available"""
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()

                    # Total records in SQLite
                    cursor.execute("SELECT COUNT(*) as count FROM buffered_records")
                    total_sqlite = cursor.fetchone()["count"]

                    # By source
                    cursor.execute(
                        """
                        SELECT source, COUNT(*) as count
                        FROM buffered_records
                        GROUP BY source
                    """
                    )
                    by_source = {
                        row["source"]: row["count"] for row in cursor.fetchall()
                    }

                    # By retry count
                    cursor.execute(
                        """
                        SELECT retry_count, COUNT(*) as count
                        FROM buffered_records
                        GROUP BY retry_count
                    """
                    )
                    by_retry = {
                        row["retry_count"]: row["count"] for row in cursor.fetchall()
                    }

                    # Oldest record
                    cursor.execute(
                        """
                        SELECT MIN(created_at) as oldest
                        FROM buffered_records
                    """
                    )
                    oldest_row = cursor.fetchone()
                    oldest = (
                        oldest_row["oldest"]
                        if oldest_row and oldest_row["oldest"]
                        else None
                    )

                    # Buffer size
                    db_size = self.db_path.stat().st_size / (1024 * 1024)  # MB

                    stats = {
                        "total_records": total_sqlite,
                        "by_source": by_source,
                        "by_retry_count": by_retry,
                        "oldest_record_age_seconds": time.time() - oldest
                        if oldest
                        else None,
                        "buffer_size_mb": round(db_size, 2),
                        "max_buffer_size": self.max_buffer_size,
                        "max_buffer_size_mb": self.max_buffer_size_mb,
                        "buffer_usage_percent": round(
                            (total_sqlite / self.max_buffer_size) * 100, 2
                        )
                        if self.max_buffer_size > 0
                        else 0,
                        "duckdb_enabled": self.use_duckdb,
                    }

                    # Add DuckDB stats if available
                    if self.use_duckdb and self.duckdb_storage:
                        try:
                            duckdb_stats = self.duckdb_storage.get_storage_stats()
                            stats["duckdb"] = duckdb_stats
                            stats["total_records"] = total_sqlite + duckdb_stats.get(
                                "total_records", 0
                            )
                        except Exception as e:
                            logger.warning(f"Failed to get DuckDB stats: {e}")

                    return stats
            except Exception as e:
                logger.error(f"Failed to get buffer stats: {e}")
                return {}

    def _check_buffer_capacity(self) -> bool:
        """Check if buffer has capacity for new records"""
        stats = self.get_buffer_stats()

        # Check record count
        if stats.get("total_records", 0) >= self.max_buffer_size:
            return False

        # Check size
        if stats.get("buffer_size_mb", 0) >= self.max_buffer_size_mb:
            return False

        return True

    def cleanup_old_records(
        self, max_age_seconds: int = 86400 * 7, max_retries: int = 20  # 7 days
    ) -> int:
        """
        Clean up old records or records with too many retries

        Returns:
            Number of records cleaned up
        """
        with self.lock:
            try:
                cutoff_time = time.time() - max_age_seconds
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        DELETE FROM buffered_records
                        WHERE created_at < ? OR retry_count >= ?
                    """,
                        (cutoff_time, max_retries),
                    )
                    deleted = cursor.rowcount
                    conn.commit()

                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old records from buffer")

                return deleted
            except Exception as e:
                logger.error(f"Failed to cleanup old records: {e}")
                return 0

    def _start_cleanup_thread(self):
        """Start background thread for periodic cleanup"""

        def cleanup_worker():
            while self._running:
                time.sleep(self.cleanup_interval)
                if self._running:
                    self.cleanup_old_records()

        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        logger.info("Cleanup thread started")

    def clear_buffer(self, source: Optional[str] = None) -> int:
        """
        Clear all records from buffer (or for a specific source)

        Returns:
            Number of records deleted
        """
        with self.lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    if source:
                        cursor.execute(
                            "DELETE FROM buffered_records WHERE source = ?", (source,)
                        )
                    else:
                        cursor.execute("DELETE FROM buffered_records")
                    deleted = cursor.rowcount
                    conn.commit()

                logger.info(
                    f"Cleared {deleted} records from buffer"
                    + (f" for source {source}" if source else "")
                )
                return deleted
            except Exception as e:
                logger.error(f"Failed to clear buffer: {e}")
                return 0

    def shutdown(self):
        """Shutdown buffer manager and cleanup"""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        logger.info("OfflineBufferManager shut down")
