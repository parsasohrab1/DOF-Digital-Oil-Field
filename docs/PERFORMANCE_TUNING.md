# Performance Tuning — OGIM

راهنمای بهینه‌سازی DB / API / Cache برای بار بالا.

## 1. Database Connection Pools

| متغیر | پیش‌فرض | توضیح |
|-------|---------|--------|
| `DATABASE_POOL_SIZE` | 20 | pool PostgreSQL |
| `DATABASE_MAX_OVERFLOW` | 40 | اتصالات اضافی |
| `TIMESCALE_CONNECTION_POOL_SIZE` | 30 | pool TimescaleDB |
| `DATABASE_POOL_RECYCLE_SECONDS` | 1800 | بازیافت اتصال |

## 2. API Gateway

| متغیر | پیش‌فرض | توضیح |
|-------|---------|--------|
| `API_GATEWAY_HTTP_KEEPALIVE_CONNECTIONS` | 100 | keep-alive |
| `API_GATEWAY_HTTP_MAX_CONNECTIONS` | 300 | سقف اتصال |
| `CACHE_TTL_SECONDS` | 30 | TTL کش GET |
| `CACHE_MAX_ENTRIES` | 2048 | حداکثر ورودی کش |

### مسیرهای cache شده

- `/api/reporting/bi/metadata`
- `/api/reporting/workflows/templates`
- `/api/digital-twin/wells`
- `/api/tag-catalog/tags`

پایش: `GET /kpi/cache-stats` — header `X-Cache: HIT|MISS`

باطل‌سازی: `POST /kpi/cache/invalidate` با بدنه اختیاری `{ "prefix": "..." }` (بدون prefix کل کش پاک می‌شود).

## 3. Rate Limiting & Security

- `RATE_LIMIT_ENABLED=true`
- `API_SECURITY_ENABLE_INPUT_HARDENING=true`
- ماژول: `backend/shared/input_validation.py`

## 4. Production

1. Redis برای rate limit در multi-replica
2. Read replica برای analytics
3. TimescaleDB compression
4. Horizontal scaling برای gateway و ingestion
