"""
Alert Service
Manages alert rules, de-duplication, escalation, and silencing
"""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uvicorn
import sys
import os
import uuid

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.database import get_db
from shared.models import Alert, AlertRule, User
from shared.config import settings
from shared.logging_config import setup_logging
from shared.kafka_utils import KafkaProducerWrapper, KAFKA_TOPICS
from shared.auth import require_authentication, require_roles
from shared.tracing import setup_tracing
from shared.metrics import setup_metrics
from sqlalchemy.orm import Session
import httpx
import asyncio

# Setup logging
logger = setup_logging("alert-service")

app = FastAPI(title="OGIM Alert Service", version="1.0.0")

setup_tracing(app, "alert-service")
setup_metrics(app, "alert-service")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Kafka producer
alert_producer = None
ALERT_CORRELATION_WINDOW_MINUTES = int(os.getenv("ALERT_CORRELATION_WINDOW_MINUTES", "15"))
# Minimum number of distinct wells firing the same rule inside the correlation
# window before we suspect a shared/systemic cause (SCADA outage, weather,
# upstream equipment) rather than N independent well-local faults.
ALERT_CROSS_WELL_MIN_WELLS = int(os.getenv("ALERT_CROSS_WELL_MIN_WELLS", "3"))
ALERT_FATIGUE_COOLDOWN_SECONDS = {
    "critical": int(os.getenv("ALERT_FATIGUE_COOLDOWN_CRITICAL", "60")),
    "warning": int(os.getenv("ALERT_FATIGUE_COOLDOWN_WARNING", "180")),
    "info": int(os.getenv("ALERT_FATIGUE_COOLDOWN_INFO", "300")),
}
REGISTERED_PUSH_DEVICES: Dict[str, Dict[str, Any]] = {}
EXPO_PUSH_API_URL = "https://exp.host/--/api/v2/push/send"

from sms_notify import (  # noqa: E402
    register_sms_recipient,
    unregister_sms_recipient,
    list_sms_recipients,
    send_sms,
    notify_alert_via_sms,
    sms_provider_status,
    SMS_OUTBOX,
)



class AlertCreate(BaseModel):
    alert_id: str
    timestamp: datetime
    severity: str  # critical, warning, info
    status: str  # open, acknowledged, resolved
    well_name: str
    sensor_id: str
    message: str
    rule_name: str


class AlertResponse(BaseModel):
    alert_id: str
    timestamp: datetime
    severity: str
    status: str
    well_name: str
    tag_id: Optional[str] = None
    message: str
    rule_name: str
    acknowledged_by_id: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    metadata_json: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class AlertRuleCreate(BaseModel):
    rule_id: str
    name: str
    description: str
    condition: str
    threshold: float
    severity: str
    enabled: bool = True


class AlertRuleResponse(BaseModel):
    rule_id: str
    name: str
    description: Optional[str] = None
    condition: str
    threshold: Optional[float] = None
    severity: str
    enabled: bool

    class Config:
        from_attributes = True


class RCARequest(BaseModel):
    lookback_minutes: int = 60


class PushDeviceRegisterRequest(BaseModel):
    user_id: str
    platform: str
    device_token: str


class SmsRegisterRequest(BaseModel):
    phone: str
    label: Optional[str] = "اپراتور میدان"
    enabled: bool = True
    severities: Optional[List[str]] = None


class SmsTestRequest(BaseModel):
    phone: Optional[str] = None
    message: Optional[str] = None


def _severity_rank(severity: str) -> int:
    return {"critical": 3, "warning": 2, "info": 1}.get(severity.lower(), 0)


def _default_metadata() -> Dict[str, Any]:
    return {
        "correlation_id": None,
        "facility_correlation_id": None,
        "cross_well_signal": None,
        "first_seen_at": None,
        "last_seen_at": None,
        "occurrence_count": 0,
        "suppressed_count": 0,
        "fatigue": {"cooldown_s": 0, "last_notified_at": None},
        "rca": None,
    }


