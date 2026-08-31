"""
API Gateway Service
Single entry point for all UI and API requests
"""

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    Depends,
    WebSocket,
    WebSocketDisconnect,
    Query,
    Body,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.responses import JSONResponse, Response, StreamingResponse
import httpx
import uvicorn
from typing import Optional, Any, Dict
import logging
import os
import sys
import json
import asyncio
from datetime import datetime, timezone
import ipaddress
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.config import settings
from shared.security import decode_token
from shared.metrics import setup_metrics

try:
    from shared.tracing import setup_tracing
except Exception:  # pragma: no cover - fallback for lean test/runtime environments

    def setup_tracing(*args, **kwargs):
        logger.warning("Tracing disabled: OpenTelemetry dependencies unavailable")


from shared.advanced_rate_limiter import get_rate_limiter, RateLimitConfig
from shared.mtls_manager import get_mtls_manager
from shared.threat_detection import siem_logger, threat_detector
from shared.input_validation import (
    contains_suspicious_content,
    scan_payload_for_attacks,
)
from shared.response_cache import TTLResponseCache
from shared.kpi_metrics import (
    get_executive_summary,
    record_feature_usage,
    record_latency,
    record_uptime_check,
)

app = FastAPI(
    title="SOGF API Gateway",
    description="API Gateway for SOGF - Smartening Oil & Gas Fields",
    version="1.0.0",
)

setup_metrics(app, "api-gateway")
setup_tracing(app, "api-gateway", instrument_httpx=True)

# Initialize rate limiter
rate_limiter = get_rate_limiter(redis_url=settings.RATE_LIMIT_REDIS_URL)

# Initialize mTLS manager
mtls_manager = get_mtls_manager(
    cert_dir=settings.MTLS_CERT_DIR,
    ca_cert_path=settings.MTLS_CA_CERT_PATH,
    client_cert_path=settings.MTLS_CLIENT_CERT_PATH,
    client_key_path=settings.MTLS_CLIENT_KEY_PATH,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Service discovery (in production, use service mesh or discovery service).
# Each upstream is reachable by its docker-compose service name on the shared
# network - these come straight from shared/config.py so a single source of
# truth defines both. A single shared SERVICE_HOST would break this: every
# service is its own container, not all reachable at one hostname.
SERVICES = {
    "auth": settings.AUTH_SERVICE_URL,
    "data-ingestion": settings.DATA_INGESTION_SERVICE_URL,
    "ml-inference": settings.ML_INFERENCE_SERVICE_URL,
    "alert": settings.ALERT_SERVICE_URL,
    "reporting": settings.REPORTING_SERVICE_URL,
    "command-control": settings.COMMAND_CONTROL_SERVICE_URL,
    "tag-catalog": settings.TAG_CATALOG_SERVICE_URL,
    "digital-twin": settings.DIGITAL_TWIN_SERVICE_URL,
    "edge-computing": settings.EDGE_SERVICE_URL,
    "erp-integration": settings.ERP_SERVICE_URL,
    "dvr": settings.DVR_SERVICE_URL,
    "remote-operations": settings.REMOTE_OPERATIONS_SERVICE_URL,
    "data-variables": settings.DATA_VARIABLES_SERVICE_URL,
    "storage-optimization": settings.STORAGE_OPTIMIZATION_SERVICE_URL,
}

SERVICE_ROLE_REQUIREMENTS = {
    "data-ingestion": {"system_admin", "data_engineer"},
    "ml-inference": {"system_admin", "data_engineer", "field_operator"},
    "alert": {"system_admin", "field_operator", "data_engineer"},
    "reporting": {"system_admin", "data_engineer"},
    "command-control": {"system_admin"},
    "tag-catalog": {"system_admin", "data_engineer"},
    "digital-twin": {"system_admin", "data_engineer"},
    "edge-computing": {"system_admin", "data_engineer", "field_operator"},
    "erp-integration": {"system_admin", "data_engineer"},
    "dvr": {"system_admin", "data_engineer"},
    "remote-operations": {"system_admin", "field_operator"},
    "data-variables": {"system_admin", "data_engineer", "field_operator"},
    "storage-optimization": {"system_admin", "data_engineer"},
}
upstream_client: Optional[httpx.AsyncClient] = None
response_cache = TTLResponseCache(
    default_ttl_seconds=settings.CACHE_TTL_SECONDS,
    max_entries=settings.CACHE_MAX_ENTRIES,
)
CACHEABLE_GET_PREFIXES = (
    "/api/reporting/bi/metadata",
    "/api/reporting/workflows/templates",
    "/api/digital-twin/wells",
    "/api/tag-catalog/tags",
)
SAFE_HEADERS_ALLOWLIST = {
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "cache-control",
    "content-type",
    "if-none-match",
    "origin",
    "referer",
    "user-agent",
    "x-correlation-id",
    "x-request-id",
    "x-forwarded-for",
    "x-real-ip",
}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


PUBLIC_AUTH_PATHS = {"api/auth/token", "api/auth/refresh", "api/auth/health"}


async def authenticate_request(request: Request):
    """Validate authentication token"""
    if request.url.path.strip("/") in PUBLIC_AUTH_PATHS:
        return None

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")

    token = auth_header.split(" ", 1)[1].strip()

    try:
        payload = decode_token(token)
    except ValueError as exc:
        logger.warning("Token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))

    request.state.user = payload
    return payload


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "").strip()
    if forwarded_for:
        return forwarded_for
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def _contains_suspicious_content(value: str) -> bool:
    return contains_suspicious_content(value)


def _scan_payload_for_attacks(payload: Any) -> bool:
    return scan_payload_for_attacks(payload)


def _build_security_headers() -> Dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    }


