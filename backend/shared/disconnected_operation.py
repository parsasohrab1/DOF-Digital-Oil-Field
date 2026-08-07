"""
Disconnected Operation Manager for Edge Computing
مدیریت عملیات در حالت قطع ارتباط برای Edge Computing
"""
import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from contextlib import contextmanager
from collections import deque

from .connection_monitor import ConnectionMonitor
from .offline_buffer import OfflineBufferManager

logger = logging.getLogger(__name__)


class DisconnectedOperationManager:
    """
    Manages operations in disconnected mode for Edge Computing
    - Local data storage
    - Critical decision making
    - Sync when connection restored
    """

    def __init__(
        self,
        data_dir: str = "./data/edge",
        connection_monitor: Optional[ConnectionMonitor] = None,
        offline_buffer: Optional[OfflineBufferManager] = None,
        sync_interval: int = 60,  # Sync interval in seconds when online
        max_local_storage_mb: int = 1000,  # Max local storage in MB
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "edge_operations.db"
        self.sync_interval = sync_interval
        self.max_local_storage_mb = max_local_storage_mb

        # Initialize components
        self.connection_monitor = connection_monitor or ConnectionMonitor()
        self.offline_buffer = offline_buffer or OfflineBufferManager(
            buffer_path=str(self.data_dir / "buffer")
        )

        # Local storage for critical operations
        self._init_local_storage()

        # Sync status
        self.is_online = True
        self.last_sync_time = None
        self.pending_sync_count = 0
        self.sync_lock = threading.RLock()

        # Callbacks
        self.online_callbacks: List[Callable] = []
        self.offline_callbacks: List[Callable] = []

        # Start monitoring
        self.connection_monitor.add_callback(self._on_connection_change)
        self.connection_monitor.start_monitoring()

        # Start sync thread
        self._sync_thread = None
        self._running = True
        self._start_sync_thread()

        logger.info("DisconnectedOperationManager initialized")

    def _init_local_storage(self):
        """Initialize local SQLite database for edge operations"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Critical alerts table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS critical_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id TEXT UNIQUE NOT NULL,
                    sensor_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data TEXT,
                    timestamp REAL NOT NULL,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    synced BOOLEAN DEFAULT FALSE,
                    created_at REAL NOT NULL
                )
            """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON critical_alerts (timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_synced ON critical_alerts (synced)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sensor_id ON critical_alerts (sensor_id)"
            )

            # Local decisions table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS local_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id TEXT UNIQUE NOT NULL,
                    decision_type TEXT NOT NULL,
                    sensor_id TEXT,
                    action_taken TEXT,
                    reason TEXT,
                    data TEXT,
                    timestamp REAL NOT NULL,
                    synced BOOLEAN DEFAULT FALSE,
                    created_at REAL NOT NULL
                )
            """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON local_decisions (timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_decisions_synced ON local_decisions (synced)"
            )

            # Processed data cache
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_data_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT UNIQUE NOT NULL,
                    data TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    expires_at REAL,
                    created_at REAL NOT NULL
                )
            """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_expires ON processed_data_cache (expires_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_key_lookup ON processed_data_cache (cache_key)"
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

    def _on_connection_change(self, is_online: bool):
        """Handle connection status change"""
        previous_status = self.is_online
        self.is_online = is_online

        if is_online and not previous_status:
            logger.info("Connection restored - starting sync")
            self._trigger_sync()
            for callback in self.online_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Online callback error: {e}")
        elif not is_online and previous_status:
            logger.warning("Connection lost - entering disconnected mode")
            for callback in self.offline_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Offline callback error: {e}")

    def add_critical_alert(
        self,
        alert_id: str,
        sensor_id: str,
        alert_type: str,
        severity: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add critical alert (works in both online and offline modes)
        """
        timestamp = time.time()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO critical_alerts
                    (alert_id, sensor_id, alert_type, severity, message, data, 
                     timestamp, synced, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        alert_id,
                        sensor_id,
                        alert_type,
                        severity,
                        message,
                        json.dumps(data) if data else None,
                        timestamp,
                        False,  # Not synced yet
                        time.time(),
                    ),
                )
                conn.commit()

            logger.warning(f"Critical alert stored: {alert_id} - {message}")

            # Try to sync immediately if online
            if self.is_online:
                self._sync_critical_alerts()

            return True
        except Exception as e:
            logger.error(f"Failed to add critical alert: {e}")
            return False

    def record_local_decision(
        self,
        decision_id: str,
        decision_type: str,
        action_taken: str,
        reason: str,
        sensor_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Record a local decision made in disconnected mode
        """
        timestamp = time.time()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO local_decisions
                    (decision_id, decision_type, sensor_id, action_taken, reason,
                     data, timestamp, synced, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        decision_id,
                        decision_type,
                        sensor_id,
                        action_taken,
                        reason,
                        json.dumps(data) if data else None,
                        timestamp,
                        False,  # Not synced yet
                        time.time(),
                    ),
                )
                conn.commit()

            logger.info(f"Local decision recorded: {decision_id} - {action_taken}")

            # Try to sync if online
            if self.is_online:
                self._sync_local_decisions()

            return True
        except Exception as e:
            logger.error(f"Failed to record local decision: {e}")
            return False

    def cache_processed_data(
        self, cache_key: str, data: Dict[str, Any], ttl_seconds: int = 3600
    ) -> bool:
        """
        Cache processed data locally
        """
        timestamp = time.time()
        expires_at = timestamp + ttl_seconds

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO processed_data_cache
                    (cache_key, data, timestamp, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (cache_key, json.dumps(data), timestamp, expires_at, time.time()),
                )
                conn.commit()

            return True
        except Exception as e:
            logger.error(f"Failed to cache data: {e}")
            return False

    def get_cached_data(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached data if not expired"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT data, expires_at FROM processed_data_cache
                    WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > ?)
                """,
                    (cache_key, time.time()),
                )

                row = cursor.fetchone()
                if row:
                    return json.loads(row["data"])
        except Exception as e:
            logger.error(f"Failed to get cached data: {e}")

        return None

    def get_pending_critical_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending critical alerts that need to be synced"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM critical_alerts
                    WHERE synced = FALSE
                    ORDER BY timestamp ASC
                    LIMIT ?
                """,
                    (limit,),
                )

                alerts = []
                for row in cursor.fetchall():
                    alerts.append(
                        {
                            "alert_id": row["alert_id"],
                            "sensor_id": row["sensor_id"],
                            "alert_type": row["alert_type"],
                            "severity": row["severity"],
                            "message": row["message"],
                            "data": json.loads(row["data"]) if row["data"] else None,
                            "timestamp": row["timestamp"],
                            "acknowledged": bool(row["acknowledged"]),
                        }
                    )

                return alerts
        except Exception as e:
            logger.error(f"Failed to get pending alerts: {e}")
            return []

    def get_pending_local_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending local decisions that need to be synced"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM local_decisions
                    WHERE synced = FALSE
                    ORDER BY timestamp ASC
                    LIMIT ?
                """,
                    (limit,),
                )

                decisions = []
                for row in cursor.fetchall():
                    decisions.append(
                        {
                            "decision_id": row["decision_id"],
                            "decision_type": row["decision_type"],
                            "sensor_id": row["sensor_id"],
                            "action_taken": row["action_taken"],
                            "reason": row["reason"],
                            "data": json.loads(row["data"]) if row["data"] else None,
                            "timestamp": row["timestamp"],
                        }
                    )

                return decisions
        except Exception as e:
            logger.error(f"Failed to get pending decisions: {e}")
            return []

    def _sync_critical_alerts(self):
        """Sync critical alerts to central server"""
        if not self.is_online:
            return

        alerts = self.get_pending_critical_alerts(limit=50)
        if not alerts:
            return

        # TODO: Implement actual sync to central server
        # For now, just mark as synced
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                alert_ids = [a["alert_id"] for a in alerts]
                placeholders = ",".join("?" * len(alert_ids))
                cursor.execute(
                    f"""
                    UPDATE critical_alerts
                    SET synced = TRUE
                    WHERE alert_id IN ({placeholders})
                """,
                    alert_ids,
                )
                conn.commit()

            logger.info(f"Synced {len(alerts)} critical alerts")
        except Exception as e:
            logger.error(f"Failed to sync critical alerts: {e}")

    def _sync_local_decisions(self):
        """Sync local decisions to central server"""
        if not self.is_online:
            return

        decisions = self.get_pending_local_decisions(limit=50)
        if not decisions:
            return

        # TODO: Implement actual sync to central server
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                decision_ids = [d["decision_id"] for d in decisions]
                placeholders = ",".join("?" * len(decision_ids))
                cursor.execute(
                    f"""
                    UPDATE local_decisions
                    SET synced = TRUE
                    WHERE decision_id IN ({placeholders})
                """,
                    decision_ids,
                )
                conn.commit()

            logger.info(f"Synced {len(decisions)} local decisions")
        except Exception as e:
            logger.error(f"Failed to sync local decisions: {e}")

    def _trigger_sync(self):
        """Trigger immediate sync"""
        if self.is_online:
            self._sync_critical_alerts()
            self._sync_local_decisions()

    def _start_sync_thread(self):
        """Start background thread for periodic sync"""

        def sync_worker():
            while self._running:
                if self.is_online:
                    self._sync_critical_alerts()
                    self._sync_local_decisions()
                    self.last_sync_time = time.time()

                time.sleep(self.sync_interval)

        self._sync_thread = threading.Thread(target=sync_worker, daemon=True)
        self._sync_thread.start()
        logger.info("Sync thread started")

    def get_status(self) -> Dict[str, Any]:
        """Get disconnected operation status"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Count pending items
                cursor.execute(
                    "SELECT COUNT(*) as count FROM critical_alerts WHERE synced = FALSE"
                )
                pending_alerts = cursor.fetchone()["count"]

                cursor.execute(
                    "SELECT COUNT(*) as count FROM local_decisions WHERE synced = FALSE"
                )
                pending_decisions = cursor.fetchone()["count"]

                # Storage size
                db_size = self.db_path.stat().st_size / (1024 * 1024)  # MB

                return {
                    "is_online": self.is_online,
                    "last_sync_time": self.last_sync_time,
                    "pending_alerts": pending_alerts,
                    "pending_decisions": pending_decisions,
                    "storage_size_mb": round(db_size, 2),
                    "max_storage_mb": self.max_local_storage_mb,
                    "connection_status": self.connection_monitor.get_status(),
                }
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {"error": str(e)}

    def add_online_callback(self, callback: Callable):
        """Add callback for when connection is restored"""
        self.online_callbacks.append(callback)

    def add_offline_callback(self, callback: Callable):
        """Add callback for when connection is lost"""
        self.offline_callbacks.append(callback)

    def shutdown(self):
        """Shutdown manager"""
        self._running = False
        self.connection_monitor.stop_monitoring()
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
        logger.info("DisconnectedOperationManager shut down")


# Global instance
_disconnected_op_manager: Optional[DisconnectedOperationManager] = None


def get_disconnected_op_manager(**kwargs) -> DisconnectedOperationManager:
    """Get or create global disconnected operation manager"""
    global _disconnected_op_manager
    if _disconnected_op_manager is None:
        _disconnected_op_manager = DisconnectedOperationManager(**kwargs)
    return _disconnected_op_manager
