import { useQuery } from '@tanstack/react-query'
import { useWebSocket } from '../hooks/useWebSocket'
import { kpiAPI } from '../api/services'
import './Performance.css'

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'http://localhost:3001'

function statusClass(status?: string): string {
  return status === 'ok' ? 'kpi-ok' : status === 'warning' ? 'kpi-warn' : 'kpi-neutral'
}

function transportFa(transport: string) {
  if (transport === 'websocket') return 'وب‌سوکت'
  if (transport === 'sse') return 'رویداد سمت سرور'
  if (transport === 'simulation') return 'زنده محلی (بدون اینترنت)'
  if (transport === 'disconnected') return 'در این صفحه مشترک نیست'
  return transport
}

export default function Performance() {
  const { transport } = useWebSocket({ enabled: false })

  const kpiQuery = useQuery({
    queryKey: ['kpi-summary'],
    queryFn: () => kpiAPI.getSummary(),
    refetchInterval: 30000,
  })

  const cacheQuery = useQuery({
    queryKey: ['kpi-cache'],
    queryFn: () => kpiAPI.getCacheStats(),
    refetchInterval: 30000,
  })

  const kpi = kpiQuery.data
  const cache = cacheQuery.data

  const panels = [
    { title: 'نرخ درخواست', desc: 'service_requests_total به‌ازای سرویس' },
    { title: 'نرخ خطا', desc: 'service_request_errors_total به‌ازای سرویس' },
    { title: 'تأخیر صدک ۹۵', desc: 'service_request_latency_seconds (درگاه برنامه‌نویسی)' },
    { title: 'استنتاج یادگیری ماشین', desc: 'ml_inference_latency_seconds به‌ازای نوع مدل' },
  ]

  return (
    <div className="perf-page" dir="rtl">
      <div className="perf-header">
        <h2>عملکرد سامانه و شاخص‌های اجرایی</h2>
        <a href={GRAFANA_URL} target="_blank" rel="noopener noreferrer" className="perf-grafana-link">
          باز کردن داشبورد گرافانا
        </a>
      </div>

      <div className="kpi-grid">
        <div className={`kpi-card ${statusClass(kpi?.latency?.status)}`}>
          <strong>تأخیر صدک ۹۵</strong>
          <span className="kpi-value">{kpi?.latency?.p95_ms ?? '—'} ms</span>
          <small>هدف: &lt; {kpi?.latency?.target_p95_ms ?? 100} ms</small>
        </div>
        <div className={`kpi-card ${statusClass(kpi?.uptime?.status)}`}>
          <strong>دسترس‌پذیری</strong>
          <span className="kpi-value">{kpi?.uptime?.ratio != null ? `${(kpi.uptime.ratio * 100).toFixed(2)}%` : '—'}</span>
          <small>هدف: ≥ {(kpi?.uptime?.target_ratio ?? 0.999) * 100}%</small>
        </div>
        <div className={`kpi-card ${statusClass(kpi?.adoption?.status)}`}>
          <strong>پذیرش قابلیت‌ها</strong>
          <span className="kpi-value">{kpi?.adoption?.total_events ?? 0} رویداد</span>
          <small>{Object.keys(kpi?.adoption?.feature_hits ?? {}).length} قابلیت استفاده‌شده</small>
        </div>
        <div className={`kpi-card ${statusClass(kpi?.alert_quality?.status)}`}>
          <strong>نرخ هشدار کاذب</strong>
          <span className="kpi-value">
            {kpi?.alert_quality?.false_positive_rate != null
              ? `${(kpi.alert_quality.false_positive_rate * 100).toFixed(1)}%`
              : '—'}
          </span>
          <small>هدف: ≤ {(kpi?.alert_quality?.target_max_false_positive_rate ?? 0.3) * 100}%</small>
        </div>
      </div>

      <div className="perf-stack">
        <section className="perf-card">
          <h3>کش پاسخ درگاه</h3>
          <p>نرخ برخورد: {cache?.hit_rate != null ? `${(cache.hit_rate * 100).toFixed(1)}%` : '—'}</p>
          <p>ورودی‌ها: {cache?.entries ?? 0} | برخورد: {cache?.hits ?? 0} | ازدست‌رفته: {cache?.misses ?? 0}</p>
        </section>

        <section className="perf-card">
          <h3>انتقال بلادرنگ</h3>
          <p className={`perf-transport ${transport}`}>
            {transportFa(transport)}
          </p>
        </section>

        <section className="perf-card full">
          <h3>پشته مشاهده‌پذیری</h3>
          <ul className="perf-list">
            <li><strong>OpenTelemetry</strong> → Tempo</li>
            <li><strong>Prometheus</strong> + هشدارهای executive-kpis.yml</li>
            <li><strong>گرافانا</strong> — نمای کلی پایش عملکرد سامانه هوشمندسازی میادین</li>
            <li><strong>امنیت</strong> — اعتماد صفر، مدیریت رویداد امنیتی، تشخیص تهدید</li>
          </ul>
        </section>

        <section className="perf-card full">
          <h3>پنل‌های شاخص کلیدی</h3>
          <div className="perf-panels-grid">
            {panels.map((p) => (
              <div key={p.title} className="perf-panel-item">
                <strong>{p.title}</strong>
                <span>{p.desc}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