async def validate_and_harden_request(request: Request, service_name: str, path: str):
    """Validate request shape and block suspicious payloads."""
    if not settings.API_SECURITY_ENABLE_INPUT_HARDENING:
        return None

    if len(path) > settings.API_SECURITY_MAX_PARAM_LENGTH:
        raise HTTPException(status_code=414, detail="Request path is too long")
    if len(request.query_params) > settings.API_SECURITY_MAX_QUERY_PARAMS:
        raise HTTPException(status_code=400, detail="Too many query parameters")

    for key, value in request.query_params.multi_items():
        if (
            len(key) > settings.API_SECURITY_MAX_PARAM_LENGTH
            or len(value) > settings.API_SECURITY_MAX_PARAM_LENGTH
        ):
            raise HTTPException(
                status_code=400, detail="Query parameter length exceeded"
            )
        if _contains_suspicious_content(key) or _contains_suspicious_content(value):
            siem_logger.emit(
                "request_blocked_suspicious_query",
                "high",
                {
                    "ip": _client_ip(request),
                    "service": service_name,
                    "path": path,
                    "query_key": key,
                },
            )
            raise HTTPException(
                status_code=400, detail="Request contains blocked input patterns"
            )

    body = None
    if request.method in WRITE_METHODS:
        body = await request.body()
        if len(body) > settings.API_SECURITY_MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request payload is too large")

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type and body:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Malformed JSON payload")
            if _scan_payload_for_attacks(parsed):
                siem_logger.emit(
                    "request_blocked_suspicious_payload",
                    "critical",
                    {"ip": _client_ip(request), "service": service_name, "path": path},
                )
                raise HTTPException(
                    status_code=400, detail="Request contains blocked input patterns"
                )
    return body


def _sanitize_forward_headers(request_headers: Dict[str, str]) -> Dict[str, str]:
    sanitized = {}
    for key, value in request_headers.items():
        normalized = key.lower()
        if normalized in {
            "host",
            "content-length",
            "connection",
            "transfer-encoding",
            "upgrade",
        }:
            continue
        if normalized in SAFE_HEADERS_ALLOWLIST or normalized.startswith("x-"):
            sanitized[key] = value
    return sanitized


def _ip_allowed_in_zero_trust(ip: str) -> bool:
    networks_raw = settings.ZERO_TRUST_ALLOWED_NETWORKS or ""
    networks = [n.strip() for n in networks_raw.split(",") if n.strip()]
    if not networks:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in networks:
        try:
            if ip_obj in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


async def enforce_zero_trust(request: Request, service_name: str):
    """Apply zero-trust checks before service proxying."""
    if not settings.ZERO_TRUST_ENFORCED:
        return True
    if request.url.path.strip("/") in PUBLIC_AUTH_PATHS:
        return True

    ip = _client_ip(request)
    if not _ip_allowed_in_zero_trust(ip):
        siem_logger.emit(
            "zero_trust_denied_ip",
            "high",
            {"ip": ip, "path": request.url.path, "service": service_name},
        )
        raise HTTPException(
            status_code=403, detail="Access denied by zero trust policy"
        )

    user = getattr(request.state, "user", {}) or {}
    role = user.get("role")
    if not role:
        siem_logger.emit(
            "zero_trust_missing_role",
            "high",
            {"ip": ip, "path": request.url.path, "service": service_name},
        )
        raise HTTPException(
            status_code=401, detail="Role is required by zero trust policy"
        )
    return True


