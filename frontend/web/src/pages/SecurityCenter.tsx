import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'
import { securityAPI } from '../api/services'
import './SecurityCenter.css'

const SEVERITY_CLASS: Record<string, string> = {
  critical: 'sev-critical',
  high: 'sev-high',
  medium: 'sev-medium',
  low: 'sev-low',
}

const SEV_COLORS: Record<string, string> = {
  critical: '#f44336',
  high: '#ff9800',
  medium: '#ffc107',
  low: '#4caf50',
  info: '#2196f3',
}

function buildTrendData(events: any[]) {
  const buckets: Record<string, Record<string, number>> = {}
  for (const ev of events) {
    const ts = ev.timestamp?.slice(0, 16) || 'unknown'
    if (!buckets[ts]) buckets[ts] = { critical: 0, high: 0, medium: 0, low: 0 }
    const sev = ev.severity || 'low'
    buckets[ts][sev] = (buckets[ts][sev] || 0) + 1
  }
  return Object.entries(buckets)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([time, counts]) => ({ time: time.slice(11) || time, ...counts }))
}

function buildTypePie(events: any[]) {
  const counts: Record<string, number> = {}
  for (const ev of events) {
    const t = ev.event_type || 'other'
    counts[t] = (counts[t] || 0) + 1
  }
  return Object.entries(counts).map(([name, value]) => ({ name, value }))
}

const PIE_COLORS = ['#2196f3', '#f44336', '#ff9800', '#4caf50', '#9c27b0', '#00bcd4', '#795548']

export default function SecurityCenter() {
  const statusQuery = useQuery({
    queryKey: ['security-status'],
    queryFn: () => securityAPI.getThreatStatus(),
    refetchInterval: 15000,
  })

  const eventsQuery = useQuery({
    queryKey: ['siem-events'],
    queryFn: () => securityAPI.getSiemEvents(200),
    refetchInterval: 10000,
  })

  const status = statusQuery.data
  const events = eventsQuery.data?.events || []
  const summary = eventsQuery.data?.summary || status?.siem_summary

  const trendData = useMemo(() => buildTrendData(events), [events])
  const typePieData = useMemo(() => buildTypePie(events), [events])

  const sevCounts = useMemo(() => {
    const c: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 }
    events.forEach((ev: any) => { c[ev.severity] = (c[ev.severity] || 0) + 1 })
    return c
  }, [events])

  return (
    <div className="sec-page">
      <h2>Security Center</h2>
      <p className="sec-subtitle">Zero Trust, SIEM events, and threat detection</p>

      <div className="sec-cards">
        <div className="sec-card">
          <strong>Zero Trust</strong>
          <span className={status?.zero_trust_enforced ? 'on' : 'off'}>
            {status?.zero_trust_enforced ? 'Enforced' : 'Disabled'}
          </span>
          {status?.zero_trust_networks?.length > 0 && (
            <small>Networks: {status.zero_trust_networks.join(', ')}</small>
          )}
        </div>
        <div className="sec-card">
          <strong>Threat Block Threshold</strong>
          <span>{status?.threat_block_threshold ?? 70}</span>
        </div>
        <div className="sec-card">
          <strong>API Hardening</strong>
          <span className={status?.api_security_hardening ? 'on' : 'off'}>
            {status?.api_security_hardening ? 'Active' : 'Inactive'}
          </span>
        </div>
        <div className="sec-card">
          <strong>SIEM Events (buffered)</strong>
          <span>{summary?.total_buffered ?? 0}</span>
        </div>
      </div>

      {/* Severity KPI badges */}
      <div className="sec-sev-badges">
        {Object.entries(sevCounts).map(([sev, count]) => (
          <div key={sev} className="sec-sev-badge" style={{ borderColor: SEV_COLORS[sev] }}>
            <span className="sec-sev-count" style={{ color: SEV_COLORS[sev] }}>{count}</span>
            <span className="sec-sev-label">{sev}</span>
          </div>
        ))}
      </div>

      {/* Charts row */}
      {events.length > 0 && (
        <div className="sec-charts">
          <section className="sec-panel sec-chart-panel">
            <h3>Severity Trend</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={trendData}>
                <XAxis dataKey="time" tick={{ fill: '#555', fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fill: '#555', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #ccc', color: '#111' }} />
                <Bar dataKey="critical" stackId="a" fill={SEV_COLORS.critical} />
                <Bar dataKey="high" stackId="a" fill={SEV_COLORS.high} />
                <Bar dataKey="medium" stackId="a" fill={SEV_COLORS.medium} />
                <Bar dataKey="low" stackId="a" fill={SEV_COLORS.low} />
              </BarChart>
            </ResponsiveContainer>
          </section>

          <section className="sec-panel sec-chart-panel">
            <h3>Event Type Breakdown</h3>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={typePieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {typePieData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #ccc', color: '#111' }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </section>
        </div>
      )}

      <section className="sec-panel">
        <h3>Recent SIEM Events</h3>
        {eventsQuery.isLoading ? <p>Loading events...</p> : events.length === 0 ? (
          <p className="sec-muted">No security events recorded yet.</p>
        ) : (
          <div className="sec-events">
            {events.slice(0, 50).map((event: any, i: number) => (
              <div key={i} className={`sec-event ${SEVERITY_CLASS[event.severity] || ''}`}>
                <div className="sec-event-header">
                  <strong>{event.event_type}</strong>
                  <span className="sec-sev">{event.severity}</span>
                </div>
                <div className="sec-event-time">{event.timestamp}</div>
                <pre>{JSON.stringify(event.payload, null, 2)}</pre>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="sec-panel">
        <h3>Threat Detection Rules</h3>
        <ul className="sec-rules">
          <li>High request rate per IP (&gt;120 req / 5 min) — risk +45</li>
          <li>High request rate per user (&gt;80 req / 5 min) — risk +35</li>
          <li>Auth failures (401/403) — risk +20</li>
          <li>Known attack patterns (SQLi, sqlmap UA) — risk +60</li>
          <li>Requests blocked when risk score ≥ threshold</li>
        </ul>
      </section>
    </div>
  )
}
