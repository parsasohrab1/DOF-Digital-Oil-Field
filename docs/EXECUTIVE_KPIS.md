# Executive KPIs — OGIM

**هدف:** شاخص‌های اجرایی برای پایش Latency، Uptime، Adoption و False Positive Rate.

## KPIهای اصلی

| KPI | هدف | منبع اندازه‌گیری |
|-----|------|------------------|
| **Latency (P95)** | < 100ms | `GET /kpi/summary` → `latency.p95_ms` |
| **Uptime** | ≥ 99.9% | `GET /kpi/summary` → `uptime.ratio` |
| **Adoption** | ≥ 5 feature فعال/ماه | `GET /kpi/summary` → `adoption.feature_hits` |
| **False Positive Rate** | ≤ 30% | `GET /kpi/summary` → `alert_quality.false_positive_rate` |

## Prometheus Metrics

- `ogim_kpi_api_latency_seconds` — histogram per service
- `ogim_kpi_system_uptime_ratio` — gauge
- `ogim_kpi_feature_usage_total` — counter per feature
- `ogim_kpi_alert_false_positive_total` — counter per severity

## Alert Rules

فایل: `infrastructure/prometheus/rules/executive-kpis.yml`

- `KPILatencyP95High` — P95 > 100ms
- `KPIUptimeLow` — uptime < 99.9%
- `KPIFalsePositiveRateHigh` — FP rate > 30%

## داشبورد

- Grafana: **OGIM APM Overview**
- Web UI: صفحه **APM** (`/performance`)

## API نمونه

```bash
curl http://localhost:8000/kpi/summary
curl http://localhost:8000/kpi/cache-stats
curl -X POST http://localhost:8000/kpi/feature-usage -H "Content-Type: application/json" -d "{\"feature\":\"dashboard\"}"
curl -X POST http://localhost:8000/kpi/cache/invalidate -H "Content-Type: application/json" -d "{}"
```

Web UI صفحه **APM** (`/performance`) adoption را از مسیرهای بازدیدشده (Layout → `feature-usage`) نیز تغذیه می‌کند.

جزئیات hardening: [PHASE3_HARDENING.md](PHASE3_HARDENING.md)
