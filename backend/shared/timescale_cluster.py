"""
TimescaleDB Multi-node Cluster Management
"""
import logging
from typing import List, Dict, Optional, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .config import settings
from .database import timescale_engine
from .sql_safety import (
    validate_hypertable_name,
    validate_column_identifier,
    validate_interval_literal,
)

logger = logging.getLogger(__name__)


class TimescaleClusterManager:
    """
    Manages TimescaleDB multi-node cluster operations
    """

    def __init__(self):
        self.access_nodes: List[str] = []
        self.data_nodes: List[str] = []

        if settings.TIMESCALE_MULTI_NODE_ENABLED:
            if settings.TIMESCALE_ACCESS_NODES:
                self.access_nodes = [
                    node.strip() for node in settings.TIMESCALE_ACCESS_NODES.split(",")
                ]
            if settings.TIMESCALE_DATA_NODES:
                self.data_nodes = [
                    node.strip() for node in settings.TIMESCALE_DATA_NODES.split(",")
                ]

    def add_data_node(
        self,
        node_host: str,
        node_port: int = 5432,
        database: str = "ogim_tsdb",
        user: str = "ogim_user",
        password: str = "ogim_password",
        session: Optional[Session] = None,
    ) -> bool:
        """
        Add a data node to the cluster

        Args:
            node_host: Hostname or IP of the data node
            node_port: Port number
            database: Database name
            user: Database user
            password: Database password
            session: Optional database session

        Returns:
            True if successful, False otherwise
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                # Add data node
                conn.execute(
                    text(
                        f"""
                    SELECT add_data_node(
                        '{node_host}',
                        host => '{node_host}',
                        port => {node_port},
                        database => '{database}',
                        user => '{user}',
                        password => '{password}'
                    );
                """
                    )
                )
                conn.commit()

                logger.info(f"Added data node: {node_host}:{node_port}")
                return True
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to add data node {node_host}:{node_port}: {e}")
            return False

    def remove_data_node(
        self, node_name: str, session: Optional[Session] = None
    ) -> bool:
        """
        Remove a data node from the cluster

        Args:
            node_name: Name of the data node
            session: Optional database session

        Returns:
            True if successful, False otherwise
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                conn.execute(
                    text(
                        f"""
                    SELECT delete_data_node('{node_name}', force => true);
                """
                    )
                )
                conn.commit()

                logger.info(f"Removed data node: {node_name}")
                return True
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to remove data node {node_name}: {e}")
            return False

    def list_data_nodes(
        self, session: Optional[Session] = None
    ) -> List[Dict[str, any]]:
        """
        List all data nodes in the cluster

        Args:
            session: Optional database session

        Returns:
            List of data node information
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                result = conn.execute(
                    text(
                        """
                    SELECT * FROM timescaledb_information.data_nodes;
                """
                    )
                )

                nodes = []
                for row in result:
                    nodes.append(
                        {
                            "node_name": row.node_name,
                            "host": row.host,
                            "port": row.port,
                            "database": row.database,
                            "node_created": row.node_created.isoformat()
                            if row.node_created
                            else None,
                            "database_created": row.database_created.isoformat()
                            if row.database_created
                            else None,
                        }
                    )

                return nodes
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to list data nodes: {e}")
            return []

    def create_distributed_hypertable(
        self,
        table_name: str,
        time_column: str = "timestamp",
        partitioning_column: Optional[str] = None,
        number_partitions: Optional[int] = None,
        chunk_time_interval: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> bool:
        """
        Create a distributed hypertable across data nodes

        Args:
            table_name: Name of the table
            time_column: Time column name
            partitioning_column: Optional partitioning column (for space partitioning)
            number_partitions: Number of partitions (defaults to config)
            chunk_time_interval: Chunk time interval (defaults to config)
            session: Optional database session

        Returns:
            True if successful, False otherwise
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                # table_name is not yet a hypertable at this point, so it can't be checked
                # against timescaledb_information.hypertables - validate as a bare identifier.
                table_name = validate_column_identifier(table_name)
                time_column = validate_column_identifier(time_column)
                if partitioning_column:
                    partitioning_column = validate_column_identifier(
                        partitioning_column
                    )
                num_partitions = (
                    number_partitions or settings.TIMESCALE_NUMBER_PARTITIONS
                )
                chunk_interval = validate_interval_literal(
                    chunk_time_interval or settings.TIMESCALE_CHUNK_TIME_INTERVAL
                )

                # Build create_distributed_hypertable query
                if partitioning_column:
                    query = f"""
                        SELECT create_distributed_hypertable(
                            '{table_name}',
                            '{time_column}',
                            partitioning_column => '{partitioning_column}',
                            number_partitions => {num_partitions},
                            chunk_time_interval => INTERVAL '{chunk_interval}',
                            if_not_exists => TRUE
                        );
                    """
                else:
                    query = f"""
                        SELECT create_distributed_hypertable(
                            '{table_name}',
                            '{time_column}',
                            number_partitions => {num_partitions},
                            chunk_time_interval => INTERVAL '{chunk_interval}',
                            if_not_exists => TRUE
                        );
                    """

                conn.execute(text(query))
                conn.commit()

                logger.info(f"Created distributed hypertable: {table_name}")
                return True
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to create distributed hypertable {table_name}: {e}")
            return False

    def get_cluster_status(self, session: Optional[Session] = None) -> Dict[str, any]:
        """
        Get cluster status and statistics

        Args:
            session: Optional database session

        Returns:
            Dictionary with cluster status information
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                status = {
                    "multi_node_enabled": settings.TIMESCALE_MULTI_NODE_ENABLED,
                    "access_nodes": self.access_nodes,
                    "data_nodes": [],
                    "hypertables": [],
                }

                # Get data nodes
                data_nodes = self.list_data_nodes(session=session if session else None)
                status["data_nodes"] = data_nodes

                # Get distributed hypertables
                result = conn.execute(
                    text(
                        """
                    SELECT * FROM timescaledb_information.hypertables
                    WHERE is_distributed = true;
                """
                    )
                )

                hypertables = []
                for row in result:
                    hypertables.append(
                        {
                            "hypertable_name": row.hypertable_name,
                            "num_dimensions": row.num_dimensions,
                            "num_chunks": row.num_chunks,
                            "compression_enabled": row.compression_enabled
                            if hasattr(row, "compression_enabled")
                            else False,
                        }
                    )

                status["hypertables"] = hypertables

                return status
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to get cluster status: {e}")
            return {"error": str(e)}

    def attach_data_node_to_hypertable(
        self,
        hypertable_name: str,
        data_node_name: str,
        session: Optional[Session] = None,
    ) -> bool:
        """
        Attach a data node to an existing hypertable

        Args:
            hypertable_name: Name of the hypertable
            data_node_name: Name of the data node
            session: Optional database session

        Returns:
            True if successful, False otherwise
        """
        try:
            if session:
                conn = session.connection()
            else:
                conn = timescale_engine.connect()

            try:
                hypertable_name = validate_hypertable_name(conn, hypertable_name)
                data_node_name = validate_column_identifier(data_node_name)
                conn.execute(
                    text(
                        f"""
                    SELECT attach_data_node('{data_node_name}', '{hypertable_name}');
                """
                    )
                )
                conn.commit()

                logger.info(
                    f"Attached data node {data_node_name} to hypertable {hypertable_name}"
                )
                return True
            finally:
                if not session:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to attach data node to hypertable: {e}")
            return False


# Global cluster manager instance
cluster_manager = TimescaleClusterManager()
