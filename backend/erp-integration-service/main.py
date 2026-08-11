"""
ERP Integration Service
Integrates with enterprise systems (SAP, Oracle, etc.) for automated work orders
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.config import settings
from shared.logging_config import setup_logging
from shared.metrics import setup_metrics
from shared.tracing import setup_tracing
from shared.auth import require_authentication, require_roles
from shared.database import get_db
from shared.models import Alert, Command
from sqlalchemy.orm import Session

# Setup logging
logger = setup_logging("erp-integration-service")

app = FastAPI(title="OGIM ERP Integration Service", version="1.0.0")
setup_metrics(app, "erp-integration-service")
setup_tracing(app, "erp-integration-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ERP connectors
erp_connectors = {}


class WorkOrderRequest(BaseModel):
    """Work order creation request"""

    alert_id: Optional[str] = None
    command_id: Optional[str] = None
    equipment_id: str
    well_name: str
    issue_description: str
    priority: str = Field(default="medium", description="low, medium, high, critical")
    work_type: str = Field(
        ..., description="maintenance, repair, inspection, replacement"
    )
    estimated_duration: Optional[int] = None  # minutes
    required_skills: Optional[List[str]] = None
    parts_required: Optional[List[str]] = None


class WorkOrderResponse(BaseModel):
    """Work order response from ERP"""

    work_order_id: str
    erp_system: str
    status: str
    created_at: datetime
    erp_reference: Optional[str] = None
    message: Optional[str] = None


class ERPConnectionConfig(BaseModel):
    """ERP system connection configuration"""

    erp_type: str = Field(..., description="sap, oracle, maximo, etc.")
    base_url: str
    username: str
    password: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None
    additional_config: Optional[Dict[str, Any]] = None


class SAPConnector:
    """SAP ERP connector"""

    def __init__(self, config: ERPConnectionConfig):
        self.config = config
        self.base_url = config.base_url
        self.authenticated = False

    def authenticate(self) -> bool:
        """Authenticate with SAP system"""
        try:
            # In production, use SAP RFC or OData API
            # For now, mock authentication
            logger.info(f"Authenticating with SAP at {self.base_url}")
            self.authenticated = True
            return True
        except Exception as e:
            logger.error(f"SAP authentication failed: {e}")
            return False

    def create_work_order(self, work_order: WorkOrderRequest) -> WorkOrderResponse:
        """Create work order in SAP"""
        if not self.authenticated:
            if not self.authenticate():
                raise HTTPException(status_code=503, detail="SAP authentication failed")

        try:
            # In production, call SAP API (OData or RFC)
            # Example: POST /sap/opu/odata/sap/ZWORKORDER_SRV/WorkOrders

            work_order_id = f"SAP-WO-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Mock SAP response
            response = WorkOrderResponse(
                work_order_id=work_order_id,
                erp_system="SAP",
                status="created",
                created_at=datetime.utcnow(),
                erp_reference=f"WO{work_order_id}",
                message="Work order created successfully in SAP",
            )

            logger.info(
                f"Created SAP work order: {work_order_id} for {work_order.equipment_id}"
            )
            return response

        except Exception as e:
            logger.error(f"Failed to create SAP work order: {e}")
            raise HTTPException(
                status_code=500, detail=f"SAP work order creation failed: {str(e)}"
            )

    def get_work_order_status(self, work_order_id: str) -> Dict[str, Any]:
        """Get work order status from SAP"""
        # Mock implementation
        return {
            "work_order_id": work_order_id,
            "status": "in_progress",
            "assigned_to": "Maintenance Team A",
            "start_date": datetime.utcnow().isoformat(),
            "estimated_completion": (datetime.utcnow().replace(hour=18)).isoformat(),
        }


class OracleConnector:
    """Oracle ERP connector"""

    def __init__(self, config: ERPConnectionConfig):
        self.config = config
        self.base_url = config.base_url
        self.authenticated = False

    def authenticate(self) -> bool:
        """Authenticate with Oracle system"""
        try:
            logger.info(f"Authenticating with Oracle at {self.base_url}")
            self.authenticated = True
            return True
        except Exception as e:
            logger.error(f"Oracle authentication failed: {e}")
            return False

    def create_work_order(self, work_order: WorkOrderRequest) -> WorkOrderResponse:
        """Create work order in Oracle"""
        if not self.authenticated:
            if not self.authenticate():
                raise HTTPException(
                    status_code=503, detail="Oracle authentication failed"
                )

        work_order_id = f"ORACLE-WO-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        response = WorkOrderResponse(
            work_order_id=work_order_id,
            erp_system="Oracle",
            status="created",
            created_at=datetime.utcnow(),
            erp_reference=f"WO{work_order_id}",
            message="Work order created successfully in Oracle",
        )

        logger.info(f"Created Oracle work order: {work_order_id}")
        return response


def get_erp_connector(erp_type: str):
    """Get ERP connector instance"""
    if erp_type not in erp_connectors:
        raise HTTPException(
            status_code=404, detail=f"ERP connector not found: {erp_type}"
        )
    return erp_connectors[erp_type]


@app.post("/erp/connect")
async def connect_erp(
    config: ERPConnectionConfig,
    _: Dict[str, Any] = Depends(require_roles({"system_admin"})),
):
    """Connect to an ERP system"""
    try:
        if config.erp_type.lower() == "sap":
            connector = SAPConnector(config)
        elif config.erp_type.lower() == "oracle":
            connector = OracleConnector(config)
        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported ERP type: {config.erp_type}"
            )

        if connector.authenticate():
            erp_connectors[config.erp_type.lower()] = connector
            logger.info(f"Connected to {config.erp_type} ERP system")
            return {"status": "connected", "erp_type": config.erp_type}
        else:
            raise HTTPException(status_code=401, detail="ERP authentication failed")

    except Exception as e:
        logger.error(f"ERP connection error: {e}")
        raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")


@app.post("/work-orders", response_model=WorkOrderResponse)
async def create_work_order(
    request: WorkOrderRequest,
    erp_type: str = "sap",
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Create work order in ERP system"""
    try:
        connector = get_erp_connector(erp_type)
        response = connector.create_work_order(request)

        # Optionally link to alert or command
        if request.alert_id:
            alert = db.query(Alert).filter(Alert.alert_id == request.alert_id).first()
            if alert:
                alert.erp_work_order_id = response.work_order_id
                db.commit()

        if request.command_id:
            command = (
                db.query(Command)
                .filter(Command.command_id == request.command_id)
                .first()
            )
            if command:
                command.erp_work_order_id = response.work_order_id
                db.commit()

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Work order creation error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Work order creation failed: {str(e)}"
        )