async def check_rate_limit(request: Request, service_name: str):
    """Check rate limit for request"""
    if not settings.RATE_LIMIT_ENABLED:
        return True

    # Get client identifier
    client_ip = request.client.host if request.client else "unknown"

    # Get user identifier if authenticated
    user_id = None
    user_role = None
    if hasattr(request.state, "user"):
        user_id = request.state.user.get("sub")
        user_role = request.state.user.get("role")

    # Use user ID if available, otherwise IP
    identifier = user_id or client_ip

    # Get rate limit configuration
    limit_config = RateLimitConfig.get_limit(service_name, user_role)

    # Check rate limit
    allowed, info = await rate_limiter.check_rate_limit(
        identifier=identifier,
        endpoint=service_name,
        max_requests=limit_config["max_requests"],
        window_seconds=limit_config["window_seconds"],
        strategy=settings.RATE_LIMIT_STRATEGY,
    )

    if not allowed:
        logger.warning(
            f"Rate limit exceeded: identifier={identifier}, "
            f"service={service_name}, limit={limit_config}"
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers={
                "X-RateLimit-Limit": str(limit_config["max_requests"]),
                "X-RateLimit-Remaining": str(info.get("remaining", 0)),
                "X-RateLimit-Reset": str(info.get("reset", 0)),
                "Retry-After": str(limit_config["window_seconds"]),
            },
        )

    # Add rate limit headers to response
    request.state.rate_limit_info = info

    # Extra endpoint-level guard to reduce abuse on hot paths.
    endpoint_key = f"{service_name}:{request.method}:{request.url.path}"
    endpoint_limit = (
        max(5, int(limit_config["max_requests"] * 0.5))
        if request.method in WRITE_METHODS
        else limit_config["max_requests"]
    )
    endpoint_allowed, endpoint_info = await rate_limiter.check_rate_limit(
        identifier=identifier,
        endpoint=endpoint_key,
        max_requests=endpoint_limit,
        window_seconds=limit_config["window_seconds"],
        strategy=settings.RATE_LIMIT_STRATEGY,
    )
    if not endpoint_allowed:
        raise HTTPException(
            status_code=429,
            detail="Endpoint rate limit exceeded. Please try again later.",
            headers={
                "X-RateLimit-Limit": str(endpoint_limit),
                "X-RateLimit-Remaining": str(endpoint_info.get("remaining", 0)),
                "X-RateLimit-Reset": str(endpoint_info.get("reset", 0)),
                "Retry-After": str(limit_config["window_seconds"]),
            },
        )

    request.state.endpoint_rate_limit_info = endpoint_info
    return True


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"service": "API Gateway", "status": "healthy", "version": "1.0.0"}


@app.get("/kpi/summary")
async def kpi_summary():
    """Executive KPI summary: latency, uptime, adoption, false-positive rate."""
    record_uptime_check(True)
    return get_executive_summary()


@app.get("/kpi/cache-stats")
async def kpi_cache_stats():
    """Response cache statistics for performance tuning."""
    return response_cache.stats()


@app.post("/kpi/feature-usage")
async def kpi_feature_usage(payload: Dict[str, Any]):
    """Record feature adoption hit from the web UI."""
    feature = str(payload.get("feature") or "").strip()
    if not feature or len(feature) > 128:
        raise HTTPException(status_code=400, detail="Invalid feature name")
    if contains_suspicious_content(feature):
        raise HTTPException(
            status_code=400, detail="Request contains blocked input patterns"
        )
    record_feature_usage(feature)
    return {"recorded": True, "feature": feature}


@app.post("/kpi/cache/invalidate")
async def kpi_cache_invalidate(payload: Optional[Dict[str, Any]] = Body(default=None)):
    """Invalidate response cache entries (optional prefix) for ops/tuning."""
    prefix = ""
    if payload and isinstance(payload, dict):
        prefix = str(payload.get("prefix") or "")
    if prefix:
        removed = response_cache.invalidate_prefix(prefix)
    else:
        response_cache.clear()
        removed = -1
    return {"invalidated": True, "removed": removed, "stats": response_cache.stats()}


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}


