"""
Command & Control Service
Manages command queue, two-factor approval, and status feedback
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
from shared.models import Command, User, AuditLog
from shared.config import settings
from shared.logging_config import setup_logging
from shared.kafka_utils import (
    KafkaProducerWrapper,
    KAFKA_TOPICS,
    create_low_latency_producer,
)
from shared.auth import require_authentication, require_roles
from shared.secure_command_workflow import secure_command_workflow
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from sqlalchemy.orm import Session

# Setup logging
logger = setup_logging("command-control-service")

app = FastAPI(title="OGIM Command & Control Service", version="1.0.0")

setup_tracing(app, "command-control-service")
setup_metrics(app, "command-control-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Kafka producers - separate for critical and standard commands
command_producer = None
critical_command_producer = None


class CommandRequest(BaseModel):
    well_name: str
    equipment_id: str
    command_type: str  # setpoint, open_valve, close_valve, start_pump, stop_pump
    parameters: Dict
    requested_by: str
    requires_two_factor: bool = True
    critical: bool = False  # True for critical controls requiring millisecond latency


class CommandResponse(BaseModel):
    command_id: str
    timestamp: datetime
    well_name: str
    equipment_id: str
    command_type: str
    parameters: Dict[str, Any]
    status: str
    requested_by_id: int
    approved_by_id: Optional[int] = None
    executed_at: Optional[datetime] = None
    requires_two_factor: bool

    class Config:
        from_attributes = True


# Role dependencies
require_command_read = require_roles({"system_admin", "field_operator", "operator"})
require_command_admin = require_roles({"system_admin"})


@app.on_event("startup")
async def startup_event():
    """Initialize database and Kafka on startup"""
    global command_producer, critical_command_producer
    logger.info("Starting command control service...")
    try:
        # Standard producer for regular commands
        command_producer = KafkaProducerWrapper(KAFKA_TOPICS["CONTROL_COMMANDS"])
        # Low-latency producer for critical commands
        critical_command_producer = create_low_latency_producer(
            KAFKA_TOPICS["CRITICAL_CONTROL_COMMANDS"]
        )
        logger.info(
            "Command control service ready. Ensure database migrations are applied."
        )
    except Exception as e:
        logger.error(f"Failed to initialize command control service: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if command_producer:
        command_producer.close()
    if critical_command_producer:
        critical_command_producer.close()


@app.post("/commands")
async def create_command(
    request: CommandRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_command_read),
):
    """Create a control command"""
    # Get user
    user = db.query(User).filter(User.username == request.requested_by).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    requester_username = claims.get("sub")
    if requester_username != user.username:
        raise HTTPException(
            status_code=403, detail="Cannot create command for another user"
        )

    command_id = f"CMD-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{user.id}"

    # Create command
    db_command = Command(
        command_id=command_id,
        timestamp=datetime.utcnow(),
        well_name=request.well_name,
        equipment_id=request.equipment_id,
        command_type=request.command_type,
        parameters=request.parameters,
        status="pending",
        requested_by_id=user.id,
        requires_two_factor=request.requires_two_factor,
    )

    db.add(db_command)

    # Create audit log
    audit = AuditLog(
        timestamp=datetime.utcnow(),
        user_id=user.id,
        action="create_command",
        resource_type="command",
        resource_id=command_id,
        details=request.dict(),
        status="success",
    )
    db.add(audit)

    db.commit()
    db.refresh(db_command)

    logger.info(f"Command created: {command_id} by {request.requested_by}")

    return {"command_id": command_id, "status": "pending", "message": "Command queued"}


@app.post("/commands/{command_id}/approve")
async def approve_command(
    command_id: str,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_command_admin),
):
    """Approve a command (two-factor approval)"""
    # Get command
    command = db.query(Command).filter(Command.command_id == command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    if command.status != "pending":
        raise HTTPException(status_code=400, detail=f"Command already {command.status}")

    # Get approver
    username = claims.get("sub")
    approver = db.query(User).filter(User.username == username).first()
    if not approver:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if approver is different from requester (two-person rule)
    if command.requested_by_id == approver.id:
        raise HTTPException(
            status_code=400, detail="Cannot approve own command (two-person rule)"
        )

    # Update command
    command.status = "approved"
    command.approved_by_id = approver.id

    # Create audit log
    audit = AuditLog(
        timestamp=datetime.utcnow(),
        user_id=approver.id,
        action="approve_command",
        resource_type="command",
        resource_id=command_id,
        details={"approved_by": username},
        status="success",
    )
    db.add(audit)

    db.commit()

    logger.info(f"Command approved: {command_id} by {username}")

    return {"command_id": command_id, "status": "approved"}


@app.post("/commands/{command_id}/execute")
async def execute_command(
    command_id: str,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_command_admin),
):
    """Execute an approved command"""
    command = db.query(Command).filter(Command.command_id == command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    if command.status != "approved":
        raise HTTPException(
            status_code=400, detail="Command must be approved before execution"
        )

    # Update status
    command.status = "executing"
    db.commit()

    # Publish to Kafka for SCADA connector to execute
    try:
        command_data = {
            "command_id": command.command_id,
            "well_name": command.well_name,
            "equipment_id": command.equipment_id,
            "command_type": command.command_type,
            "parameters": command.parameters,
        }

        # Use low-latency producer for critical commands
        # Check if command is marked as critical (from request or stored in DB)
        is_critical = getattr(command, "critical", False)

        if is_critical and critical_command_producer:
            # Low-latency path: no flush, immediate send
            critical_command_producer.send(
                command_id, command_data, flush_immediately=False
            )
            logger.info(f"Critical command sent via low-latency channel: {command_id}")
        elif command_producer:
            # Standard path: flush for reliability
            command_producer.send(command_id, command_data)
            command_producer.flush()
        else:
            raise RuntimeError("No Kafka producer available")

    except Exception as e:
        logger.error(f"Failed to publish command to Kafka: {e}")
        command.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to execute command")

    # Mark as executed (in production, wait for SCADA confirmation)
    command.status = "executed"
    command.executed_at = datetime.utcnow()
    command.execution_result = {"status": "success", "message": "Command sent to SCADA"}

    # Create audit log
    audit = AuditLog(
        timestamp=datetime.utcnow(),
        user_id=command.approved_by_id,
        action="execute_command",
        resource_type="command",
        resource_id=command_id,
        details={"execution_time": command.executed_at.isoformat()},
        status="success",
    )
    db.add(audit)

    db.commit()

    logger.info(f"Command executed: {command_id}")

    return {"command_id": command_id, "status": "executed"}


@app.get("/commands")
async def list_commands(
    well_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_command_read),
):
    """List commands"""
    query = db.query(Command).order_by(Command.timestamp.desc())

    if well_name:
        query = query.filter(Command.well_name == well_name)
    if status:
        query = query.filter(Command.status == status)

    commands = query.limit(limit).all()
    return {
        "commands": [
            CommandResponse.model_validate(command).model_dump() for command in commands
        ],
        "count": len(commands),
    }


@app.get("/commands/{command_id}")
async def get_command(
    command_id: str,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_command_read),
):
    """Get command by ID"""
    command = db.query(Command).filter(Command.command_id == command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")
    return CommandResponse.model_validate(command)


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Health check"""
    pending = db.query(Command).filter(Command.status == "pending").count()
    return {"status": "healthy", "pending_commands": pending}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8006)
