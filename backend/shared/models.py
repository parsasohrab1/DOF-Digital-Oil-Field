"""
Shared database models
"""
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Boolean,
    JSON,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class User(Base):
    """User model"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    disabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String(255), nullable=True)

    # Relationships
    alerts_acknowledged = relationship("Alert", back_populates="acknowledger")
    commands_requested = relationship(
        "Command", foreign_keys="[Command.requested_by_id]", back_populates="requester"
    )
    commands_approved = relationship(
        "Command", foreign_keys="[Command.approved_by_id]", back_populates="approver"
    )


class Tag(Base):
    """Tag/Sensor metadata"""

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    tag_id = Column(String(100), unique=True, nullable=False, index=True)
    well_name = Column(String(50), nullable=False, index=True)
    equipment_type = Column(String(50), nullable=False)
    sensor_type = Column(String(50), nullable=False, index=True)
    unit = Column(String(20), nullable=False)
    valid_range_min = Column(Float, nullable=False)
    valid_range_max = Column(Float, nullable=False)
    critical_threshold_min = Column(Float, nullable=True)
    critical_threshold_max = Column(Float, nullable=True)
    warning_threshold_min = Column(Float, nullable=True)
    warning_threshold_max = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    location = Column(String(100), nullable=True)
    status = Column(String(20), default="active", index=True)
    last_calibration = Column(DateTime, nullable=True)
    sampling_rate_ms = Column(Integer, default=1000)  # Sampling rate in milliseconds
    data_category = Column(
        String(50), nullable=True
    )  # pressure, temperature, flow, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sensor_data = relationship("SensorData", back_populates="tag")
    alerts = relationship("Alert", back_populates="tag")


class SensorData(Base):
    """Sensor data readings (for TimescaleDB)"""

    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    tag_id = Column(String(100), ForeignKey("tags.tag_id"), nullable=False, index=True)
    value = Column(Float, nullable=False)
    data_quality = Column(String(20), default="good")
    anomaly_flag = Column(Boolean, default=False)
    anomaly_score = Column(Float, nullable=True)

    # Relationships
    tag = relationship("Tag", back_populates="sensor_data")

    # Indexes for time-series queries
    __table_args__ = (Index("idx_sensor_data_timestamp_tag", "timestamp", "tag_id"),)


class Alert(Base):
    """Alert model"""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(50), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)  # critical, warning, info
    status = Column(
        String(20), nullable=False, index=True
    )  # open, acknowledged, resolved
    well_name = Column(String(50), nullable=False, index=True)
    tag_id = Column(String(100), ForeignKey("tags.tag_id"), nullable=True)
    message = Column(Text, nullable=False)
    rule_name = Column(String(100), nullable=False)
    acknowledged_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    erp_work_order_id = Column(
        String(100), nullable=True, index=True
    )  # Link to ERP work order
    equipment_id = Column(String(100), nullable=True)  # Equipment identifier
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tag = relationship("Tag", back_populates="alerts")
    acknowledger = relationship("User", back_populates="alerts_acknowledged")


class AlertRule(Base):
    """Alert rule configuration"""

    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    condition = Column(
        String(50), nullable=False
    )  # threshold_high, threshold_low, etc.
    threshold = Column(Float, nullable=True)
    severity = Column(String(20), nullable=False)
    enabled = Column(Boolean, default=True)
    configuration = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Command(Base):
    """Control command model"""

    __tablename__ = "commands"

    id = Column(Integer, primary_key=True, index=True)
    command_id = Column(String(50), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    well_name = Column(String(50), nullable=False, index=True)
    equipment_id = Column(String(100), nullable=False)
    command_type = Column(String(50), nullable=False)
    parameters = Column(JSON, nullable=False)
    status = Column(
        String(20), nullable=False, index=True
    )  # pending, approved, executing, executed, rejected, failed
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    executed_at = Column(DateTime, nullable=True)
    requires_two_factor = Column(Boolean, default=True)
    execution_result = Column(JSON, nullable=True)
    erp_work_order_id = Column(
        String(100), nullable=True, index=True
    )  # Link to ERP work order
    stage = Column(
        String(30), nullable=False, default="requested"
    )  # secure workflow stage, see CommandStage
    two_fa_verified_at = Column(DateTime, nullable=True)
    simulation_result = Column(JSON, nullable=True)
    approval_notes = Column(Text, nullable=True)
    critical = Column(
        Boolean, nullable=False, default=False
    )  # routes to low-latency Kafka topic
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    requester = relationship(
        "User", foreign_keys=[requested_by_id], back_populates="commands_requested"
    )
    approver = relationship(
        "User", foreign_keys=[approved_by_id], back_populates="commands_approved"
    )


class Report(Base):
    """Report model"""

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String(50), unique=True, nullable=False, index=True)
    report_type = Column(String(50), nullable=False)
    generated_at = Column(DateTime, nullable=False, index=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    well_name = Column(String(50), nullable=True, index=True)
    metrics = Column(JSON, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), default="completed")
    file_path = Column(String(255), nullable=True)


class Simulation(Base):
    """Digital twin simulation model"""

    __tablename__ = "simulations"

    id = Column(Integer, primary_key=True, index=True)
    simulation_id = Column(String(50), unique=True, nullable=False, index=True)
    well_name = Column(String(50), nullable=False, index=True)
    simulation_type = Column(String(50), nullable=False)
    parameters = Column(JSON, nullable=False)
    results = Column(JSON, nullable=False)
    recommendations = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="completed")


class AuditLog(Base):
    """Audit log for all critical operations"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False)  # success, failure