@app.get("/security/siem/events")
async def get_siem_events(limit: int = 50, severity: Optional[str] = None):
    """Return recent SIEM security events for the Security Center dashboard."""
    return {
        "events": siem_logger.recent_events(limit=min(limit, 200), severity=severity),
        "summary": siem_logger.summary(),
    }


@app.get("/security/threat/status")
async def get_threat_status():
    """Expose zero-trust and threat-detection configuration status."""
    return {
        "zero_trust_enforced": settings.ZERO_TRUST_ENFORCED,
        "zero_trust_networks": [
            n.strip()
            for n in (settings.ZERO_TRUST_ALLOWED_NETWORKS or "").split(",")
            if n.strip()
        ],
        "threat_block_threshold": settings.THREAT_BLOCK_THRESHOLD,
        "api_security_hardening": settings.API_SECURITY_ENABLE_INPUT_HARDENING,
        "siem_summary": siem_logger.summary(),
    }


class RealtimeBroadcaster:
    """Fan-out for pushed realtime events to every connected WebSocket client.

    Replaces the previous design where the gateway itself polled
    data-ingestion-service's REST endpoint once a second (a full poll
    interval plus an HTTP round-trip of added latency, regardless of how
    fresh the data actually was). Services now push new data here directly
    (see POST /internal/realtime/publish) and every subscriber queue gets it
    immediately.
    """

    def __init__(self) -> None:
        self._subscribers: set = set()

    def subscribe(self) -> "asyncio.Queue":
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue") -> None:
        self._subscribers.discard(queue)

    def publish(self, payload: Dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer: drop the oldest pending event rather than
                # blocking the publisher or growing unbounded.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass


realtime_broadcaster = RealtimeBroadcaster()
# Fallback cadence for the WebSocket loop when nothing has been pushed
# recently (keeps alerts/heartbeat fresh even for idle wells). This is a
# safety net, not the primary delivery path anymore.
REALTIME_FALLBACK_POLL_SECONDS = 10.0


async def _fetch_realtime_snapshot() -> Dict[str, Any]:
    """
    Collect a lightweight snapshot for realtime transport.
    Errors are isolated so one upstream outage doesn't break the stream.
    """
    sensor_records = []
    open_alerts = {"count": 0, "alerts": []}

    client = upstream_client
    if client is None:
        timeout = httpx.Timeout(5.0, connect=2.0)
        client = httpx.AsyncClient(timeout=timeout)
    try:
        sensor_res = await client.get(
            f"{SERVICES['data-ingestion']}/sensor-data", params={"limit": 20}
        )
        if sensor_res.is_success:
            sensor_records = sensor_res.json().get("records", [])
    except Exception as exc:
        logger.debug("Realtime sensor fetch failed: %s", exc)

    try:
        alert_res = await client.get(
            f"{SERVICES['alert']}/alerts", params={"status": "open"}
        )
        if alert_res.is_success:
            open_alerts = alert_res.json()
    except Exception as exc:
        logger.debug("Realtime alert fetch failed: %s", exc)

    return {
        "type": "snapshot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "sensor_records": sensor_records,
            "alerts": open_alerts,
        },
    }


@app.websocket("/stream/realtime/ws")
async def realtime_websocket(websocket: WebSocket, token: str = Query(default="")):
    """Low-latency realtime stream over WebSocket."""
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    try:
        decode_token(token)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await websocket.accept()
    logger.info("Realtime WebSocket connected")

    queue = realtime_broadcaster.subscribe()

    async def sender_loop() -> None:
        while True:
            try:
                # Primary path: forward pushed events (e.g. from
                # data-ingestion-service) the instant they arrive.
                pushed = await asyncio.wait_for(
                    queue.get(), timeout=REALTIME_FALLBACK_POLL_SECONDS
                )
                await websocket.send_json(pushed)
            except asyncio.TimeoutError:
                # Nothing pushed recently: fall back to a snapshot so alerts
                # and the connection heartbeat stay current for idle wells.
                snapshot = await _fetch_realtime_snapshot()
                await websocket.send_json(snapshot)

    async def receiver_loop() -> None:
        # sender_loop only ever sends, so without this the client's
        # disconnect would go unnoticed for up to REALTIME_FALLBACK_POLL_SECONDS
        # (until the next send() happens to fail) instead of being detected
        # immediately.
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))

    sender_task = asyncio.ensure_future(sender_loop())
    receiver_task = asyncio.ensure_future(receiver_loop())
    try:
        done, pending = await asyncio.wait(
            {sender_task, receiver_task}, return_when=asyncio.FIRST_EXCEPTION
        )
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
    except WebSocketDisconnect:
        logger.info("Realtime WebSocket disconnected")
    except Exception as exc:
        logger.warning("Realtime WebSocket error: %s", exc)
        try:
            await websocket.close(code=1011, reason="Internal stream error")
        except Exception:
            pass
    finally:
        realtime_broadcaster.unsubscribe(queue)


