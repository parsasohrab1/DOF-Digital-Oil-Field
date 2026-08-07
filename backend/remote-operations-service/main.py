"""
Remote Operations Service
Setpoint adjustments, Equipment start/stop, Valve control, Emergency shutdown

All operations other than emergency shutdown go through the secure command
workflow (2FA -> Digital Twin simulation -> two-person approval -> execution).
Approval is always mandatory for these; there is no client-supplied bypass.
"""
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Add backend directory to path
backend_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, backend_dir)

from shared.config import settings
from shared.logging_config import setup_logging
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from shared.auth import require_roles
from shared.database import get_db
from shared.models import Command, User, AuditLog
from sqlalchemy.orm import Session
from shared.secure_command_workflow import secure_command_workflow

# Setup logging
logger = setup_logging("remote-operations-service")

app = FastAPI(title="OGIM Remote Operations Service", version="1.0.0")
setup_metrics(app, "remote-operations-service")
setup_tracing(app, "remote-operations-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Role dependencies - mirrors command-control-service's convention
require_operator = require_roles({"system_admin", "field_operator", "operator"})
require_command_admin = require_roles({"system_admin"})


@app.on_event("startup")
async def startup_event():
    """Initialize Kafka producers used by the secure command workflow."""
    try:
        secure_command_workflow.init_producers()
        logger.info("Remote operations service ready.")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producers: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    secure_command_workflow.close_producers()


class OperationType(str, Enum):
    """Remote operation types"""

    SETPOINT_ADJUSTMENT = "setpoint_adjustment"
    EQUIPMENT_START = "equipment_start"
    EQUIPMENT_STOP = "equipment_stop"
    VALVE_OPEN = "valve_open"
    VALVE_CLOSE = "valve_close"
    VALVE_POSITION = "valve_position"
    EMERGENCY_SHUTDOWN = "emergency_shutdown"
    PUMP_SPEED = "pump_speed"
    COMPRESSOR_LOAD = "compressor_load"


class SetpointRequest(BaseModel):
    """Setpoint adjustment request"""

    well_name: str
    equipment_id: str
    parameter_name: str  # pressure, temperature, flow_rate, etc.
    target_value: float
    ramp_rate: Optional[float] = None  # Rate of change per second


class EquipmentControlRequest(BaseModel):
    """Equipment start/stop request"""

    well_name: str
    equipment_id: str
    equipment_type: str  # pump, compressor, motor, etc.
    operation: str  # start, stop, restart


class ValveControlRequest(BaseModel):
    """Valve control request"""

    well_name: str
    valve_id: str
    operation: str  # open, close, set_position
    position: Optional[float] = None  # 0.0 to 1.0 for set_position


class EmergencyShutdownRequest(BaseModel):
    """Emergency shutdown request"""

    well_name: Optional[str] = None  # None for site-wide shutdown
    equipment_id: Optional[str] = None
    shutdown_type: str = "immediate"  # immediate, controlled, partial
    reason: str


class TwoFactorRequest(BaseModel):
    """2FA verification for a pending command"""

    two_fa_code: str


class ApprovalRequest(BaseModel):
    """Simulation approval for a pending command"""

    approval_notes: Optional[str] = None


class OperationResponse(BaseModel):
    """Operation response"""

    operation_id: str
    operation_type: str
    status: str  # pending, approved, executing, executed, rejected, failed
    command_id: Optional[str] = None
    message: str
    timestamp: datetime


class OperationStatus(BaseModel):
    """Operation status"""

    operation_id: str
    status: str
    progress: float  # 0.0 to 1.0
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    estimated_completion: Optional[datetime] = None
    error_message: Optional[str] = None


def _get_requesting_user(db: Session, claims: Dict[str, Any]) -> User:
    username = claims.get("sub", "unknown")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _workflow_result_or_400(result: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/setpoint/adjust", response_model=OperationResponse)
async def adjust_setpoint(
    request: SetpointRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_operator),
):
    """Request a setpoint adjustment. Always requires 2FA + simulation + approval."""
    user = _get_requesting_user(db, claims)
    command_id = f"CMD-SETPOINT-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    await secure_command_workflow.initiate_command(
        db,
        command_id=command_id,
        command_type="setpoint_adjustment",
        parameters={
            "parameter_name": request.parameter_name,
            "target_value": request.target_value,
            "ramp_rate": request.ramp_rate,
        },
        requested_by_id=user.id,
        well_name=request.well_name,
        equipment_id=request.equipment_id,
    )

    return OperationResponse(
        operation_id=command_id,
        operation_type=OperationType.SETPOINT_ADJUSTMENT.value,
        status="pending",
        command_id=command_id,
        message="Setpoint adjustment requested. Two-factor authentication required.",
        timestamp=datetime.utcnow(),
    )


@app.post("/equipment/control", response_model=OperationResponse)
async def control_equipment(
    request: EquipmentControlRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_operator),
):
    """Request equipment start/stop. Always requires 2FA + simulation + approval."""
    user = _get_requesting_user(db, claims)
    command_id = f"CMD-EQ-{request.operation.upper()}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    await secure_command_workflow.initiate_command(
        db,
        command_id=command_id,
        command_type=f"equipment_{request.operation}",
        parameters={
            "equipment_type": request.equipment_type,
            "operation": request.operation,
        },
        requested_by_id=user.id,
        well_name=request.well_name,
        equipment_id=request.equipment_id,
    )

    return OperationResponse(
        operation_id=command_id,
        operation_type=f"equipment_{request.operation}",
        status="pending",
        command_id=command_id,
        message=f"Equipment {request.operation} requested. Two-factor authentication required.",
        timestamp=datetime.utcnow(),
    )