@app.post("/work-orders/auto-create")
async def auto_create_work_order_from_alert(
    alert_id: str,
    erp_type: str = "sap",
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_roles({"system_admin", "data_engineer"})),
):
    """Automatically create work order from alert"""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Determine work type based on alert
    work_type = "inspection"
    if alert.severity == "critical":
        work_type = "repair"
    elif "maintenance" in alert.message.lower():
        work_type = "maintenance"

    # Create work order request
    work_order_request = WorkOrderRequest(
        alert_id=alert_id,
        equipment_id=alert.equipment_id or "unknown",
        well_name=alert.well_name,
        issue_description=alert.message,
        priority=alert.severity,
        work_type=work_type,
        estimated_duration=120 if alert.severity == "critical" else 60,
    )

    try:
        connector = get_erp_connector(erp_type)
        response = connector.create_work_order(work_order_request)

        # Link to alert
        alert.erp_work_order_id = response.work_order_id
        db.commit()

        logger.info(
            f"Auto-created work order {response.work_order_id} from alert {alert_id}"
        )
        return response

    except Exception as e:
        logger.error(f"Auto work order creation error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Auto work order creation failed: {str(e)}"
        )


@app.get("/work-orders/{work_order_id}/status")
async def get_work_order_status(
    work_order_id: str,
    erp_type: str = "sap",
    _: Dict[str, Any] = Depends(require_authentication),
):
    """Get work order status from ERP"""
    try:
        connector = get_erp_connector(erp_type)
        status = connector.get_work_order_status(work_order_id)
        return status
    except Exception as e:
        logger.error(f"Error getting work order status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get work order status: {str(e)}"
        )


@app.get("/erp/connections")
async def list_erp_connections(_: Dict[str, Any] = Depends(require_authentication)):
    """List connected ERP systems"""
    return {
        "connections": [
            {"erp_type": erp_type, "connected": True, "base_url": connector.base_url}
            for erp_type, connector in erp_connectors.items()
        ]
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "erp-integration",
        "connected_erp_systems": list(erp_connectors.keys()),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