@app.post("/internal/realtime/publish")
async def publish_realtime_event(request: Request):
    """Internal push endpoint for services to feed the realtime WebSocket stream.

    Not part of the public API surface: it bypasses authenticate_request /
    enforce_zero_trust (those only wrap the /api/{service}/{path} proxy
    route) and instead checks a shared internal service token, since this
    lets the caller broadcast arbitrary data straight to every connected
    dashboard client.
    """
    internal_token = request.headers.get("X-Internal-Token", "")
    if not internal_token or internal_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid internal service token")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    payload = {
        "type": body.get("type", "push"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": body.get("data", {}),
    }
    realtime_broadcaster.publish(payload)
    return {"status": "published"}


@app.get("/stream/realtime/sse")
async def realtime_sse(token: str):
    """Realtime stream fallback over Server-Sent Events."""
    try:
        decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    async def event_generator():
        while True:
            snapshot = await _fetch_realtime_snapshot()
            # SSE format: event + data + blank line.
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.on_event("startup")
async def startup_gateway():
    global upstream_client
    limits = httpx.Limits(
        max_keepalive_connections=settings.API_GATEWAY_HTTP_KEEPALIVE_CONNECTIONS,
        max_connections=settings.API_GATEWAY_HTTP_MAX_CONNECTIONS,
    )
    timeout = httpx.Timeout(
        settings.API_GATEWAY_UPSTREAM_TIMEOUT_SECONDS,
        connect=3.0,
    )
    upstream_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    logger.info("Upstream HTTP client initialized with pooled connections")


@app.on_event("shutdown")
async def shutdown_gateway():
    global upstream_client
    if upstream_client is not None:
        await upstream_client.aclose()
        upstream_client = None