@app.post("/valve/control", response_model=OperationResponse)
async def control_valve(
    request: ValveControlRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_operator),
):
    """Request valve control. Always requires 2FA + simulation + approval."""
    user = _get_requesting_user(db, claims)
    command_id = f"CMD-VALVE-{request.operation.upper()}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    parameters = {"operation": request.operation}
    if request.position is not None:
        parameters["position"] = request.position

    await secure_command_workflow.initiate_command(
        db,
        command_id=command_id,
        command_type="valve_control",
        parameters=parameters,
        requested_by_id=user.id,
        well_name=request.well_name,
        equipment_id=request.valve_id,
    )

    return OperationResponse(
        operation_id=command_id,
        operation_type=f"valve_{request.operation}",
        status="pending",
        command_id=command_id,
        message=f"Valve {request.operation} requested. Two-factor authentication required.",
        timestamp=datetime.utcnow(),
    )


@app.post("/operations/{command_id}/verify-2fa")
async def verify_two_factor(
    command_id: str,
    request: TwoFactorRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_operator),
):
    """Verify the requester's 2FA code and automatically run the Digital Twin simulation."""
    user = _get_requesting_user(db, claims)
    try:
        result = await secure_command_workflow.verify_two_factor(
            db, command_id, request.two_fa_code, user
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _workflow_result_or_400(result)


@app.post("/operations/{command_id}/approve")
async def approve_operation(
    command_id: str,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_command_admin),
):
    """Approve a simulated command. Enforces the two-person rule (cannot approve your own request)."""
    approver = _get_requesting_user(db, claims)
    try:
        result = await secure_command_workflow.approve_simulation(
            db, command_id, approver, request.approval_notes
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _workflow_result_or_400(result)


@app.post("/operations/{command_id}/execute")
async def execute_operation(
    command_id: str,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_command_admin),
):
    """Execute an approved command by publishing it to Kafka for SCADA/PLC pickup."""
    executor = _get_requesting_user(db, claims)
    try:
        result = await secure_command_workflow.execute_command(db, command_id, executor)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _workflow_result_or_400(result)


@app.post("/emergency/shutdown", response_model=OperationResponse)
async def emergency_shutdown(
    request: EmergencyShutdownRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_roles({"system_admin", "field_operator"})),
):
    """
    Emergency shutdown procedure.

    Intentionally bypasses 2FA/simulation/approval - an emergency stop must be
    immediate. It still actually publishes to Kafka (unlike the previous stub)
    and is fully audited.
    """
    user = _get_requesting_user(db, claims)
    command_id = f"CMD-ESD-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    db_command = Command(
        command_id=command_id,
        timestamp=datetime.utcnow(),
        well_name=request.well_name or "SITE-WIDE",
        equipment_id=request.equipment_id or "ALL",
        command_type="emergency_shutdown",
        parameters={
            "shutdown_type": request.shutdown_type,
            "reason": request.reason,
        },
        status="pending",
        stage="requested",
        requested_by_id=user.id,
        requires_two_factor=False,
        critical=True,
    )
    db.add(db_command)
    db.commit()
    db.refresh(db_command)

    logger.critical(f"EMERGENCY SHUTDOWN INITIATED: {command_id} by {user.username}")

    result = await secure_command_workflow.execute_immediately(db, db_command, user)

    audit = AuditLog(
        timestamp=datetime.utcnow(),
        user_id=user.id,
        action="emergency_shutdown",
        resource_type="command",
        resource_id=command_id,
        details={
            "shutdown_type": request.shutdown_type,
            "reason": request.reason,
            "well_name": request.well_name,
            "equipment_id": request.equipment_id,
        },
        status="failed" if "error" in result else "success",
    )
    db.add(audit)
    db.commit()

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return OperationResponse(
        operation_id=command_id,
        operation_type=OperationType.EMERGENCY_SHUTDOWN.value,
        status=db_command.status,
        command_id=command_id,
        message=f"Emergency shutdown executed: {request.reason}",
        timestamp=datetime.utcnow(),
    )


@app.get("/operation/{operation_id}/status", response_model=OperationStatus)
async def get_operation_status(
    operation_id: str,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_operator),
):
    """Get status of a remote operation"""
    command = db.query(Command).filter(Command.command_id == operation_id).first()

    if not command:
        raise HTTPException(status_code=404, detail="Operation not found")

    progress_map = {
        "pending": 0.0,
        "approved": 0.6,
        "executing": 0.8,
        "executed": 1.0,
        "rejected": 0.0,
        "failed": 0.0,
    }

    progress = progress_map.get(command.status, 0.0)

    return OperationStatus(
        operation_id=operation_id,
        status=command.status,
        progress=progress,
        current_value=None,  # Would be fetched from equipment
        target_value=command.parameters.get("target_value")
        if isinstance(command.parameters, dict)
        else None,
        estimated_completion=None,
        error_message=None,
    )


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "remote-operations"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8012)
