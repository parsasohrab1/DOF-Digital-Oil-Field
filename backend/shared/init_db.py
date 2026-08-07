#!/usr/bin/env python3
"""
Initialize database schema and create initial data
"""
import os
import sys
from sqlalchemy import text

# Add backend directory to path so `shared` can be imported as a package,
# regardless of whether this script is run directly or via `python -m`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import engine, timescale_engine, SessionLocal, Base
from shared.models import User, Tag, AlertRule
from shared.security import get_password_hash
from datetime import datetime


def create_hypertables():
    """Create TimescaleDB hypertables (single-node or distributed)"""
    from shared.config import settings
    from shared.timescale_cluster import cluster_manager

    with timescale_engine.connect() as conn:
        if settings.TIMESCALE_MULTI_NODE_ENABLED:
            # Create distributed hypertable
            print("Creating distributed hypertable for sensor_data...")
            try:
                success = cluster_manager.create_distributed_hypertable(
                    table_name="sensor_data",
                    time_column="timestamp",
                    partitioning_column="tag_id",  # Partition by tag_id for better distribution
                )
                if success:
                    print("✓ Created distributed hypertable for sensor_data")
                else:
                    raise Exception("Failed to create distributed hypertable")
            except Exception as e:
                print(f"⚠ Failed to create distributed hypertable: {e}")
                print("Trying regular hypertable as fallback...")
                # Fallback to regular hypertable
                chunk_interval = settings.TIMESCALE_CHUNK_TIME_INTERVAL
                conn.execute(
                    text(
                        f"""
                    SELECT create_hypertable(
                        'sensor_data', 
                        'timestamp',
                        chunk_time_interval => INTERVAL '{chunk_interval}',
                        if_not_exists => TRUE
                    );
                """
                    )
                )
                conn.commit()
                print(
                    f"✓ Created regular hypertable for sensor_data (chunk interval: {chunk_interval})"
                )
        else:
            # Create regular hypertable for single-node
            print("Creating hypertable for sensor_data (single-node)...")
            chunk_interval = settings.TIMESCALE_CHUNK_TIME_INTERVAL
            conn.execute(
                text(
                    f"""
                SELECT create_hypertable(
                    'sensor_data', 
                    'timestamp',
                    chunk_time_interval => INTERVAL '{chunk_interval}',
                    if_not_exists => TRUE
                );
            """
                )
            )
            conn.commit()
            print(
                f"✓ Created hypertable for sensor_data (chunk interval: {chunk_interval})"
            )

        # Optimize for high-volume writes (10GB/day)
        print("\nOptimizing hypertable for high-volume data ingestion...")
        try:
            # Set chunk interval to 1 day for 10GB/day
            conn.execute(
                text(
                    """
                SELECT set_chunk_time_interval('sensor_data', INTERVAL '1 day');
            """
                )
            )
            conn.commit()
            print("✓ Set chunk interval to 1 day")

            # Create additional indexes for better query performance
            conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_sensor_data_tag_timestamp 
                ON sensor_data (tag_id, timestamp DESC);
            """
                )
            )
            conn.commit()
            print("✓ Created optimized indexes")

            # Enable compression
            from shared.compression_manager import compression_manager

            print("\nSetting up compression policy...")
            if compression_manager.enable_compression(
                "sensor_data", segmentby_column="tag_id"
            ):
                print("✓ Compression enabled")

                # Add compression policy (compress data older than 90 days)
                if compression_manager.add_compression_policy(
                    "sensor_data", compress_after_days=90
                ):
                    print(
                        "✓ Compression policy added (compress chunks older than 90 days)"
                    )
                else:
                    print("⚠ Failed to add compression policy")
            else:
                print("⚠ Failed to enable compression")
        except Exception as e:
            print(f"⚠ Optimization warning: {e}")


def create_initial_users(db):
    """Create initial admin and test users"""
    users = [
        User(
            username="admin",
            email="admin@ogim.local",
            hashed_password=get_password_hash("Admin@123"),
            role="system_admin",
            disabled=False,
            two_factor_enabled=False,
        ),
        User(
            username="operator1",
            email="operator1@ogim.local",
            hashed_password=get_password_hash("Operator@123"),
            role="field_operator",
            disabled=False,
            two_factor_enabled=False,
        ),
        User(
            username="engineer1",
            email="engineer1@ogim.local",
            hashed_password=get_password_hash("Engineer@123"),
            role="data_engineer",
            disabled=False,
            two_factor_enabled=False,
        ),
        User(
            username="viewer1",
            email="viewer1@ogim.local",
            hashed_password=get_password_hash("Viewer@123"),
            role="viewer",
            disabled=False,
            two_factor_enabled=False,
        ),
    ]

    for user in users:
        existing = db.query(User).filter(User.username == user.username).first()
        if not existing:
            db.add(user)
            print(f"✓ Created user: {user.username}")

    db.commit()


def create_sample_alert_rules(db):
    """Create sample alert rules"""
    rules = [
        AlertRule(
            rule_id="rule-pressure-high",
            name="High Pressure Alert",
            description="Alert when pressure exceeds critical threshold",
            condition="threshold_high",
            threshold=450.0,
            severity="critical",
            enabled=True,
        ),
        AlertRule(
            rule_id="rule-temperature-high",
            name="High Temperature Alert",
            description="Alert when temperature exceeds warning threshold",
            condition="threshold_high",
            threshold=120.0,
            severity="warning",
            enabled=True,
        ),
        AlertRule(
            rule_id="rule-anomaly",
            name="Anomaly Detection",
            description="Alert on ML-detected anomalies",
            condition="anomaly",
            threshold=0.7,
            severity="warning",
            enabled=True,
        ),
    ]

    for rule in rules:
        existing = db.query(AlertRule).filter(AlertRule.rule_id == rule.rule_id).first()
        if not existing:
            db.add(rule)
            print(f"✓ Created alert rule: {rule.name}")

    db.commit()


def main():
    """Main initialization function"""
    print("=" * 60)
    print("Initializing OGIM Database")
    print("=" * 60)
    print()

    if os.getenv("ENVIRONMENT", "development") != "development":
        print(
            "Refusing to run init_db outside development environment.", file=sys.stderr
        )
        sys.exit(1)

    try:
        # Create all tables (development only)
        print("Creating tables (development use only)...")
        Base.metadata.create_all(bind=engine)
        Base.metadata.create_all(bind=timescale_engine)
        print("✓ Tables created")
        print()

        # Create hypertables in TimescaleDB
        print("Creating hypertables...")
        create_hypertables()
        print()

        # Create initial data
        print("Creating initial data...")
        db = SessionLocal()

        try:
            create_initial_users(db)
            create_sample_alert_rules(db)
            print()
            print("=" * 60)
            print("Database initialization completed successfully!")
            print("=" * 60)
            print()
            print("Default Users:")
            print("  - admin / Admin@123 (System Admin)")
            print("  - operator1 / Operator@123 (Field Operator)")
            print("  - engineer1 / Engineer@123 (Data Engineer)")
            print("  - viewer1 / Viewer@123 (Viewer)")
            print()
        finally:
            db.close()

    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