def _merge_metadata(existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = _default_metadata()
    if isinstance(existing, dict):
        merged.update(existing)
    return merged


def _should_suppress_for_fatigue(alert: AlertCreate, existing: Alert) -> bool:
    cooldown_s = ALERT_FATIGUE_COOLDOWN_SECONDS.get(alert.severity.lower(), 120)
    if existing.timestamp is None:
        return False
    age_seconds = (datetime.utcnow() - existing.timestamp).total_seconds()
    return age_seconds < cooldown_s


def _derive_correlation_key(alert: AlertCreate) -> str:
    sensor = (alert.sensor_id or "unknown").strip()
    well = (alert.well_name or "unknown").strip()
    rule = (alert.rule_name or "unknown").strip()
    return f"{well}:{rule}:{sensor}"


def _find_cross_well_candidates(
    db: Session, alert: Alert, window_minutes: int
) -> List[Alert]:
    """Find alerts firing the same rule on OTHER wells within the correlation window.

    Same-well correlation (`_derive_correlation_key` / `correlation_id`) only ever
    looks at `Alert.well_name == alert.well_name`, so a fault shared across the
    facility (a SCADA gateway outage, a weather event, a bad sensor batch) shows
    up as N unrelated per-well incidents instead of one systemic one. This looks
    across all wells for the same rule to surface that pattern.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    return (
        db.query(Alert)
        .filter(
            Alert.rule_name == alert.rule_name,
            Alert.timestamp >= cutoff,
        )
        .order_by(Alert.timestamp.desc())
        .limit(200)
        .all()
    )


def _infer_rca(
    candidates: List[Alert],
    cross_well_candidates: Optional[List[Alert]] = None,
) -> Dict[str, Any]:
    if not candidates:
        return {
            "suspected_root_cause": "insufficient_data",
            "confidence": 0.2,
            "reasoning": "Not enough related alerts to infer RCA.",
            "contributing_alerts": [],
            "scope": "well",
            "distinct_wells": 0,
        }

    by_rule: Dict[str, int] = {}
    by_sensor: Dict[str, int] = {}
    max_severity = "info"
    for a in candidates:
        by_rule[a.rule_name] = by_rule.get(a.rule_name, 0) + 1
        by_sensor[a.tag_id or "unknown"] = by_sensor.get(a.tag_id or "unknown", 0) + 1
        if _severity_rank(a.severity) > _severity_rank(max_severity):
            max_severity = a.severity

    top_rule = max(by_rule, key=by_rule.get)
    top_sensor = max(by_sensor, key=by_sensor.get)
    confidence = min(0.95, 0.4 + (by_rule[top_rule] / max(1, len(candidates))) * 0.5)

    well_local_result = {
        "suspected_root_cause": f"{top_rule}:{top_sensor}",
        "confidence": round(confidence, 2),
        "reasoning": (
            f"Dominant rule '{top_rule}' observed {by_rule[top_rule]} times with max severity '{max_severity}'."
        ),
        "contributing_alerts": [a.alert_id for a in candidates[:10]],
        "scope": "well",
        "distinct_wells": len({a.well_name for a in candidates}),
    }

    if not cross_well_candidates:
        return well_local_result

    distinct_wells = {a.well_name for a in cross_well_candidates}
    if len(distinct_wells) < ALERT_CROSS_WELL_MIN_WELLS:
        return well_local_result

    cross_max_severity = "info"
    for a in cross_well_candidates:
        if _severity_rank(a.severity) > _severity_rank(cross_max_severity):
            cross_max_severity = a.severity
    cross_confidence = min(0.95, 0.5 + (len(distinct_wells) / 20))
    rule_name = cross_well_candidates[0].rule_name
    return {
        "suspected_root_cause": f"systemic:{rule_name}",
        "confidence": round(cross_confidence, 2),
        "reasoning": (
            f"Rule '{rule_name}' fired across {len(distinct_wells)} distinct wells "
            f"within the correlation window (max severity '{cross_max_severity}'). "
            "This many independent wells sharing the same rule at the same time "
            "suggests a shared upstream cause (SCADA/network outage, weather event, "
            "sensor batch defect) rather than separate well-local faults."
        ),
        "contributing_alerts": [a.alert_id for a in cross_well_candidates[:10]],
        "scope": "facility",
        "distinct_wells": len(distinct_wells),
        "affected_wells": sorted(distinct_wells)[:20],
    }


async def _send_push_notification(
    title: str, body: str, data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    tokens = [item["device_token"] for item in REGISTERED_PUSH_DEVICES.values()]
    if not tokens:
        return {"sent": 0, "reason": "no_registered_devices"}

    messages = [
        {
            "to": token,
            "title": title,
            "body": body,
            "sound": "default",
            "data": data or {},
        }
        for token in tokens
    ]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(EXPO_PUSH_API_URL, json=messages)
            response.raise_for_status()
            payload = response.json()
            return {"sent": len(messages), "result": payload}
    except Exception as exc:
        logger.error("Push send failed: %s", exc)
        return {"sent": 0, "reason": str(exc)}


# Role dependencies
require_alert_read = require_authentication
require_alert_write = require_roles({"system_admin", "field_operator", "data_engineer"})
require_alert_admin = require_roles({"system_admin"})


@app.on_event("startup")
async def startup_event():
    """Initialize database and Kafka on startup"""
    global alert_producer
    logger.info("Starting alert service...")
    try:
        alert_producer = KafkaProducerWrapper(KAFKA_TOPICS["ALERTS"])
        logger.info("Alert service ready. Ensure database migrations are applied.")
    except Exception as e:
        logger.error(f"Failed to initialize alert service: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if alert_producer:
        alert_producer.close()


@app.post("/alerts", status_code=201)
async def create_alert(
    alert: AlertCreate,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_write),
):
    """Create a new alert"""
    # De-duplication + fatigue suppression: check if similar alert exists
    existing = (
        db.query(Alert)
        .filter(
            Alert.well_name == alert.well_name,
            Alert.rule_name == alert.rule_name,
            Alert.tag_id == alert.sensor_id,
            Alert.status == "open",
        )
        .order_by(Alert.timestamp.desc())
        .first()
    )

    if existing:
        existing_meta = _merge_metadata(existing.metadata_json)
        existing_meta["occurrence_count"] = (
            int(existing_meta.get("occurrence_count", 1)) + 1
        )
        existing_meta["last_seen_at"] = datetime.utcnow().isoformat()
        cooldown_s = ALERT_FATIGUE_COOLDOWN_SECONDS.get(alert.severity.lower(), 120)
        fatigue_meta = existing_meta.get("fatigue", {}) or {}
        fatigue_meta["cooldown_s"] = cooldown_s

        if _should_suppress_for_fatigue(alert, existing):
            existing_meta["suppressed_count"] = (
                int(existing_meta.get("suppressed_count", 0)) + 1
            )
            fatigue_meta["last_notified_at"] = (
                fatigue_meta.get("last_notified_at") or existing.timestamp.isoformat()
            )
            existing.metadata_json = existing_meta
            existing.timestamp = max(existing.timestamp, alert.timestamp)
            db.commit()
            logger.info(f"Alert fatigue suppression triggered: {alert.alert_id}")
            return {
                "message": "Alert suppressed by fatigue policy",
                "alert_id": existing.alert_id,
                "suppressed_count": existing_meta["suppressed_count"],
                "correlation_id": existing_meta.get("correlation_id"),
            }

        fatigue_meta["last_notified_at"] = datetime.utcnow().isoformat()
        existing_meta["fatigue"] = fatigue_meta
        existing.metadata_json = existing_meta
        existing.timestamp = max(existing.timestamp, alert.timestamp)
        db.commit()
        logger.info(f"Duplicate alert correlated: {alert.alert_id}")
        return {
            "message": "Duplicate alert correlated with existing open alert",
            "alert_id": existing.alert_id,
            "correlation_id": existing_meta.get("correlation_id"),
            "occurrence_count": existing_meta["occurrence_count"],
        }

    correlation_cutoff = datetime.utcnow() - timedelta(
        minutes=ALERT_CORRELATION_WINDOW_MINUTES
    )
    related = (
        db.query(Alert)
        .filter(
            Alert.well_name == alert.well_name, Alert.timestamp >= correlation_cutoff
        )
        .order_by(Alert.timestamp.desc())
        .limit(50)
        .all()
    )

    correlation_id = None
    for related_alert in related:
        meta = _merge_metadata(related_alert.metadata_json)
        rel_corr = meta.get("correlation_id")
        same_sensor = (related_alert.tag_id or "") == (alert.sensor_id or "")
        same_rule = related_alert.rule_name == alert.rule_name
        if rel_corr and (same_sensor or same_rule):
            correlation_id = rel_corr
            break
    if not correlation_id:
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}-{_derive_correlation_key(alert)}"

    # Cross-well correlation: the same rule firing on several other wells inside
    # the window suggests a shared/systemic cause rather than N unrelated
    # well-local faults. Kept as a separate facility_correlation_id so per-well
    # triage (correlation_id above) is unaffected.
    cross_well_related = _find_cross_well_candidates(db, alert, ALERT_CORRELATION_WINDOW_MINUTES)
    distinct_wells = {a.well_name for a in cross_well_related} | {alert.well_name}
    facility_correlation_id = None
    if len(distinct_wells) >= ALERT_CROSS_WELL_MIN_WELLS:
        for related_alert in cross_well_related:
            meta = _merge_metadata(related_alert.metadata_json)
            existing_facility_id = meta.get("facility_correlation_id")
            if existing_facility_id:
                facility_correlation_id = existing_facility_id
                break
        if not facility_correlation_id:
            facility_correlation_id = f"facility-{uuid.uuid4().hex[:12]}-{alert.rule_name}"
            # This alert is the one that crossed the threshold: backfill the
            # newly-minted id onto the earlier alerts that made up the signal,
            # so the cluster is visible as a whole and not just from here on.
            for related_alert in cross_well_related:
                related_meta = _merge_metadata(related_alert.metadata_json)
                if not related_meta.get("facility_correlation_id"):
                    related_meta["facility_correlation_id"] = facility_correlation_id
                    related_meta["cross_well_signal"] = {
                        "distinct_wells": len(distinct_wells),
                        "affected_wells": sorted(distinct_wells)[:20],
                    }
                    related_alert.metadata_json = related_meta

    # Create alert
    now_iso = datetime.utcnow().isoformat()
    metadata_json = _default_metadata()
    metadata_json.update(
        {
            "correlation_id": correlation_id,
            "facility_correlation_id": facility_correlation_id,
            "first_seen_at": now_iso,
            "last_seen_at": now_iso,
            "occurrence_count": 1,
            "suppressed_count": 0,
            "fatigue": {
                "cooldown_s": ALERT_FATIGUE_COOLDOWN_SECONDS.get(
                    alert.severity.lower(), 120
                ),
                "last_notified_at": now_iso,
            },
            "correlation_context": {
                "window_minutes": ALERT_CORRELATION_WINDOW_MINUTES,
                "related_alert_candidates": [a.alert_id for a in related[:10]],
            },
            "cross_well_signal": {
                "distinct_wells": len(distinct_wells),
                "affected_wells": sorted(distinct_wells)[:20],
            } if facility_correlation_id else None,
        }
    )

    db_alert = Alert(
        alert_id=alert.alert_id,
        timestamp=alert.timestamp,
        severity=alert.severity,
        status=alert.status,
        well_name=alert.well_name,
        tag_id=alert.sensor_id,
        message=alert.message,
        rule_name=alert.rule_name,
        metadata_json=metadata_json,
    )

    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)

    # Publish to Kafka
    try:
        if alert_producer:
            alert_producer.send(alert.alert_id, alert.dict())
    except Exception as e:
        logger.error(f"Failed to publish alert to Kafka: {e}")

    # Auto-create work order for critical alerts if enabled (background task)
    if alert.severity == "critical" and settings.ERP_AUTO_CREATE_WORK_ORDERS:
        async def create_work_order():
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{settings.ERP_SERVICE_URL}/work-orders/auto-create",
                        params={
                            "alert_id": alert.alert_id,
                            "erp_type": settings.ERP_DEFAULT_SYSTEM,
                        },
                        timeout=10.0,
                    )
                    if response.status_code == 200:
                        logger.info(
                            f"Auto-created work order for alert {alert.alert_id}"
                        )
            except Exception as e:
                logger.error(f"Failed to auto-create work order: {e}")

        # Run in background
        asyncio.create_task(create_work_order())

    # Push notification for critical alerts (best effort).
    if alert.severity == "critical":
        asyncio.create_task(
            _send_push_notification(
                title="Critical OGIM Alert",
                body=f"{alert.well_name}: {alert.message}",
                data={
                    "alert_id": alert.alert_id,
                    "severity": alert.severity,
                    "well_name": alert.well_name,
                },
            )
        )

    # SMS notification for configured severities (best effort).
    if settings.SMS_ENABLED:
        asyncio.create_task(
            notify_alert_via_sms(
                alert_id=alert.alert_id,
                well_name=alert.well_name,
                severity=alert.severity,
                message=alert.message,
            )
        )

    logger.info(f"Alert created: {alert.alert_id}")
    return {
        "alert_id": alert.alert_id,
        "message": "Alert created",
        "correlation_id": correlation_id,
    }


@app.get("/alerts")
async def list_alerts(
    well_name: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """List alerts with optional filtering"""
    query = db.query(Alert).order_by(Alert.timestamp.desc())

    if well_name:
        query = query.filter(Alert.well_name == well_name)
    if status:
        query = query.filter(Alert.status == status)
    if severity:
        query = query.filter(Alert.severity == severity)

    alerts = query.limit(limit).all()
    return {
        "alerts": [
            AlertResponse.model_validate(alert).model_dump() for alert in alerts
        ],
        "count": len(alerts),
    }


@app.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_alert_write),
):
    """Acknowledge an alert"""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Get user
    username = claims.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    alert.status = "acknowledged"
    alert.acknowledged_by_id = user.id
    alert.acknowledged_at = datetime.utcnow()

    db.commit()
    logger.info(f"Alert acknowledged: {alert_id} by {username}")

    return {"message": "Alert acknowledged", "alert_id": alert_id}


@app.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_admin),
):
    """Resolve an alert"""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "resolved"
    alert.resolved_at = datetime.utcnow()

    db.commit()
    logger.info(f"Alert resolved: {alert_id}")

    return {"message": "Alert resolved", "alert_id": alert_id}


@app.get("/alerts/correlations")
async def list_correlated_alerts(
    status: str = "open",
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """List correlated alert groups to support noise reduction and triage."""
    alerts = (
        db.query(Alert)
        .filter(Alert.status == status)
        .order_by(Alert.timestamp.desc())
        .limit(limit)
        .all()
    )
    groups: Dict[str, Dict[str, Any]] = {}
    for alert in alerts:
        meta = _merge_metadata(alert.metadata_json)
        correlation_id = meta.get("correlation_id") or f"uncorrelated:{alert.alert_id}"
        if correlation_id not in groups:
            groups[correlation_id] = {
                "correlation_id": correlation_id,
                "well_name": alert.well_name,
                "alerts": [],
                "count": 0,
                "max_severity": alert.severity,
                "suppressed_total": 0,
            }
        groups[correlation_id]["alerts"].append(alert.alert_id)
        groups[correlation_id]["count"] += 1
        groups[correlation_id]["suppressed_total"] += int(
            meta.get("suppressed_count", 0)
        )
        if _severity_rank(alert.severity) > _severity_rank(
            groups[correlation_id]["max_severity"]
        ):
            groups[correlation_id]["max_severity"] = alert.severity

    grouped = sorted(
        groups.values(),
        key=lambda x: (x["count"], _severity_rank(x["max_severity"])),
        reverse=True,
    )
    return {"groups": grouped, "count": len(grouped)}


@app.get("/alerts/correlations/facility")
async def list_facility_correlated_alerts(
    status: str = "open",
    limit: int = 200,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """List cross-well alert clusters that share a facility_correlation_id.

    Complements /alerts/correlations (which groups by well-scoped
    correlation_id) by surfacing incidents where the same rule fired across
    several wells at once — a signal of a shared/systemic cause rather than
    independent well-local faults.
    """
    alerts = db.query(Alert).filter(Alert.status == status).order_by(Alert.timestamp.desc()).limit(limit).all()
    groups: Dict[str, Dict[str, Any]] = {}
    for alert in alerts:
        meta = _merge_metadata(alert.metadata_json)
        facility_id = meta.get("facility_correlation_id")
        if not facility_id:
            continue
        if facility_id not in groups:
            groups[facility_id] = {
                "facility_correlation_id": facility_id,
                "rule_name": alert.rule_name,
                "wells": set(),
                "alerts": [],
                "count": 0,
                "max_severity": alert.severity,
            }
        groups[facility_id]["wells"].add(alert.well_name)
        groups[facility_id]["alerts"].append(alert.alert_id)
        groups[facility_id]["count"] += 1
        if _severity_rank(alert.severity) > _severity_rank(groups[facility_id]["max_severity"]):
            groups[facility_id]["max_severity"] = alert.severity

    grouped = []
    for group in groups.values():
        group["wells"] = sorted(group["wells"])
        group["distinct_wells"] = len(group["wells"])
        grouped.append(group)
    grouped.sort(key=lambda x: (x["distinct_wells"], _severity_rank(x["max_severity"])), reverse=True)
    return {"groups": grouped, "count": len(grouped)}


@app.post("/alerts/{alert_id}/rca")
async def run_alert_rca(
    alert_id: str,
    request: RCARequest,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """Run lightweight RCA for a given alert and store result in metadata."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    lookback_minutes = max(5, request.lookback_minutes)
    lookback_start = datetime.utcnow() - timedelta(minutes=lookback_minutes)
    candidates = db.query(Alert).filter(
        Alert.well_name == alert.well_name,
        Alert.timestamp >= lookback_start,
    ).order_by(Alert.timestamp.desc()).limit(100).all()
    cross_well_candidates = _find_cross_well_candidates(db, alert, lookback_minutes)

    rca = _infer_rca(candidates, cross_well_candidates)
    metadata = _merge_metadata(alert.metadata_json)
    metadata["rca"] = {
        "generated_at": datetime.utcnow().isoformat(),
        "lookback_minutes": lookback_minutes,
        **rca,
    }
    alert.metadata_json = metadata
    db.commit()

    return {
        "alert_id": alert_id,
        "correlation_id": metadata.get("correlation_id"),
        "facility_correlation_id": metadata.get("facility_correlation_id"),
        "rca": metadata["rca"],
    }


@app.post("/notifications/devices/register")
async def register_push_device(
    request: PushDeviceRegisterRequest,
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """Register a mobile push token for critical alert notifications."""
    key = f"{request.user_id}:{request.device_token}"
    REGISTERED_PUSH_DEVICES[key] = {
        "user_id": request.user_id,
        "platform": request.platform,
        "device_token": request.device_token,
        "registered_at": datetime.utcnow().isoformat(),
    }
    return {"message": "Device registered", "count": len(REGISTERED_PUSH_DEVICES)}


@app.post("/notifications/devices/unregister")
async def unregister_push_device(
    request: PushDeviceRegisterRequest,
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """Unregister a mobile push token."""
    key = f"{request.user_id}:{request.device_token}"
    REGISTERED_PUSH_DEVICES.pop(key, None)
    return {"message": "Device unregistered", "count": len(REGISTERED_PUSH_DEVICES)}


@app.get("/notifications/devices")
async def list_push_devices(
    _: Dict[str, Any] = Depends(require_alert_admin),
):
    """List currently registered push devices."""
    return {
        "devices": list(REGISTERED_PUSH_DEVICES.values()),
        "count": len(REGISTERED_PUSH_DEVICES),
    }


@app.get("/notifications/sms/status")
async def get_sms_status(
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """SMS provider status + registered recipients."""
    return {
        **sms_provider_status(),
        "recipients": list_sms_recipients(),
    }


@app.post("/notifications/sms/register")
async def register_sms_phone(
    request: SmsRegisterRequest,
    _: Dict[str, Any] = Depends(require_alert_write),
):
    """Register a mobile number for alert SMS."""
    try:
        recipient = register_sms_recipient(
            request.phone,
            label=request.label or "اپراتور میدان",
            enabled=request.enabled,
            severities=request.severities,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "شماره موبایل برای پیامک هشدار ثبت شد",
        "recipient": recipient,
        "status": sms_provider_status(),
    }


@app.post("/notifications/sms/unregister")
async def unregister_sms_phone(
    request: SmsRegisterRequest,
    _: Dict[str, Any] = Depends(require_alert_write),
):
    """Remove a mobile number from SMS alerts."""
    try:
        removed = unregister_sms_recipient(request.phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="شماره یافت نشد")
    return {"message": "شماره حذف شد", "status": sms_provider_status()}


@app.post("/notifications/sms/test")
async def send_test_sms(
    request: SmsTestRequest,
    _: Dict[str, Any] = Depends(require_alert_write),
):
    """Send a test SMS to a registered (or provided) phone number."""
    phone = request.phone
    if not phone:
        recipients = list_sms_recipients()
        if not recipients:
            raise HTTPException(
                status_code=400,
                detail="ابتدا یک شماره موبایل ثبت کنید",
            )
        phone = recipients[0]["phone"]
    message = request.message or (
        "SOGF پیامک آزمایشی\n"
        "سامانه هوشمندسازی میدان دهلران\n"
        "اگر این پیام را دریافت کردید، اعلان SMS فعال است."
    )
    try:
        entry = await send_sms(phone, message, meta={"type": "test"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "پیامک آزمایشی ارسال/صف‌بندی شد",
        "entry": entry,
        "status": sms_provider_status(),
    }


@app.get("/notifications/sms/outbox")
async def list_sms_outbox(
    limit: int = 30,
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """Recent SMS outbox (includes mock provider records)."""
    return {"count": len(SMS_OUTBOX[:limit]), "messages": SMS_OUTBOX[:limit]}


@app.post("/alerts/{alert_id}/sms")
async def send_alert_sms_manual(
    alert_id: str,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_write),
):
    """Manually SMS-notify an existing alert to all registered numbers."""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    result = await notify_alert_via_sms(
        alert_id=alert.alert_id,
        well_name=alert.well_name,
        severity=alert.severity,
        message=alert.message,
    )
    if result.get("sent", 0) == 0 and result.get("reason") == "no_recipients":
        raise HTTPException(
            status_code=400,
            detail="هیچ شماره موبایلی برای پیامک ثبت نشده است",
        )
    return {"alert_id": alert_id, **result}


@app.post("/alerts/{alert_id}/create-work-order")
async def create_work_order_from_alert(
    alert_id: str,
    erp_type: str = "sap",
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_write),
):
    """Create work order from alert manually"""
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Check if work order already exists
    if alert.erp_work_order_id:
        return {
            "message": "Work order already exists for this alert",
            "work_order_id": alert.erp_work_order_id,
            "alert_id": alert_id,
        }

    try:
        # Call ERP service to create work order
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.ERP_SERVICE_URL}/work-orders/auto-create",
                params={"alert_id": alert_id, "erp_type": erp_type},
                timeout=30.0,
            )

            if response.status_code == 200:
                work_order_data = response.json()
                # Update alert with work order ID
                alert.erp_work_order_id = work_order_data.get("work_order_id")
                db.commit()

                logger.info(
                    f"Created work order {work_order_data.get('work_order_id')} for alert {alert_id}"
                )
                return {
                    "message": "Work order created successfully",
                    "work_order_id": work_order_data.get("work_order_id"),
                    "erp_system": work_order_data.get("erp_system"),
                    "status": work_order_data.get("status"),
                    "alert_id": alert_id,
                }
            else:
                error_detail = response.text
                logger.error(f"Failed to create work order: {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to create work order: {error_detail}",
                )
    except httpx.TimeoutException:
        logger.error("Timeout while creating work order")
        raise HTTPException(status_code=504, detail="ERP service timeout")
    except httpx.RequestError as e:
        logger.error(f"Error connecting to ERP service: {e}")
        raise HTTPException(
            status_code=503, detail=f"ERP service unavailable: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error creating work order: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create work order: {str(e)}"
        )


@app.post("/rules")
async def create_rule(
    rule: AlertRuleCreate,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_admin),
):
    """Create an alert rule"""
    db_rule = AlertRule(**rule.dict())
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)

    logger.info(f"Alert rule created: {rule.rule_id}")
    return {"message": "Rule created", "rule_id": rule.rule_id}


@app.get("/rules")
async def list_rules(
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(require_alert_read),
):
    """List all alert rules"""
    query = db.query(AlertRule)

    if enabled is not None:
        query = query.filter(AlertRule.enabled == enabled)

    rules = query.all()
    return {
        "rules": [
            AlertRuleResponse.model_validate(rule).model_dump() for rule in rules
        ],
        "count": len(rules),
    }


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Health check"""
    open_alerts = db.query(Alert).filter(Alert.status == "open").count()
    return {"status": "healthy", "open_alerts": open_alerts}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
