import { useMemo, useState, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'
import {
  FIELD,
  STATUS_COLOR,
  STATUS_LABEL_FA,
  buildWellProductionForecasts,
  type WellProductionForecast,
} from '../data/dehloranField'
import './ProductionForecast.css'

type TabKey = 'decline' | 'watercut' | 'table'

export default function ProductionForecast() {
  const [tick, setTick] = useState(Date.now())
  const [tab, setTab] = useState<TabKey>('decline')
  const [selectedWell, setSelectedWell] = useState('DEH-01')

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 20000)
    return () => window.clearInterval(id)
  }, [])

  const forecasts = useMemo(() => buildWellProductionForecasts(tick), [tick])
  const selected = forecasts.find((f) => f.wellId === selectedWell) || forecasts[0]

  const summary = useMemo(() => {
    const avgDecline =
      forecasts.reduce((s, f) => s + f.declineAnnualPct, 0) / Math.max(1, forecasts.length)
    const avgWcRise =
      forecasts.reduce((s, f) => s + f.waterCutRise90d, 0) / Math.max(1, forecasts.length)
    const highDecline = forecasts.filter((f) => f.declineAnnualPct > 25).length
    const highWc = forecasts.filter((f) => f.waterCutIn90d > 60).length
    return {
      avgDecline: Math.round(avgDecline * 10) / 10,
      avgWcRise: Math.round(avgWcRise * 10) / 10,
      highDecline,
      highWc,
    }
  }, [forecasts])

  const compareOil = forecasts.map((f) => ({
    well: f.wellId.replace('DEH-', ''),
    now: f.currentOil,
    m3: f.oilIn90d,
    m12: f.series[12]?.oil ?? f.oilIn90d,
  }))

  const compareWc = forecasts.map((f) => ({
    well: f.wellId.replace('DEH-', ''),
    now: f.currentWaterCut,
    m3: f.waterCutIn90d,
    m12: f.series[12]?.waterCut ?? f.waterCutIn90d,
  }))

  return (
    <div className="pf-page" dir="rtl">
      <header className="pf-hero">
        <div>
          <p className="pf-client">{FIELD.clientFa}</p>
          <h2>پیش‌بینی تولید — {FIELD.nameFa}</h2>
          <p className="pf-meta">
            منحنی افت تولید و درصد آب تولیدی برای هر ۱۶ حلقه · افق ۱۲ ماه · نفت سنگین درجه سنگینی {FIELD.apiGravity}°
          </p>
        </div>
      </header>

      <div className="pf-kpis">
        <div className="pf-kpi">
          <span>میانگین افت سالانه</span>
          <strong>{summary.avgDecline}%</strong>
        </div>
        <div className="pf-kpi">
          <span>میانگین رشد درصد آب تولیدی در ۹۰ روز</span>
          <strong>+{summary.avgWcRise}%</strong>
        </div>
        <div className="pf-kpi warn">
          <span>چاه با افت بالا (&gt;۲۵٪/سال)</span>
          <strong>{summary.highDecline}</strong>
        </div>
        <div className="pf-kpi warn">
          <span>چاه با درصد آب تولیدی پیش‌بینی &gt;۶۰٪</span>
          <strong>{summary.highWc}</strong>
        </div>
      </div>

      <div className="pf-tabs">
        <button
          type="button"
          className={tab === 'decline' ? 'active' : ''}
          onClick={() => setTab('decline')}
        >
          افت تولید
        </button>
        <button
          type="button"
          className={tab === 'watercut' ? 'active' : ''}
          onClick={() => setTab('watercut')}
        >
          آب تولیدی
        </button>
        <button
          type="button"
          className={tab === 'table' ? 'active' : ''}
          onClick={() => setTab('table')}
        >
          جدول همه چاه‌ها
        </button>
      </div>

      <div className="pf-well-picker">
        <label>انتخاب چاه:</label>
        <div className="pf-well-chips">
          {forecasts.map((f) => (
            <button
              key={f.wellId}
              type="button"
              className={selectedWell === f.wellId ? 'active' : ''}
              style={{ borderColor: STATUS_COLOR[f.status] }}
              onClick={() => setSelectedWell(f.wellId)}
            >
              {f.wellId.replace('DEH-', '')}
            </button>
          ))}
        </div>
      </div>

      {selected && (tab === 'decline' || tab === 'watercut') && (
        <section className="pf-detail">
          <div className="pf-detail-head">
            <h3>
              {selected.nameFa} ({selected.wellId})
              <em style={{ color: STATUS_COLOR[selected.status] }}>
                {STATUS_LABEL_FA[selected.status]}
              </em>
            </h3>
            <div className="pf-detail-stats">
              <span>
                نفت فعلی: <b>{selected.currentOil} bbl/d</b>
              </span>
              <span>
                درصد آب تولیدی فعلی: <b>{selected.currentWaterCut}%</b>
              </span>
              <span>
                افت ۳۰روزه: <b>{selected.declinePct30d}%</b>
              </span>
              <span>
                افت سالانه پیش‌بینی: <b>{selected.declineAnnualPct}%</b>
              </span>
              <span>
                درصد آب تولیدی در ۹۰ روز: <b>{selected.waterCutIn90d}%</b> (+{selected.waterCutRise90d})
              </span>
            </div>
          </div>

          {tab === 'decline' && (
            <>
              <div className="pf-chart-card">
                <h4>منحنی زوال تولید نفت — ۱۲ ماه</h4>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={selected.series}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" stroke="#888" />
                    <YAxis stroke="#888" />
                    <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #ccc', color: '#111' }} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="oil"
                      name="دبی نفت (bbl/d)"
                      stroke="#42a5f5"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="pf-chart-card">
                <h4>مقایسه افت تولید همه چاه‌ها (اکنون / ۹۰روز / ۱۲ماه)</h4>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={compareOil}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="well" stroke="#888" tick={{ fontSize: 11 }} />
                    <YAxis stroke="#888" />
                    <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #ccc', color: '#111' }} />
                    <Legend />
                    <Bar dataKey="now" name="اکنون" fill="#66bb6a" />
                    <Bar dataKey="m3" name="۹۰ روز" fill="#42a5f5" />
                    <Bar dataKey="m12" name="۱۲ ماه" fill="#ffa726" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}

          {tab === 'watercut' && (
            <>
              <div className="pf-chart-card">
                <h4>پیش‌بینی درصد آب تولیدی — ۱۲ ماه</h4>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={selected.series}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" stroke="#888" />
                    <YAxis stroke="#888" domain={[0, 100]} unit="%" />
                    <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #ccc', color: '#111' }} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="waterCut"
                      name="درصد آب تولیدی %"
                      stroke="#ab47bc"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="water"
                      name="دبی آب (bbl/d)"
                      stroke="#26c6da"
                      strokeDasharray="4 3"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="pf-chart-card">
                <h4>مقایسه درصد آب تولیدی همه چاه‌ها (اکنون / ۹۰روز / ۱۲ماه)</h4>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={compareWc}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="well" stroke="#888" tick={{ fontSize: 11 }} />
                    <YAxis stroke="#888" domain={[0, 100]} />
                    <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #ccc', color: '#111' }} />
                    <Legend />
                    <Bar dataKey="now" name="اکنون %" fill="#7e57c2" />
                    <Bar dataKey="m3" name="۹۰ روز %" fill="#ab47bc" />
                    <Bar dataKey="m12" name="۱۲ ماه %" fill="#ec407a" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </section>
      )}

      {tab === 'table' && <ForecastTable forecasts={forecasts} onSelect={setSelectedWell} />}
    </div>
  )
}

function ForecastTable({
  forecasts,
  onSelect,
}: {
  forecasts: WellProductionForecast[]
  onSelect: (id: string) => void
}) {
  return (
    <div className="pf-table-card">
      <h3>خلاصه پیش‌بینی هر چاه</h3>
      <div className="pf-table-wrap">
        <table>
          <thead>
            <tr>
              <th>چاه</th>
              <th>وضعیت</th>
              <th>نفت فعلی</th>
              <th>نفت ۹۰روز</th>
              <th>نفت ۱۲ماه</th>
              <th>افت سالانه</th>
              <th>درصد آب فعلی</th>
              <th>درصد آب ۹۰روز</th>
              <th>درصد آب ۱۲ماه</th>
              <th>Δ درصد آب ۹۰روز</th>
            </tr>
          </thead>
          <tbody>
            {forecasts.map((f) => (
              <tr key={f.wellId} onClick={() => onSelect(f.wellId)}>
                <td>
                  <strong>{f.wellId}</strong>
                  <div className="sub">{f.nameFa}</div>
                </td>
                <td style={{ color: STATUS_COLOR[f.status] }}>{STATUS_LABEL_FA[f.status]}</td>
                <td>{f.currentOil}</td>
                <td>{f.oilIn90d}</td>
                <td>{f.series[12]?.oil}</td>
                <td className={f.declineAnnualPct > 25 ? 'warn' : ''}>{f.declineAnnualPct}%</td>
                <td>{f.currentWaterCut}%</td>
                <td>{f.waterCutIn90d}%</td>
                <td>{f.series[12]?.waterCut}%</td>
                <td className={f.waterCutRise90d > 4 ? 'warn' : ''}>+{f.waterCutRise90d}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
