# Phase 3 — Hardening: Tests, Docs, Optimization, API Security, KPIs

**Status:** Implemented  
**Date:** July 2026

## Goals

| Area | Target | Status |
|------|--------|--------|
| **Tests** | Coverage ≥ 85% on security/KPI/cache modules | ✅ `pytest.ini` `--cov-fail-under=85` |
| **Documentation** | Operator + developer guides for Phase 3 | ✅ This doc + linked guides |
| **Optimization** | Response TTL cache + cache stats/invalidate | ✅ Gateway + `/kpi/cache-*` |
| **API Security** | Input hardening, Zero Trust, SIEM, threat scoring | ✅ Gateway middleware |
| **KPIs** | Latency / Uptime / Adoption / FP rate | ✅ `/kpi/summary` + APM UI |

---

## 1. Tests (>85%)

Coverage is enforced on:

- `shared.security`
- `shared.security_alerts`
- `shared.threat_detection`
- `shared.input_validation`
- `shared.response_cache`
- `shared.kpi_metrics`

```bash
cd backend
python -m pytest tests/unit tests/test_api_gateway.py -q
```

Key test files:

- `tests/unit/test_*_unit.py` — pure unit coverage
- `tests/test_api_gateway.py` — proxy auth, XSS/SQLi blocking, body/query limits, KPI + SIEM endpoints
- `tests/integration/test_security_alerts_integration.py` — login-failure alerting

---

## 2. Documentation map

| Doc | Purpose |
|-----|---------|
| [TESTING.md](TESTING.md) | How to run pytest / coverage |
| [GATEWAY_SECURITY.md](GATEWAY_SECURITY.md) | Rate limit, mTLS, gateway controls |
| [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) | Ops security checklist |
| [PERFORMANCE_TUNING.md](PERFORMANCE_TUNING.md) | DB pools, cache TTL, connection limits |
| [EXECUTIVE_KPIS.md](EXECUTIVE_KPIS.md) | KPI targets and Prometheus names |
| [SUCCESS_METRICS_AND_KPIS.md](SUCCESS_METRICS_AND_KPIS.md) | Full metric definitions |
| [OBSERVABILITY.md](OBSERVABILITY.md) | OTel / Tempo / Grafana |

---

## 3. Optimization

- **TTL response cache** (`shared.response_cache.TTLResponseCache`) on high-read GET paths
- Config: `CACHE_TTL_SECONDS`, `CACHE_MAX_ENTRIES`
- Monitor: `GET /kpi/cache-stats` → hits / misses / hit_rate
- Ops: `POST /kpi/cache/invalidate` with optional `{ "prefix": "..." }`
- Keep-alive / max connections: see `PERFORMANCE_TUNING.md`
- Real-time path: WebSocket primary, SSE fallback (reduces polling load)

---

## 4. API Security

Enabled by default (`API_SECURITY_ENABLE_INPUT_HARDENING=true`):

| Control | Behavior |
|---------|----------|
| XSS / SQLi patterns | Block query + JSON body (`400`) |
| Max body size | `API_SECURITY_MAX_BODY_BYTES` → `413` |
| Max query params | `API_SECURITY_MAX_QUERY_PARAMS` → `400` |
| Param/path length | `API_SECURITY_MAX_PARAM_LENGTH` |
| Security headers | nosniff, DENY frame, CSP, Referrer-Policy |
| Zero Trust | Role + optional network allowlist |
| Threat scoring | IP/user rate, auth failures, attack UA → SIEM |
| Login lockout helpers | `shared.security_alerts` |

Dashboards: **Security Center** (`/security`), SIEM via `GET /security/siem/events`.

---

## 5. KPIs

| KPI | Target | API field |
|-----|--------|-----------|
| Latency P95 | < 100 ms | `latency.p95_ms` |
| Uptime | ≥ 99.9% | `uptime.ratio` |
| Adoption | ≥ 3–5 features | `adoption.feature_hits` |
| False positive rate | ≤ 30% | `alert_quality.false_positive_rate` |

Endpoints:

```bash
GET  /kpi/summary
GET  /kpi/cache-stats
POST /kpi/feature-usage   # { "feature": "dashboard" }
POST /kpi/cache/invalidate
```

Frontend:

- **APM** page (`/performance`) shows live executive KPIs
- **Layout** records page visits via `POST /kpi/feature-usage`

Prometheus: `ogim_kpi_*` metrics (see `EXECUTIVE_KPIS.md`).

---

## Verification checklist

- [ ] `pytest` unit + gateway passes with coverage ≥ 85%
- [ ] `GET /kpi/summary` returns latency/uptime/adoption/alert_quality
- [ ] Suspicious payload blocked (`<script>`, `OR 1=1`)
- [ ] Security Center shows SIEM events
- [ ] Cache stats move after repeated GETs on cacheable routes