@app.api_route(
    "/api/{service_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_request(
    service_name: str,
    path: str,
    request: Request,
    token: str = Depends(authenticate_request),
):
    """Proxy requests to backend services"""
    if service_name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")

    await check_rate_limit(request, service_name)
    await enforce_zero_trust(request, service_name)

    # Determine protocol (https if mTLS enabled, otherwise http)
    protocol = (
        "https" if (settings.MTLS_ENABLED and mtls_manager.mtls_enabled) else "http"
    )
    base_url = SERVICES[service_name].replace("http://", "").replace("https://", "")
    service_url = f"{protocol}://{base_url}"
    target_url = f"{service_url}/{path}"

    required_roles = SERVICE_ROLE_REQUIREMENTS.get(service_name)
    if required_roles:
        payload = request.state.user
        role = payload.get("role")
        if not role:
            raise HTTPException(
                status_code=401, detail="Token missing role information"
            )
        if role not in required_roles:
            logger.warning(
                "Forbidden: user=%s role=%s service=%s path=%s",
                payload.get("sub"),
                role,
                service_name,
                path,
            )
            raise HTTPException(status_code=403, detail="Not enough permissions")

    # Forward query parameters
    params = dict(request.query_params)

    body = await validate_and_harden_request(request, service_name, path)

    # Forward headers
    headers = _sanitize_forward_headers(dict(request.headers))

    full_path = f"/api/{service_name}/{path}"
    user_sub = (
        (request.state.user or {}).get("sub", "")
        if hasattr(request.state, "user")
        else ""
    )
    cache_key = None
    if request.method == "GET" and any(
        full_path.startswith(p) for p in CACHEABLE_GET_PREFIXES
    ):
        query_str = str(request.url.query or "")
        cache_key = response_cache.build_key("GET", full_path, query_str, user_sub)
        cached = response_cache.get(cache_key)
        if cached is not None:
            record_latency(service_name, 0.001)
            return JSONResponse(
                status_code=200,
                content=cached,
                headers={**_build_security_headers(), "X-Cache": "HIT"},
            )

    started = time.perf_counter()

    # Get mTLS configuration if enabled; fallback to one-shot client for that path.
    use_dedicated_mtls_client = settings.MTLS_ENABLED and mtls_manager.mtls_enabled

    try:
        if use_dedicated_mtls_client:
            client_kwargs = mtls_manager.get_httpx_client_kwargs(
                verify=settings.MTLS_VERIFY_SERVER
            )
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    params=params,
                    content=body,
                    headers=headers,
                    timeout=settings.API_GATEWAY_UPSTREAM_TIMEOUT_SECONDS,
                )
        else:
            client = upstream_client
            if client is None:
                raise HTTPException(
                    status_code=503, detail="Gateway upstream client unavailable"
                )
            response = await client.request(
                method=request.method,
                url=target_url,
                params=params,
                content=body,
                headers=headers,
                timeout=settings.API_GATEWAY_UPSTREAM_TIMEOUT_SECONDS,
            )
    except httpx.TimeoutException:
        logger.error("Timeout while proxying request to %s", service_name)
        raise HTTPException(status_code=504, detail=f"Service {service_name} timed out")
    except httpx.RequestError as e:
        logger.error("Error proxying to %s: %s", service_name, e)
        record_uptime_check(False)
        raise HTTPException(
            status_code=502, detail=f"Service {service_name} unavailable"
        )

    record_latency(service_name, time.perf_counter() - started)
    record_uptime_check(response.is_success)

    risk_score, reasons = threat_detector.evaluate(
        ip=_client_ip(request),
        user=(
            (request.state.user or {}).get("sub")
            if hasattr(request.state, "user")
            else None
        ),
        path=request.url.path,
        method=request.method,
        status_code=response.status_code,
        user_agent=request.headers.get("user-agent", ""),
    )
    if risk_score >= settings.THREAT_BLOCK_THRESHOLD:
        siem_logger.emit(
            "threat_detected_blocked",
            "critical",
            {
                "ip": _client_ip(request),
                "path": request.url.path,
                "method": request.method,
                "service": service_name,
                "risk_score": risk_score,
                "reasons": reasons,
            },
        )
        raise HTTPException(
            status_code=403, detail="Request blocked by threat detection policy"
        )
    elif risk_score >= 40:
        siem_logger.emit(
            "threat_detected_warning",
            "medium",
            {
                "ip": _client_ip(request),
                "path": request.url.path,
                "method": request.method,
                "service": service_name,
                "risk_score": risk_score,
                "reasons": reasons,
            },
        )

    content_type = response.headers.get("content-type", "")
    response_body: Optional[object]

    if "application/json" in content_type:
        try:
            response_body = response.json()
        except ValueError:
            response_body = response.text
    else:
        response_body = response.text

    if response.is_error:
        detail = (
            response_body
            if isinstance(response_body, (dict, list))
            else {"message": response_body}
        )
        raise HTTPException(status_code=response.status_code, detail=detail)

    # Add rate limit headers to response
    response_headers = {}
    if hasattr(request.state, "rate_limit_info"):
        info = request.state.rate_limit_info
        response_headers.update(
            {
                "X-RateLimit-Limit": str(info.get("limit", 0)),
                "X-RateLimit-Remaining": str(info.get("remaining", 0)),
                "X-RateLimit-Reset": str(info.get("reset", 0)),
                "X-Threat-Risk-Score": str(risk_score),
            }
        )
    if hasattr(request.state, "endpoint_rate_limit_info"):
        endpoint_info = request.state.endpoint_rate_limit_info
        response_headers.update(
            {
                "X-Endpoint-RateLimit-Limit": str(endpoint_info.get("limit", 0)),
                "X-Endpoint-RateLimit-Remaining": str(
                    endpoint_info.get("remaining", 0)
                ),
                "X-Endpoint-RateLimit-Reset": str(endpoint_info.get("reset", 0)),
            }
        )
    response_headers.update(_build_security_headers())

    if isinstance(response_body, (dict, list)):
        if cache_key and response.is_success:
            response_cache.set(cache_key, response_body)
            response_headers["X-Cache"] = "MISS"
        return JSONResponse(
            status_code=response.status_code,
            content=response_body,
            headers=response_headers,
        )

    return Response(
        content=response_body or "",
        status_code=response.status_code,
        media_type=content_type or "text/plain",
        headers=response_headers,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
