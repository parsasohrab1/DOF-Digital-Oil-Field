"""
Shared database configuration and utilities
"""
from sqlalchemy import create_engine, pool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import os
import random
import logging
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

# Database URLs from environment variables
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://ogim_user:ogim_password@postgres:5432/ogim"
)

TIMESCALE_URL = os.getenv(
    "TIMESCALE_URL", "postgresql://ogim_user:ogim_password@timescaledb:5432/ogim_tsdb"
)

# Create engines
engine = create_engine(
    DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
    echo=False,
)


def get_timescale_connection_url() -> str:
    """
    Get TimescaleDB connection URL with load balancing for multi-node setup

    Returns:
        Connection URL (load balanced if multi-node enabled)
    """
    if settings.TIMESCALE_MULTI_NODE_ENABLED and settings.TIMESCALE_ACCESS_NODES:
        # Load balance across access nodes
        access_nodes = [
            node.strip() for node in settings.TIMESCALE_ACCESS_NODES.split(",")
        ]
        if access_nodes:
            # Random selection for load balancing
            selected_node = random.choice(access_nodes)
            # Parse original URL and replace host:port
            base_url = TIMESCALE_URL
            if "@" in base_url:
                parts = base_url.split("@")
                if len(parts) == 2:
                    auth_part = parts[0]
                    rest = parts[1]
                    # Replace host:port in rest part
                    if ":" in rest:
                        db_part = rest.split("/")[-1] if "/" in rest else rest
                        new_url = f"{auth_part}@{selected_node}/{db_part}"
                        logger.debug(f"Using TimescaleDB access node: {selected_node}")
                        return new_url

    return TIMESCALE_URL


# Create TimescaleDB engine with optimized pool settings
timescale_engine = create_engine(
    get_timescale_connection_url(),
    pool_size=settings.TIMESCALE_CONNECTION_POOL_SIZE,
    max_overflow=settings.TIMESCALE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.DATABASE_POOL_RECYCLE_SECONDS,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT_SECONDS,
    echo=False,
    # Optimize for high-volume writes
    connect_args={"connect_timeout": 10, "application_name": "ogim_timescale_client"},
)

# Create session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
TimescaleSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=timescale_engine
)

# Create base class for models
Base = declarative_base()


def get_db() -> Session:
    """Get database session for dependency injection"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_timescale_db() -> Session:
    """Get TimescaleDB session for dependency injection"""
    db = TimescaleSessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Get database session as context manager"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def init_timescale_db():
    """Initialize TimescaleDB tables"""
    Base.metadata.create_all(bind=timescale_engine)
