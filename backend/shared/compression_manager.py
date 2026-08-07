"""
TimescaleDB Compression Policy Manager
مدیریت سیاست‌های فشرده‌سازی برای داده‌های قدیمی
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .config import settings
from .database import timescale_engine
from .sql_safety import validate_hypertable_name, validate_column_identifier

logger = logging.getLogger(__name__)


class CompressionManager:
    """
    Manages TimescaleDB compression policies
    مدیریت سیاست‌های فشرده‌سازی TimescaleDB
    """

    def __init__(self):
        self.compression_threshold_days = 90  # Compress data older than 90 days
        self.compression_segmentby = (
            "tag_id"  # Segment by tag_id for better compression
        )

    def enable_compression(
        self,
        table_name: str,
        segmentby_column: Optional[str] = None,
        orderby_column: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> bool:
        """
        Enable compression on a hypertable
        فعال‌سازی فشرده‌سازی روی hypertable
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                table_name = validate_hypertable_name(conn, table_name)
                segmentby = validate_column_identifier(
                    segmentby_column or self.compression_segmentby
                )
                orderby = validate_column_identifier(orderby_column or "timestamp DESC")

                query = f"""
                    ALTER TABLE {table_name} SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = '{segmentby}',
                        timescaledb.compress_orderby = '{orderby}'
                    );
                """

                conn.execute(text(query))
                conn.commit()

                logger.info(f"Compression enabled for {table_name}")
                return True
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to enable compression for {table_name}: {e}")
            return False

    def add_compression_policy(
        self,
        table_name: str,
        compress_after_days: int = 90,
        if_not_exists: bool = True,
        session: Optional[Session] = None,
    ) -> bool:
        """
        Add compression policy to compress chunks older than specified days
        اضافه کردن سیاست فشرده‌سازی برای chunks قدیمی‌تر از روزهای مشخص شده
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                table_name = validate_hypertable_name(conn, table_name)

                if if_not_exists:
                    # Check if policy already exists
                    check_query = f"""
                        SELECT COUNT(*) as count
                        FROM timescaledb_information.jobs
                        WHERE proc_name = 'policy_compression'
                        AND hypertable_name = '{table_name}';
                    """
                    result = conn.execute(text(check_query))
                    count = result.fetchone()[0]

                    if count > 0:
                        logger.info(
                            f"Compression policy already exists for {table_name}"
                        )
                        return True

                query = f"""
                    SELECT add_compression_policy(
                        '{table_name}',
                        INTERVAL '{compress_after_days} days',
                        if_not_exists => {str(if_not_exists).lower()}
                    );
                """

                conn.execute(text(query))
                conn.commit()

                logger.info(
                    f"Compression policy added for {table_name}: "
                    f"compress chunks older than {compress_after_days} days"
                )
                return True
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to add compression policy for {table_name}: {e}")
            return False

    def remove_compression_policy(
        self, table_name: str, session: Optional[Session] = None
    ) -> bool:
        """
        Remove compression policy from a hypertable
        حذف سیاست فشرده‌سازی از hypertable
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                table_name = validate_hypertable_name(conn, table_name)
                query = f"""
                    SELECT remove_compression_policy('{table_name}', if_exists => true);
                """

                conn.execute(text(query))
                conn.commit()

                logger.info(f"Compression policy removed for {table_name}")
                return True
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to remove compression policy for {table_name}: {e}")
            return False

    def get_compression_status(
        self, table_name: str, session: Optional[Session] = None
    ) -> Dict[str, any]:
        """
        Get compression status for a hypertable
        دریافت وضعیت فشرده‌سازی برای hypertable
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                table_name = validate_hypertable_name(conn, table_name)

                # Get compression settings
                settings_query = f"""
                    SELECT 
                        h.hypertable_name,
                        h.compression_enabled,
                        h.compression_status,
                        COUNT(DISTINCT c.chunk_name) as total_chunks,
                        COUNT(DISTINCT CASE WHEN c.is_compressed THEN c.chunk_name END) as compressed_chunks,
                        COUNT(DISTINCT CASE WHEN NOT c.is_compressed THEN c.chunk_name END) as uncompressed_chunks,
                        pg_size_pretty(SUM(c.total_bytes)) as total_size,
                        pg_size_pretty(SUM(CASE WHEN c.is_compressed THEN c.total_bytes ELSE 0 END)) as compressed_size,
                        pg_size_pretty(SUM(CASE WHEN NOT c.is_compressed THEN c.total_bytes ELSE 0 END)) as uncompressed_size
                    FROM timescaledb_information.hypertables h
                    LEFT JOIN timescaledb_information.chunks c 
                        ON h.hypertable_name = c.hypertable_name
                    WHERE h.hypertable_name = '{table_name}'
                    GROUP BY h.hypertable_name, h.compression_enabled, h.compression_status;
                """

                result = conn.execute(text(settings_query))
                row = result.fetchone()

                if not row:
                    return {"error": f"Hypertable {table_name} not found"}

                # Get compression policy
                policy_query = f"""
                    SELECT 
                        j.job_id,
                        j.proc_name,
                        j.scheduled,
                        j.config
                    FROM timescaledb_information.jobs j
                    WHERE j.proc_name = 'policy_compression'
                    AND j.hypertable_name = '{table_name}';
                """

                policy_result = conn.execute(text(policy_query))
                policy_row = policy_result.fetchone()

                status = {
                    "hypertable_name": row.hypertable_name,
                    "compression_enabled": row.compression_enabled,
                    "compression_status": row.compression_status,
                    "total_chunks": row.total_chunks or 0,
                    "compressed_chunks": row.compressed_chunks or 0,
                    "uncompressed_chunks": row.uncompressed_chunks or 0,
                    "total_size": row.total_size or "0 bytes",
                    "compressed_size": row.compressed_size or "0 bytes",
                    "uncompressed_size": row.uncompressed_size or "0 bytes",
                    "compression_ratio": None,
                    "policy": None,
                }

                # Calculate compression ratio
                if row.compressed_chunks and row.compressed_chunks > 0:
                    # Get actual sizes
                    size_query = f"""
                        SELECT 
                            pg_total_relation_size('{table_name}') as total_size,
                            pg_total_relation_size('{table_name}') FILTER (WHERE is_compressed = true) as compressed_size
                        FROM timescaledb_information.chunks
                        WHERE hypertable_name = '{table_name}';
                    """
                    # Simplified calculation
                    if row.uncompressed_size and row.compressed_size:
                        try:
                            uncompressed_bytes = self._parse_size(row.uncompressed_size)
                            compressed_bytes = self._parse_size(row.compressed_size)
                            if uncompressed_bytes > 0:
                                ratio = (
                                    1 - compressed_bytes / uncompressed_bytes
                                ) * 100
                                status["compression_ratio"] = f"{ratio:.1f}%"
                        except:
                            pass

                # Get policy info
                if policy_row:
                    status["policy"] = {
                        "job_id": policy_row.job_id,
                        "scheduled": policy_row.scheduled,
                        "config": policy_row.config,
                    }

                return status
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to get compression status for {table_name}: {e}")
            return {"error": str(e)}

    def _parse_size(self, size_str: str) -> int:
        """Parse size string to bytes"""
        size_str = size_str.strip().upper()
        if size_str.endswith("KB"):
            return int(float(size_str[:-2]) * 1024)
        elif size_str.endswith("MB"):
            return int(float(size_str[:-2]) * 1024 * 1024)
        elif size_str.endswith("GB"):
            return int(float(size_str[:-2]) * 1024 * 1024 * 1024)
        elif size_str.endswith("TB"):
            return int(float(size_str[:-2]) * 1024 * 1024 * 1024 * 1024)
        else:
            return int(float(size_str))

    def compress_chunks_manually(
        self,
        table_name: str,
        older_than_days: int = 90,
        session: Optional[Session] = None,
    ) -> Dict[str, any]:
        """
        Manually compress chunks older than specified days
        فشرده‌سازی دستی chunks قدیمی‌تر از روزهای مشخص شده
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                table_name = validate_hypertable_name(conn, table_name)
                cutoff_time = datetime.utcnow() - timedelta(days=older_than_days)

                # Find chunks to compress
                chunks_query = f"""
                    SELECT chunk_name, range_start, range_end
                    FROM timescaledb_information.chunks
                    WHERE hypertable_name = '{table_name}'
                    AND is_compressed = false
                    AND range_end < '{cutoff_time.isoformat()}'
                    ORDER BY range_start;
                """

                chunks_result = conn.execute(text(chunks_query))
                chunks = chunks_result.fetchall()

                compressed_count = 0
                failed_chunks = []

                for chunk in chunks:
                    try:
                        compress_query = f"""
                            SELECT compress_chunk('{chunk.chunk_name}');
                        """
                        conn.execute(text(compress_query))
                        conn.commit()
                        compressed_count += 1
                        logger.info(f"Compressed chunk: {chunk.chunk_name}")
                    except Exception as e:
                        logger.error(
                            f"Failed to compress chunk {chunk.chunk_name}: {e}"
                        )
                        failed_chunks.append(chunk.chunk_name)

                return {
                    "compressed_count": compressed_count,
                    "failed_chunks": failed_chunks,
                    "total_chunks": len(chunks),
                }
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to compress chunks manually: {e}")
            return {"error": str(e)}

    def get_chunk_statistics(
        self, table_name: str, session: Optional[Session] = None
    ) -> List[Dict[str, any]]:
        """
        Get detailed chunk statistics
        دریافت آمار تفصیلی chunks
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                table_name = validate_hypertable_name(conn, table_name)
                query = f"""
                    SELECT
                        chunk_name,
                        range_start,
                        range_end,
                        is_compressed,
                        pg_size_pretty(pg_total_relation_size(chunk_schema || '.' || chunk_name)) as size,
                        pg_total_relation_size(chunk_schema || '.' || chunk_name) as size_bytes
                    FROM timescaledb_information.chunks
                    WHERE hypertable_name = '{table_name}'
                    ORDER BY range_start DESC
                    LIMIT 100;
                """

                result = conn.execute(text(query))

                chunks = []
                for row in result:
                    chunks.append(
                        {
                            "chunk_name": row.chunk_name,
                            "range_start": row.range_start.isoformat()
                            if row.range_start
                            else None,
                            "range_end": row.range_end.isoformat()
                            if row.range_end
                            else None,
                            "is_compressed": row.is_compressed,
                            "size": row.size,
                            "size_bytes": row.size_bytes,
                        }
                    )

                return chunks
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to get chunk statistics: {e}")
            return []


# Global instance
compression_manager = CompressionManager()
