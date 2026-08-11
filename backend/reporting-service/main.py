"""
Reporting Service
Generates periodic and on-demand analytical reports
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import time
import uvicorn
import sys
import os
import statistics
import asyncio

import httpx

from prometheus_client import Counter, Histogram

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.logging_config import setup_logging  # type: ignore
from shared.metrics import setup_metrics  # type: ignore
from shared.tracing import setup_tracing  # type: ignore
from shared.config import settings  # type: ignore

logger = setup_logging("reporting-service")
app = FastAPI(title="OGIM Reporting Service", version="1.0.0")
setup_metrics(app, "reporting-service")
setup_tracing(app, "reporting-service")

REPORTS_GENERATED = Counter(
    "reports_generated_total",
    "Number of reports generated",
    ["report_type"],
)
REPORT_GENERATION_DURATION = Histogram(
    "report_generation_duration_seconds",
    "Time spent generating reports",
)


class ReportRequest(BaseModel):
    report_type: str  # daily, weekly, monthly, custom
    well_name: Optional[str] = None
    start_date: datetime
    end_date: datetime
    metrics: List[str] = []


class Report(BaseModel):
    report_id: str
    report_type: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    well_name: Optional[str]
    metrics: dict


reports_db = []
auto_data_quality_reports_db: List[Dict[str, Any]] = []
report_builder_db: Dict[str, Dict[str, Any]] = {}
SUPPORTED_DIMENSIONS = {"well_name", "sensor_type", "sensor_id", "data_quality"}
SUPPORTED_MEASURES = {"count", "avg_value", "min_value", "max_value", "sum_value"}
workflows_db: Dict[str, Dict[str, Any]] = {}
workflow_runs_db: List[Dict[str, Any]] = []
workflow_scheduler_task: Optional[asyncio.Task] = None
_sensor_data_cache: Dict[str, Dict[str, Any]] = {}


class DataQualityLineageRequest(BaseModel):
    well_name: Optional[str] = None
    lookback_hours: int = 24


class ReportBuilderRequest(BaseModel):
    name: str
    well_name: Optional[str] = None
    lookback_hours: int = 24
    dimensions: List[str] = ["well_name", "sensor_type"]
    measures: List[str] = ["count", "avg_value", "min_value", "max_value"]
    filters: Dict[str, Any] = {}
    limit: int = 200


class WorkflowStep(BaseModel):
    id: str
    type: str  # http_request | generate_report | data_quality_lineage
    config: Dict[str, Any] = {}
    depends_on: List[str] = []


class WorkflowCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    schedule_minutes: Optional[int] = None
    steps: List[WorkflowStep]


class WorkflowRunRequest(BaseModel):
    input: Dict[str, Any] = {}


def _safe_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "stdev": 0.0}
    if len(values) == 1:
        return {"mean": float(values[0]), "stdev": 0.0}
    return {
        "mean": float(statistics.mean(values)),
        "stdev": float(statistics.pstdev(values)),
    }


async def _fetch_sensor_data(
    limit: int = 500, well_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    cache_key = f"{well_name or 'all'}:{limit}"
    cached = _sensor_data_cache.get(cache_key)
    now_ts = time.time()
    if cached and cached["expires_at"] > now_ts:
        return cached["data"]

    service_url = os.getenv("DATA_INGESTION_SERVICE_URL", "http://localhost:8002")
    params: Dict[str, Any] = {"limit": limit}
    if well_name:
        params["well_name"] = well_name

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{service_url}/sensor-data", params=params)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("records", [])
        _sensor_data_cache[cache_key] = {
            "expires_at": now_ts + max(1, settings.CACHE_TTL_SECONDS),
            "data": records,
        }
        return records


def _build_data_quality_metrics(
    records: List[Dict[str, Any]], lookback_hours: int
) -> Dict[str, Any]:
    now = datetime.utcnow()
    horizon = now - timedelta(hours=max(1, lookback_hours))

    scoped = []
    for rec in records:
        try:
            ts = datetime.fromisoformat(
                str(rec.get("timestamp")).replace("Z", "+00:00")
            ).replace(tzinfo=None)
            if ts >= horizon:
                scoped.append(rec)
        except Exception:
            continue

    total = len(scoped)
    if total == 0:
        return {
            "overall_score": 0.0,
            "completeness": 0.0,
            "validity": 0.0,
            "timeliness": 0.0,
            "consistency": 0.0,
            "duplicates": 0,
            "null_count": 0,
            "out_of_range_count": 0,
            "record_count": 0,
            "lookback_hours": lookback_hours,
        }

    duplicates = 0
    null_count = 0
    out_of_range = 0
    timely_count = 0
    values_by_sensor: Dict[str, List[float]] = {}
    seen_keys = set()

    for rec in scoped:
        sensor_id = str(rec.get("sensor_id", "unknown"))
        ts = str(rec.get("timestamp", ""))
        dedup_key = (sensor_id, ts)
        if dedup_key in seen_keys:
            duplicates += 1
        else:
            seen_keys.add(dedup_key)

        value = rec.get("value")
        if value is None:
            null_count += 1
            continue
        try:
            val = float(value)
            values_by_sensor.setdefault(sensor_id, []).append(val)
            if val < -1000 or val > 100000:
                out_of_range += 1
        except Exception:
            out_of_range += 1
            continue

        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            if (datetime.utcnow() - dt).total_seconds() <= 120:
                timely_count += 1
        except Exception:
            pass

    consistency_violations = 0
    for sensor_values in values_by_sensor.values():
        stats = _safe_stats(sensor_values)
        if stats["stdev"] > max(1.0, abs(stats["mean"]) * 0.5):
            consistency_violations += 1

    completeness = max(0.0, 1 - (null_count / total))
    validity = max(0.0, 1 - (out_of_range / total))
    timeliness = timely_count / total
    consistency = max(0.0, 1 - (consistency_violations / max(1, len(values_by_sensor))))
    duplicate_penalty = max(0.0, 1 - (duplicates / total))
    overall = (
        completeness + validity + timeliness + consistency + duplicate_penalty
    ) / 5

    return {
        "overall_score": round(overall, 3),
        "completeness": round(completeness, 3),
        "validity": round(validity, 3),
        "timeliness": round(timeliness, 3),
        "consistency": round(consistency, 3),
        "duplicates": duplicates,
        "null_count": null_count,
        "out_of_range_count": out_of_range,
        "record_count": total,
        "lookback_hours": lookback_hours,
    }


def _build_lineage(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    sensors = sorted({str(rec.get("sensor_id", "unknown")) for rec in records})[:30]
    nodes = [
        {"id": "ingest", "label": "Data Ingestion", "type": "source"},
        {"id": "dvr", "label": "DVR Validation", "type": "process"},
        {"id": "storage", "label": "Timescale Storage", "type": "storage"},
        {"id": "features", "label": "Feature Engineering", "type": "process"},
        {"id": "ml", "label": "ML Inference", "type": "consumer"},
        {"id": "alerts", "label": "Alert Engine", "type": "consumer"},
        {"id": "reports", "label": "Reporting", "type": "consumer"},
    ]
    edges = [
        {"from": "ingest", "to": "dvr"},
        {"from": "dvr", "to": "storage"},
        {"from": "storage", "to": "features"},
        {"from": "features", "to": "ml"},
        {"from": "ml", "to": "alerts"},
        {"from": "storage", "to": "reports"},
    ]

    for sensor in sensors:
        node_id = f"sensor:{sensor}"
        nodes.append({"id": node_id, "label": sensor, "type": "dataset"})
        edges.append({"from": "ingest", "to": node_id})
        edges.append({"from": node_id, "to": "dvr"})

    return {"nodes": nodes, "edges": edges}


def _apply_filters(
    records: List[Dict[str, Any]], filters: Dict[str, Any]
) -> List[Dict[str, Any]]:
    if not filters:
        return records

    def _match(record: Dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if expected is None:
                continue
            if str(record.get(key, "")) != str(expected):
                return False
        return True

    return [r for r in records if _match(r)]


def _run_report_builder_query(
    records: List[Dict[str, Any]],
    dimensions: List[str],
    measures: List[str],
    limit: int = 200,
) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        dim_values = {d: rec.get(d) for d in dimensions}
        key = "|".join([str(dim_values[d]) for d in dimensions])
        if key not in groups:
            groups[key] = {
                **dim_values,
                "_count": 0,
                "_sum": 0.0,
                "_min": None,
                "_max": None,
            }

        item = groups[key]
        item["_count"] += 1
        try:
            value = float(rec.get("value", 0))
            item["_sum"] += value
            item["_min"] = value if item["_min"] is None else min(item["_min"], value)
            item["_max"] = value if item["_max"] is None else max(item["_max"], value)
        except Exception:
            pass

    rows: List[Dict[str, Any]] = []
    for item in groups.values():
        row: Dict[str, Any] = {d: item.get(d) for d in dimensions}
        if "count" in measures:
            row["count"] = item["_count"]
        if "sum_value" in measures:
            row["sum_value"] = round(item["_sum"], 3)
        if "avg_value" in measures:
            row["avg_value"] = round(item["_sum"] / max(1, item["_count"]), 3)
        if "min_value" in measures:
            row["min_value"] = item["_min"]
        if "max_value" in measures:
            row["max_value"] = item["_max"]
        rows.append(row)

    rows.sort(key=lambda x: x.get("count", 0), reverse=True)
    return rows[:limit]


async def _execute_step(step: WorkflowStep, context: Dict[str, Any]) -> Dict[str, Any]:
    step_type = step.type
    cfg = step.config or {}

    if step_type == "http_request":
        method = str(cfg.get("method", "GET")).upper()
        url = cfg.get("url")
        if not url:
            raise ValueError(f"Step {step.id}: missing url")
        timeout = float(cfg.get("timeout_seconds", 15))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                params=cfg.get("params"),
                json=cfg.get("json"),
                headers=cfg.get("headers"),
            )
            return {
                "status_code": response.status_code,
                "ok": response.is_success,
                "body": (
                    response.json()
                    if "application/json" in response.headers.get("content-type", "")
                    else response.text
                ),
            }

    if step_type == "generate_report":
        now = datetime.utcnow()
        req = ReportRequest(
            report_type=cfg.get("report_type", "custom"),
            well_name=cfg.get("well_name"),
            start_date=now - timedelta(hours=int(cfg.get("lookback_hours", 24))),
            end_date=now,
            metrics=cfg.get("metrics", []),
        )
        return await generate_report(req)

    if step_type == "data_quality_lineage":
        req = DataQualityLineageRequest(
            well_name=cfg.get("well_name"),
            lookback_hours=int(cfg.get("lookback_hours", 24)),
        )
        return await generate_data_quality_lineage_report(req)

    raise ValueError(f"Unsupported step type: {step_type}")


async def _run_workflow(
    workflow: Dict[str, Any],
    trigger: str,
    trigger_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    run_id = f"WFR-{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}"
    steps = [WorkflowStep(**s) for s in workflow.get("steps", [])]
    status = "success"
    context: Dict[str, Any] = {"input": trigger_input or {}}
    step_results: Dict[str, Any] = {}

    try:
        pending = {s.id: s for s in steps}
        executed = set()
        while pending:
            progress = False
            for step_id, step in list(pending.items()):
                if all(dep in executed for dep in step.depends_on):
                    result = await _execute_step(step, context)
                    step_results[step_id] = {"status": "success", "result": result}
                    context[step_id] = result
                    executed.add(step_id)
                    pending.pop(step_id)
                    progress = True
            if not progress:
                raise ValueError("Workflow has circular or unresolved dependencies.")
    except Exception as exc:
        status = "failed"
        step_results["error"] = str(exc)

    run_record = {
        "run_id": run_id,
        "workflow_id": workflow["workflow_id"],
        "workflow_name": workflow["name"],
        "trigger": trigger,
        "started_at": datetime.utcnow().isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
        "status": status,
        "steps": step_results,
    }
    workflow_runs_db.append(run_record)
    workflow["last_run_at"] = run_record["finished_at"]
    workflow["last_run_status"] = status
    return run_record


async def _workflow_scheduler_loop():
    while True:
        try:
            now = datetime.utcnow()
            for wf in workflows_db.values():
                every = wf.get("schedule_minutes")
                if not every:
                    continue
                last = wf.get("_last_scheduled_run_ts")
                should_run = (
                    last is None
                    or (now - datetime.fromisoformat(last)).total_seconds()
                    >= int(every) * 60
                )
                if should_run:
                    wf["_last_scheduled_run_ts"] = now.isoformat()
                    await _run_workflow(wf, trigger="schedule")
        except Exception as exc:
            logger.warning("Workflow scheduler iteration failed: %s", exc)
        await asyncio.sleep(20)


@app.post("/reports/generate")
async def generate_report(request: ReportRequest):
    """Generate a new report"""
    start = time.perf_counter()
    report_id = f"RPT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    report = {
        "report_id": report_id,
        "report_type": request.report_type,
        "generated_at": datetime.now().isoformat(),
        "period_start": request.start_date.isoformat(),
        "period_end": request.end_date.isoformat(),
        "well_name": request.well_name,
        "metrics": {
            "total_production": 12500.5,
            "average_pressure": 350.2,
            "average_temperature": 85.3,
            "alerts_count": 12,
            "downtime_hours": 2.5,
        },
    }

    reports_db.append(report)
    duration = time.perf_counter() - start
    REPORTS_GENERATED.labels(report_type=request.report_type).inc()
    REPORT_GENERATION_DURATION.observe(duration)
    logger.info(
        "Report generated",
        extra={
            "report_id": report_id,
            "report_type": request.report_type,
            "duration": duration,
        },
    )
    return report


@app.get("/reports")
async def list_reports(well_name: Optional[str] = None, limit: int = 50):
    """List reports"""
    filtered = reports_db
    if well_name:
        filtered = [r for r in filtered if r.get("well_name") == well_name]
    return {"reports": filtered[-limit:], "count": len(filtered)}


@app.get("/reports/{report_id}")
async def get_report(report_id: str):
    """Get report by ID"""
    report = next((r for r in reports_db if r["report_id"] == report_id), None)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.post("/reports/builder")
async def run_report_builder(request: ReportBuilderRequest):
    """Build advanced analytic report with dimensions, measures, and filters."""
    invalid_dims = [d for d in request.dimensions if d not in SUPPORTED_DIMENSIONS]
    invalid_measures = [m for m in request.measures if m not in SUPPORTED_MEASURES]
    if invalid_dims:
        raise HTTPException(
            status_code=400, detail=f"Unsupported dimensions: {invalid_dims}"
        )
    if invalid_measures:
        raise HTTPException(
            status_code=400, detail=f"Unsupported measures: {invalid_measures}"
        )

    records = await _fetch_sensor_data(limit=2000, well_name=request.well_name)
    records = _apply_filters(records, request.filters)
    rows = _run_report_builder_query(
        records, request.dimensions, request.measures, request.limit
    )
    report_id = f"BI-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    report = {
        "report_id": report_id,
        "report_type": "advanced_bi",
        "name": request.name,
        "generated_at": datetime.utcnow().isoformat(),
        "well_name": request.well_name,
        "dimensions": request.dimensions,
        "measures": request.measures,
        "filters": request.filters,
        "rows": rows,
        "count": len(rows),
    }
    reports_db.append(report)
    report_builder_db[report_id] = report
    REPORTS_GENERATED.labels(report_type="advanced_bi").inc()
    return report


@app.get("/bi/metadata")
async def get_bi_metadata():
    """Expose dataset metadata for Power BI/Tableau semantic modeling."""
    return {
        "dataset": "ogim_sensor_data",
        "dimensions": sorted(list(SUPPORTED_DIMENSIONS)),
        "measures": sorted(list(SUPPORTED_MEASURES)),
        "sample_query": {
            "name": "pressure_by_well",
            "dimensions": ["well_name", "sensor_type"],
            "measures": ["count", "avg_value", "max_value"],
            "filters": {"sensor_type": "pressure"},
            "lookback_hours": 24,
        },
    }


@app.post("/bi/query")
async def query_bi_dataset(request: ReportBuilderRequest):
    """BI connector endpoint for external tools to fetch aggregated rows."""
    return await run_report_builder(request)


@app.get("/bi/connectors")
async def get_bi_connectors():
    """Connection templates for Power BI / Tableau."""
    gateway = os.getenv("API_GATEWAY_PUBLIC_URL", "http://localhost:8000")
    return {
        "power_bi": {
            "method": "REST",
            "base_url": f"{gateway}/api/reporting/bi/query",
            "metadata_url": f"{gateway}/api/reporting/bi/metadata",
            "auth": "Bearer token via API Gateway",
            "sample_payload": {
                "name": "Power BI Export",
                "dimensions": ["well_name", "sensor_type"],
                "measures": ["count", "avg_value", "max_value"],
                "lookback_hours": 24,
                "limit": 500,
            },
            "notes": "Use Power BI 'Web' connector with POST and JSON body.",
        },
        "tableau": {
            "method": "Web Data Connector / REST",
            "base_url": f"{gateway}/api/reporting/bi/query",
            "metadata_url": f"{gateway}/api/reporting/bi/metadata",
            "auth": "Bearer token via API Gateway",
            "sample_payload": {
                "name": "Tableau Export",
                "dimensions": ["well_name", "sensor_id"],
                "measures": ["avg_value", "min_value", "max_value"],
                "lookback_hours": 48,
                "limit": 1000,
            },
            "notes": "Use /bi/metadata to bootstrap schema and /bi/query for data pulls.",
        },
    }


@app.post("/reports/data-quality-lineage")
async def generate_data_quality_lineage_report(request: DataQualityLineageRequest):
    """Generate a combined Data Quality + Lineage report."""
    start = time.perf_counter()
    try:
        records = await _fetch_sensor_data(limit=1000, well_name=request.well_name)
    except Exception as exc:
        logger.warning("Failed to fetch sensor data for DQ report: %s", exc)
        records = []

    quality = _build_data_quality_metrics(records, request.lookback_hours)
    lineage = _build_lineage(records)

    report_id = f"DQ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    payload = {
        "report_id": report_id,
        "report_type": "data_quality_lineage",
        "generated_at": datetime.utcnow().isoformat(),
        "well_name": request.well_name,
        "quality": quality,
        "lineage": lineage,
        "summary": (
            "Data quality is healthy."
            if quality["overall_score"] >= 0.8
            else "Data quality requires attention."
        ),
    }
    reports_db.append(payload)
    REPORTS_GENERATED.labels(report_type="data_quality_lineage").inc()
    REPORT_GENERATION_DURATION.observe(time.perf_counter() - start)
    return payload


@app.post("/reports/data-quality-lineage/auto")
async def create_auto_data_quality_report(request: DataQualityLineageRequest):
    """Create and store an automatic Data Quality + Lineage report snapshot."""
    report = await generate_data_quality_lineage_report(request)
    auto_entry = {
        "auto_report_id": f"AUTO-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "created_at": datetime.utcnow().isoformat(),
        "next_run_eta_minutes": 60,
        "report": report,
    }
    auto_data_quality_reports_db.append(auto_entry)
    return auto_entry


@app.get("/reports/data-quality-lineage/auto")
async def list_auto_data_quality_reports(limit: int = 20):
    """List recent automatic Data Quality + Lineage reports."""
    recent = auto_data_quality_reports_db[-limit:]
    return {"reports": recent, "count": len(recent)}


@app.post("/workflows")
async def create_workflow(request: WorkflowCreateRequest):
    """Create an airflow-like workflow DAG."""
    workflow_id = f"WF-{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}"
    workflow = {
        "workflow_id": workflow_id,
        "name": request.name,
        "description": request.description,
        "schedule_minutes": request.schedule_minutes,
        "steps": [s.model_dump() for s in request.steps],
        "created_at": datetime.utcnow().isoformat(),
        "last_run_at": None,
        "last_run_status": None,
    }
    workflows_db[workflow_id] = workflow
    return workflow


@app.get("/workflows")
async def list_workflows():
    """List defined workflows."""
    return {"workflows": list(workflows_db.values()), "count": len(workflows_db)}


@app.get("/workflows/templates")
async def list_workflow_templates():
    """Pre-built workflow templates for common operational tasks."""
    return {
        "templates": [
            {
                "template_id": "daily-dq-report",
                "name": "Daily Data Quality Report",
                "description": "Generate DQ + lineage report every 24 hours",
                "schedule_minutes": 1440,
                "steps": [
                    {
                        "id": "dq",
                        "type": "data_quality_lineage",
                        "config": {"lookback_hours": 24},
                        "depends_on": [],
                    },
                ],
            },
            {
                "template_id": "hourly-health-check",
                "name": "Hourly Service Health Check",
                "description": "Ping reporting and alert services",
                "schedule_minutes": 60,
                "steps": [
                    {
                        "id": "reporting_health",
                        "type": "http_request",
                        "config": {
                            "method": "GET",
                            "url": "http://reporting-service:8005/health",
                        },
                        "depends_on": [],
                    },
                    {
                        "id": "alert_health",
                        "type": "http_request",
                        "config": {
                            "method": "GET",
                            "url": "http://alert-service:8004/health",
                        },
                        "depends_on": ["reporting_health"],
                    },
                ],
            },
            {
                "template_id": "weekly-production-report",
                "name": "Weekly Production Report",
                "description": "Generate weekly report then DQ validation",
                "schedule_minutes": 10080,
                "steps": [
                    {
                        "id": "report",
                        "type": "generate_report",
                        "config": {"report_type": "weekly"},
                        "depends_on": [],
                    },
                    {
                        "id": "dq",
                        "type": "data_quality_lineage",
                        "config": {"lookback_hours": 168},
                        "depends_on": ["report"],
                    },
                ],
            },
        ]
    }


@app.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    workflow = workflows_db.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.post("/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, request: WorkflowRunRequest):
    """Run workflow on-demand."""
    workflow = workflows_db.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await _run_workflow(workflow, trigger="manual", trigger_input=request.input)


@app.get("/workflows/{workflow_id}/runs")
async def get_workflow_runs(workflow_id: str, limit: int = 20):
    runs = [r for r in workflow_runs_db if r["workflow_id"] == workflow_id]
    return {"runs": runs[-limit:], "count": len(runs)}


@app.get("/workflows/visual-builder/step-types")
async def get_visual_builder_step_types():
    """Expose step catalog for visual builder."""
    return {
        "step_types": [
            {
                "type": "http_request",
                "label": "HTTP Request",
                "config_schema": {
                    "method": "GET|POST|PUT|DELETE",
                    "url": "string",
                    "params": "object(optional)",
                    "json": "object(optional)",
                    "headers": "object(optional)",
                },
            },
            {
                "type": "generate_report",
                "label": "Generate Standard Report",
                "config_schema": {
                    "report_type": "daily|weekly|monthly|custom",
                    "well_name": "string(optional)",
                },
            },
            {
                "type": "data_quality_lineage",
                "label": "Generate DQ + Lineage",
                "config_schema": {
                    "well_name": "string(optional)",
                    "lookback_hours": "integer",
                },
            },
        ]
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "total_reports": len(reports_db)}


@app.on_event("startup")
async def workflow_startup():
    global workflow_scheduler_task
    if workflow_scheduler_task is None:
        workflow_scheduler_task = asyncio.create_task(_workflow_scheduler_loop())


@app.on_event("shutdown")
async def workflow_shutdown():
    global workflow_scheduler_task
    if workflow_scheduler_task:
        workflow_scheduler_task.cancel()
        workflow_scheduler_task = None


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)
