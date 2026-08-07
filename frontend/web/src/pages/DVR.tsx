import { useMemo, useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import apiClient from '../api/client'
import { FIELD, DEHLORAN_WELLS } from '../data/dehloranField'
import {
  buildDehloranDvrQuality,
  buildDehloranValidation,
  buildDehloranOutliers,
  buildDehloranReconciliation,
  dvrFieldSummary,
  type DvrQualityScore,
} from '../data/dehloranDvr'
import './DVR.css'

export default function DVR() {
  const [tick, setTick] = useState(Date.now())
  const [wellFilter, setWellFilter] = useState<string>('ALL')
  const [selectedSensor, setSelectedSensor] = useState<string>('')

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 15000)
    return () => window.clearInterval(id)
  }, [])

  const localQuality = useMemo(() => buildDehloranDvrQuality(tick), [tick])

  const { data: qualityScores = localQuality, isLoading } = useQuery({
    queryKey: ['dvr-quality-dehloran', tick],
    queryFn: async () => {
      try {
        const response = await apiClient.get('/api/dvr/quality')
        const remote = response.data as DvrQualityScore[]
        if (Array.isArray(remote) && remote.length >= 8) return remote
      } catch {
        /* use Dehloran synthetic DVR */
      }
      return buildDehloranDvrQuality(tick)
    },
    initialData: localQuality,
    refetchInterval: 30000,
    retry: 0,
  })

  const filtered = useMemo(() => {
    if (wellFilter === 'ALL') return qualityScores
    return qualityScores.filter((s) => s.well_id === wellFilter || s.sensor_id.startsWith(wellFilter))
  }, [qualityScores, wellFilter])

  useEffect(() => {
    if (!selectedSensor && filtered.length > 0) {
      setSelectedSensor(filtered[0].sensor_id)
    }
  }, [filtered, selectedSensor])

  const summary = useMemo(() => dvrFieldSummary(qualityScores), [qualityScores])
  const reconciliation = useMemo(() => buildDehloranReconciliation(tick), [tick])

  const validation = useMemo(
    () => (selectedSensor ? buildDehloranValidation(selectedSensor, tick) : null),
    [selectedSensor, tick]
  )

  const outliers = useMemo(
    () => (selectedSensor ? buildDehloranOutliers(selectedSensor, tick) : []),
    [selectedSensor, tick]
  )

  const chartData = useMemo(() => {
    const byWell = new Map<string, number[]>()
    for (const s of qualityScores) {
      const wid = s.well_id || s.sensor_id.split('.')[0]
      if (!byWell.has(wid)) byWell.set(wid, [])
      byWell.get(wid)!.push(s.quality_score)
    }
    return Array.from(byWell.entries())
      .map(([well, scores]) => ({
        well,
        quality: Number(((scores.reduce((a, b) => a + b, 0) / scores.length) * 100).toFixed(1)),
      }))
      .sort((a, b) => a.well.localeCompare(b.well))
  }, [qualityScores])

  if (isLoading && !qualityScores.length) {
    return <div className="loading">در حال بارگذاری اعتبارسنجی و تطبیق داده دهلران…</div>
  }

  return (
    <div className="dvr-page deh-dvr" dir="rtl">
      <header className="deh-dvr-hero">
        <div>
          <p className="deh-dvr-client">{FIELD.clientFa}</p>
          <h2>اعتبارسنجی و تطبیق داده — {FIELD.nameFa}</h2>
          <p className="deh-dvr-meta">
            کنترل کیفیت سنسورهای ۱۶ حلقه · همخوانی با دبی‌سنج مجازی · موازنه جرمی تولید نفت سنگین درجه سنگینی{' '}
            {FIELD.apiGravity}°
          </p>
        </div>
      </header>

      <div className="deh-dvr-kpis">
        <div className="deh-dvr-kpi">
          <span>میانگین کیفیت داده</span>
          <strong>{summary.avgQuality}%</strong>
        </div>
        <div className="deh-dvr-kpi">
          <span>سنسورهای پایش‌شده</span>
          <strong>{summary.sensors}</strong>
          <small>{summary.wells} چاه</small>
        </div>
        <div className="deh-dvr-kpi warn">
          <span>کیفیت &lt; ۹۰٪</span>
          <strong>{summary.below90}</strong>
        </div>
        <div className="deh-dvr-kpi bad">
          <span>کیفیت &lt; ۷۰٪</span>
          <strong>{summary.below70}</strong>
        </div>
        <div className="deh-dvr-kpi">
          <span>عدم‌تراز میدان (نفت)</span>
          <strong>{reconciliation.field.field_imbalance_pct}%</strong>
          <small>{reconciliation.field.material_wells} چاه با عدم‌تراز مادی</small>
        </div>
      </div>

      <div className="dvr-grid">
        <div className="dvr-card deh-dvr-card span-2">
          <h3>کیفیت داده به‌ازای چاه (میانگین سنسورها)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="well" stroke="#888" tick={{ fontSize: 11 }} />
              <YAxis stroke="#888" domain={[0, 100]} />
              <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #ccc', color: '#111' }} />
              <Legend />
              <Bar dataKey="quality" name="کیفیت %" fill="#42a5f5" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="dvr-card deh-dvr-card span-2">
          <div className="deh-dvr-toolbar">
            <h3>جدول کیفیت سنسورهای دهلران</h3>
            <select value={wellFilter} onChange={(e) => setWellFilter(e.target.value)}>
              <option value="ALL">همه ۱۶ چاه</option>
              {DEHLORAN_WELLS.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.nameFa} ({w.id})
                </option>
              ))}
            </select>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>سنسور</th>
                  <th>چاه</th>
                  <th>متغیر</th>
                  <th>کیفیت</th>
                  <th>کامل بودن</th>
                  <th>دقت</th>
                  <th>تازگی</th>
                  <th>سازگاری</th>
                  <th>اعتبار</th>
                  <th>مسائل</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 64).map((score) => (
                  <tr
                    key={score.sensor_id}
                    className={selectedSensor === score.sensor_id ? 'selected-row' : ''}
                    onClick={() => setSelectedSensor(score.sensor_id)}
                  >
                    <td>{score.sensor_id}</td>
                    <td>{score.well_id}</td>
                    <td>{score.variable_fa || '—'}</td>
                    <td
                      className={
                        score.quality_score > 0.9
                          ? 'good'
                          : score.quality_score > 0.7
                            ? 'warning'
                            : 'bad'
                      }
                    >
                      {(score.quality_score * 100).toFixed(1)}%
                    </td>
                    <td>{(score.completeness * 100).toFixed(0)}%</td>
                    <td>{(score.accuracy * 100).toFixed(0)}%</td>
                    <td>{(score.timeliness * 100).toFixed(0)}%</td>
                    <td>{(score.consistency * 100).toFixed(0)}%</td>
                    <td>{(score.validity * 100).toFixed(0)}%</td>
                    <td className="issues-cell">
                      {score.issues?.length ? score.issues.join('؛ ') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="dvr-card deh-dvr-card">
          <h3>اعتبارسنجی نقطه داده</h3>
          <select
            value={selectedSensor}
            onChange={(e) => setSelectedSensor(e.target.value)}
            className="sensor-select"
          >
            {filtered.map((s) => (
              <option key={s.sensor_id} value={s.sensor_id}>
                {s.sensor_id} — {s.variable_fa}
              </option>
            ))}
          </select>
          {validation && (
            <div className="validation-info">
              <div className={`validation-status ${validation.is_valid ? 'valid' : 'invalid'}`}>
                وضعیت: {validation.is_valid ? 'معتبر' : 'نامعتبر'}
              </div>
              <div>
                مقدار: <b>{validation.value}</b> {validation.unit}
              </div>
              <div>امتیاز اعتبارسنجی: {(validation.validation_score * 100).toFixed(1)}%</div>
              <ul className="rule-list">
                {validation.rule_checks.map((r, i) => (
                  <li key={i} className={r.passed ? 'ok' : 'fail'}>
                    <strong>{r.rule}</strong> — {r.detail}
                  </li>
                ))}
              </ul>
              {validation.violations.length > 0 && (
                <div className="violations">
                  <strong>نقض‌ها:</strong>
                  <ul>
                    {validation.violations.map((v, i) => (
                      <li key={i}>{v}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="dvr-card deh-dvr-card">
          <h3>تشخیص نقاط پرت</h3>
          {outliers.length === 0 ? (
            <p className="deh-dvr-muted">نقطه پرت معناداری برای این سنسور ثبت نشده است.</p>
          ) : (
            <div className="outliers-list">
              {outliers.slice(0, 8).map((o, i) => (
                <div key={i} className={`outlier-item sev-${o.severity}`}>
                  <div>
                    <b>{o.value}</b> · Z={o.outlier_score} · {severityFaDvr(o.severity)}
                  </div>
                  <div>بازه مورد انتظار: {o.expected_range}</div>
                  <div>{o.reason_fa}</div>
                  <div className="ts">{new Date(o.timestamp).toLocaleString('fa-IR')}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="dvr-card deh-dvr-card span-2">
          <h3>تطبیق تولید — اندازه‌گیری در برابر دبی‌سنج مجازی</h3>
          <p className="deh-dvr-muted">
            نفت اندازه‌گیری‌شده میدان:{' '}
            <b>{reconciliation.field.measured_oil_total.toLocaleString()} bbl/d</b> · دبی‌سنج مجازی:{' '}
            <b>{reconciliation.field.vfm_oil_total.toLocaleString()} bbl/d</b> · تطبیق‌شده:{' '}
            <b>{reconciliation.field.reconciled_oil_total.toLocaleString()} bbl/d</b>
          </p>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>چاه</th>
                  <th>نفت اندازه‌گیری</th>
                  <th>دبی‌سنج مجازی</th>
                  <th>تطبیق‌شده</th>
                  <th>عدم‌تراز %</th>
                  <th>درصد آب اندازه‌گیری</th>
                  <th>درصد آب تطبیق</th>
                  <th>وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {reconciliation.wells.map((w) => (
                  <tr key={w.well_id}>
                    <td>{w.well_id}</td>
                    <td>{w.measured_oil}</td>
                    <td>{w.vfm_oil}</td>
                    <td>{w.reconciled_oil}</td>
                    <td
                      className={
                        w.status === 'material' ? 'bad' : w.status === 'minor' ? 'warning' : 'good'
                      }
                    >
                      {w.imbalance_pct}%
                    </td>
                    <td>{w.water_cut_measured}%</td>
                    <td>{w.water_cut_reconciled}%</td>
                    <td>{statusFa(w.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

function statusFa(s: string) {
  if (s === 'balanced') return 'متوازن'
  if (s === 'minor') return 'جزئی'
  return 'مادی'
}

function severityFaDvr(s: string) {
  if (s === 'critical') return 'بحرانی'
  if (s === 'warning') return 'هشدار'
  if (s === 'info') return 'اطلاع'
  return s
}