import { useMemo, useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts'
import { alertAPI } from '../api/services'
import { transportLabelFa } from '../api/offlineMode'
import { getDehloranAlerts } from '../data/dehloranAlerts'
import { useWebSocket } from '../hooks/useWebSocket'
import {
  FIELD,
  DEHLORAN_WELLS,
  SENSOR_VARIABLES,
  STATUS_COLOR,
  STATUS_LABEL_FA,
  getDehloranLiveState,
  fieldTotals,
  waterCutForecast,
  declineForecast,
  type WellLiveState,
  type WellHealthStatus,
} from '../data/dehloranField'
import {
  CONTROLLABLE_VARS,
  defaultControls,
  computeProductionImpact,
  autoPilotStep,
  applyImpactToOil,
  applyImpactToWaterCut,
  type ControlState,
  type ControllableKey,
  type AutoPilotAction,
} from '../data/autoPilot'
import './Dashboard.css'

export default function Dashboard() {
  const [tick, setTick] = useState(Date.now())
  const [selectedWell, setSelectedWell] = useState<string>(DEHLORAN_WELLS[0].id)
  const { transport } = useWebSocket({ enabled: true })

  const [controls, setControls] = useState<ControlState>(() => defaultControls())
  const [autoPilotOn, setAutoPilotOn] = useState(false)
  const [apStatus, setApStatus] = useState<'idle' | 'stable' | 'recovering' | 'declined'>('idle')
  const [apLog, setApLog] = useState<AutoPilotAction[]>([])
  const controlsRef = useRef(controls)
  controlsRef.current = controls

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 12000)
    return () => window.clearInterval(id)
  }, [])

  // Auto Pilot: هر ۲٫۵ثانیه متغیرهای منحرف را به‌سمت بهینه برمی‌گرداند
  useEffect(() => {
    if (!autoPilotOn) {
      setApStatus('idle')
      return
    }
    const id = window.setInterval(() => {
      const step = autoPilotStep(controlsRef.current, { aggressiveness: 0.28 })
      setControls(step.controls)
      setApStatus(step.status)
      if (step.actions.length) {
        setApLog((prev) => [...step.actions, ...prev].slice(0, 24))
      }
    }, 2500)
    return () => window.clearInterval(id)
  }, [autoPilotOn])

  const setControl = useCallback((key: ControllableKey, value: number) => {
    setControls((prev) => ({ ...prev, [key]: value }))
  }, [])

  const resetControls = useCallback(() => {
    setControls(defaultControls())
    setApLog([])
    setApStatus(autoPilotOn ? 'stable' : 'idle')
  }, [autoPilotOn])

  const baseWells = useMemo(() => getDehloranLiveState(tick), [tick])
  const impact = useMemo(() => computeProductionImpact(controls), [controls])

  const wells = useMemo(() => {
    return baseWells.map((w) => {
      if (w.status === 'offline') return w
      const oilRate = applyImpactToOil(w.oilRate, impact)
      const waterCut = applyImpactToWaterCut(w.waterCut, impact)
      const waterRate = Math.round((oilRate * waterCut) / Math.max(1, 100 - waterCut))
      return {
        ...w,
        oilRate,
        waterCut,
        waterRate,
        vfmOilRate: applyImpactToOil(w.vfmOilRate, impact),
        gasRate: Math.round(w.gasRate * (0.92 + impact.oilFactor * 0.08)),
      }
    })
  }, [baseWells, impact])

  const baseTotals = useMemo(() => fieldTotals(baseWells), [baseWells])
  const totals = useMemo(() => fieldTotals(wells), [wells])
  const selected = wells.find((w) => w.id === selectedWell) || wells[0]
  const oilLoss = Math.max(0, baseTotals.oil - totals.oil)
  const oilLossPct = baseTotals.oil > 0 ? (oilLoss / baseTotals.oil) * 100 : 0

  const { data: alertsData } = useQuery({
    queryKey: ['alerts', 'open', 'dehloran'],
    queryFn: async () => {
      try {
        const data = await alertAPI.getAlerts()
        const list = data?.alerts || []
        if (Array.isArray(list) && list.length > 0) {
          return { count: list.filter((a: any) => a.status === 'open').length, alerts: list }
        }
      } catch {
        /* local */
      }
      const alerts = getDehloranAlerts()
      return { count: alerts.filter((a) => a.status === 'open').length, alerts }
    },
    refetchInterval: 12000,
    retry: false,
  })

  const openAlerts = alertsData?.count ?? getDehloranAlerts().filter((a) => a.status === 'open').length
  const wcSeries = useMemo(() => waterCutForecast(totals.avgWc), [totals.avgWc])
  const declineSeries = useMemo(() => declineForecast(totals.oil), [totals.oil])

  const abnormalWells = wells
    .filter((w) => w.status === 'warning' || w.status === 'critical')
    .sort((a, b) => a.healthScore - b.healthScore)

  const highRiskEquipment = wells
    .filter((w) => w.equipmentRisk >= 40 && w.status !== 'offline')
    .sort((a, b) => b.equipmentRisk - a.equipmentRisk)
    .slice(0, 5)

  const prioritizedAlerts = buildPrioritizedAlerts(wells, openAlerts)

  return (
    <div className="dashboard deh-dashboard" dir="rtl">
      <header className="deh-hero">
        <div>
          <p className="deh-client">{FIELD.clientFa}</p>
          <h2>
            {FIELD.nameFa}{' '}
            <span className="deh-en">({FIELD.nameEn})</span>
          </h2>
          <p className="deh-meta">
            کارفرما: {FIELD.clientFa} · نوع نفت: {FIELD.oilTypeFa} · درجه سنگینی ≈ {FIELD.apiGravity}°
          </p>
        </div>
        <div className="deh-stream">
          جریان زنده: {transportLabelFa(transport)}
          {autoPilotOn && <span className="ap-badge"> · اپراتور هوشمند</span>}
        </div>
      </header>

      <div className="metrics-grid deh-kpis">
        <div className="metric-card">
          <h3>تعداد چاه</h3>
          <div className="metric-value">{FIELD.wellCount}</div>
          <small>حلقه · آنلاین {totals.online}</small>
        </div>
        <div className="metric-card">
          <h3>دبی نفت میدان</h3>
          <div className="metric-value">{totals.oil.toLocaleString()}</div>
          <small>
            bbl/day · پایه {baseTotals.oil.toLocaleString()}
            {oilLoss > 0 ? ` · افت ${Math.round(oilLoss).toLocaleString()} (${oilLossPct.toFixed(1)}٪)` : ''}
          </small>
        </div>
        <div className="metric-card">
          <h3>درصد آب تولیدی میانگین</h3>
          <div className="metric-value">{totals.avgWc.toFixed(1)}%</div>
          <small>
            پایه {baseTotals.avgWc.toFixed(1)}٪ · Δ {(totals.avgWc - baseTotals.avgWc).toFixed(1)}
          </small>
        </div>
        <div className="metric-card">
          <h3>وضعیت چاه‌ها</h3>
          <div className="deh-status-pills">
            <span className="pill healthy">{totals.healthy} سالم</span>
            <span className="pill warning">{totals.warning} هشدار</span>
            <span className="pill critical">{totals.critical} مشکل</span>
            <span className="pill offline">{totals.offline} آفلاین</span>
          </div>
        </div>
        <div className="metric-card">
          <h3>هشدارهای فعال</h3>
          <div className="metric-value alert">{openAlerts}</div>
          <small>اولویت‌بندی هوشمند</small>
        </div>
        <div className="metric-card">
          <h3>گاز / آب</h3>
          <div className="metric-value deh-dual">
            {Math.round(totals.gas).toLocaleString()}
            <span>Mscf/d</span>
          </div>
          <small>آب: {Math.round(totals.water).toLocaleString()} bbl/d</small>
        </div>
      </div>

      <section className={`deh-layer ap-section ${autoPilotOn ? 'on' : ''}`}>
        <div className="deh-layer-head ap-head">
          <div>
            <h3>اپراتور هوشمند</h3>
            <p>
              متغیرهای قابل تنظیم دستی را کم/زیاد کنید؛ در صورت افت تولید، اپراتور هوشمند به‌صورت خودکار
              ست‌پوینت‌ها را به‌سمت نقطه بهینه برمی‌گرداند و افت را جبران می‌کند.
            </p>
          </div>
          <div className="ap-toggles">
            <div className="ap-power" role="group" aria-label="وضعیت اپراتور هوشمند">
              <button
                type="button"
                className={`ap-power-btn on ${autoPilotOn ? 'active' : ''}`}
                onClick={() => setAutoPilotOn(true)}
                aria-pressed={autoPilotOn}
              >
                <span className="ap-power-dot" aria-hidden />
                روشن
              </button>
              <button
                type="button"
                className={`ap-power-btn off ${!autoPilotOn ? 'active' : ''}`}
                onClick={() => setAutoPilotOn(false)}
                aria-pressed={!autoPilotOn}
              >
                <span className="ap-power-dot" aria-hidden />
                خاموش
              </button>
            </div>
            <button type="button" className="ap-reset" onClick={resetControls}>
              بازگشت به بهینه
            </button>
          </div>
        </div>

        <div className="ap-status-row">
          <div className={`ap-status-pill ${apStatus}`}>
            وضعیت:{' '}
            {apStatus === 'idle'
              ? 'دستی'
              : apStatus === 'stable'
                ? 'پایدار'
                : apStatus === 'recovering'
                  ? 'در حال بازیابی افت'
                  : 'افت تشخیص داده‌شد'}
          </div>
          <div className="ap-status-pill">
            ضریب تولید: <strong>{(impact.oilFactor * 100).toFixed(1)}٪</strong>
          </div>
          <div className={`ap-status-pill ${oilLossPct > 2 ? 'warn' : ''}`}>
            افت ناشی از تنظیمات: <strong>{oilLossPct.toFixed(1)}٪</strong>
          </div>
          <div className="ap-status-pill">
            انحراف از بهینه: <strong>{(impact.deviationScore * 100).toFixed(0)}٪</strong>
          </div>
        </div>

        <div className="ap-grid">
          <div className="deh-panel ap-sliders">
            <h4>متغیرهای قابل تنظیم دستی</h4>
            {CONTROLLABLE_VARS.map((v) => {
              const val = controls[v.key]
              const row = impact.perVar.find((p) => p.key === v.key)
              return (
                <div key={v.key} className="ap-slider-row">
                  <div className="ap-slider-label">
                    <strong>{v.nameFa}</strong>
                    <span>
                      {v.nameEn} · بهینه {v.optimal} {v.unit}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={v.min}
                    max={v.max}
                    step={v.step}
                    value={val}
                    onChange={(e) => setControl(v.key, Number(e.target.value))}
                  />
                  <div className="ap-slider-value">
                    <b>
                      {val} {v.unit}
                    </b>
                    {row && row.deviationPct > 0 && (
                      <em className="warn">انحراف {row.deviationPct}٪</em>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="deh-panel ap-log-panel">
            <h4>اقدامات اپراتور هوشمند</h4>
            {!autoPilotOn && (
              <p className="deh-muted">
                برای جبران خودکار افت ناشی از تنظیم دستی، اپراتور هوشمند را روشن کنید. ابتدا اسلایدرها را
                از بهینه دور کنید تا افت را در شاخص کلیدی عملکرد ببینید.
              </p>
            )}
            {autoPilotOn && apLog.length === 0 && (
              <p className="deh-muted">در انتظار انحراف… سیستم در حالت پایدار است.</p>
            )}
            <ul className="ap-log">
              {apLog.map((a, i) => (
                <li key={`${a.at}-${a.key}-${i}`}>
                  <strong>{a.nameFa}</strong>
                  <span>
                    {a.from} → {a.to}
                  </span>
                  <p>{a.reason}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="deh-layer">
        <div className="deh-layer-head">
          <h3>لایه دیداری</h3>
          <p>نمایش لحظه‌ای فشار/دمای سرچاهی، دبی نفت/گاز/آب، وضعیت تجهیزات و نقشه میدان</p>
        </div>
        <div className="deh-sight-grid">
          <div className="deh-panel deh-map-panel">
            <div className="deh-map-title">
              نقشه میدان دهلران
              <div className="deh-legend">
                <span>
                  <i style={{ background: STATUS_COLOR.healthy }} /> سالم
                </span>
                <span>
                  <i style={{ background: STATUS_COLOR.warning }} /> هشدار
                </span>
                <span>
                  <i style={{ background: STATUS_COLOR.critical }} /> مشکل
                </span>
                <span>
                  <i style={{ background: STATUS_COLOR.offline }} /> آفلاین
                </span>
              </div>
            </div>
            <div className="deh-map">
              {DEHLORAN_WELLS.map((pos) => {
                const live = wells.find((w) => w.id === pos.id)!
                return (
                  <button
                    key={pos.id}
                    type="button"
                    className={`deh-well-dot ${live.status} ${selectedWell === pos.id ? 'selected' : ''}`}
                    style={{
                      left: `${pos.x}%`,
                      top: `${pos.y}%`,
                      background: STATUS_COLOR[live.status],
                    }}
                    title={`${pos.nameFa} — ${STATUS_LABEL_FA[live.status]}`}
                    onClick={() => setSelectedWell(pos.id)}
                  >
                    {pos.id.replace('DEH-', '')}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="deh-panel">
            <h4>
              {selected.nameFa} ({selected.id})
            </h4>
            <div className="deh-well-stats">
              <Stat label="فشار سرچاهی" value={`${selected.thp} psi`} />
              <Stat label="دمای سرچاهی" value={`${selected.tht} °C`} />
              <Stat label="دبی نفت" value={`${selected.oilRate} bbl/d`} />
              <Stat label="دبی گاز" value={`${selected.gasRate} Mscf/d`} />
              <Stat label="دبی آب" value={`${selected.waterRate} bbl/d`} />
              <Stat label="درصد آب تولیدی" value={`${selected.waterCut}%`} />
              <Stat label="دبی‌سنج مجازی نفت" value={`${selected.vfmOilRate} bbl/d`} accent />
              <Stat
                label="پمپ / تجهیزات"
                value={selected.pumpOnline ? 'آنلاین' : 'آفلاین'}
                tone={selected.pumpOnline ? 'ok' : 'bad'}
              />
            </div>
          </div>
        </div>

        <div className="deh-panel deh-sensors">
          <div className="deh-sensors-head">
            <h4>سنسورهای چاه و تاسیسات — وضعیت با چراغ</h4>
            <div className="sensor-light-legend">
              <span><i className="sensor-light green" /> سبز · سالم</span>
              <span><i className="sensor-light yellow" /> زرد · هشدار</span>
              <span><i className="sensor-light red" /> قرمز · مشکل</span>
            </div>
          </div>

          <div className="sensor-lights-grid">
            {SENSOR_VARIABLES.map((v) => {
              const reading = getSensorReading(v.key, selected)
              return (
                <div key={v.key} className={`sensor-light-card ${reading.status}`}>
                  <span className={`sensor-light ${reading.status}`} title={statusLabelFa(reading.status)} />
                  <div>
                    <strong>{v.nameFa}</strong>
                    <small>
                      {reading.display} {v.unit !== '—' ? v.unit : ''}
                    </small>
                  </div>
                  <em>{statusLabelFa(reading.status)}</em>
                </div>
              )
            })}
          </div>

          <div className="deh-sensor-table-wrap">
            <table className="deh-sensor-table">
              <thead>
                <tr>
                  <th>وضعیت</th>
                  <th>متغیر</th>
                  <th>دسته</th>
                  <th>واحد</th>
                  <th>مقدار فعلی ({selected.id})</th>
                </tr>
              </thead>
              <tbody>
                {SENSOR_VARIABLES.map((v) => {
                  const reading = getSensorReading(v.key, selected)
                  return (
                    <tr key={v.key} className={`sensor-row-${reading.status}`}>
                      <td>
                        <span className={`sensor-light ${reading.status}`} title={statusLabelFa(reading.status)} />
                      </td>
                      <td>{v.nameFa}</td>
                      <td>{categoryFa(v.category)}</td>
                      <td>{v.unit}</td>
                      <td>
                        {reading.display}
                        <small className={`sensor-status-text ${reading.status}`}>
                          {' '}
                          {statusLabelFa(reading.status)}
                        </small>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="deh-layer">
        <div className="deh-layer-head">
          <h3>لایه تحلیلی</h3>
          <p>سلامت‌سنجی چاه، شناسایی خودکار عملکرد غیرعادی و شاخص‌های کلیدی</p>
        </div>
        <div className="deh-insight-grid">
          <div className="deh-panel">
            <h4>سلامت‌سنجی چاه‌ها</h4>
            <div className="deh-health-list">
              {wells.map((w) => (
                <button
                  key={w.id}
                  type="button"
                  className="deh-health-row"
                  onClick={() => setSelectedWell(w.id)}
                >
                  <span className="dot" style={{ background: STATUS_COLOR[w.status] }} />
                  <strong>{w.id}</strong>
                  <div className="bar">
                    <i style={{ width: `${w.healthScore}%`, background: STATUS_COLOR[w.status] }} />
                  </div>
                  <em>{w.healthScore}</em>
                </button>
              ))}
            </div>
          </div>
          <div className="deh-panel">
            <h4>چاه‌های نیازمند مداخله</h4>
            {abnormalWells.length === 0 ? (
              <p className="deh-muted">همه چاه‌ها در وضعیت قابل قبول هستند.</p>
            ) : (
              <ul className="deh-action-list">
                {abnormalWells.map((w) => (
                  <li key={w.id}>
                    <strong>{w.nameFa}</strong>
                    <span className={`tag ${w.status}`}>{STATUS_LABEL_FA[w.status]}</span>
                    <p>
                      درصد آب تولیدی {w.waterCut}% · افت ۳۰روزه {w.declinePct30d}% · ریسک تجهیزات{' '}
                      {w.equipmentRisk}%
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      <section className="deh-layer">
        <div className="deh-layer-head">
          <h3>لایه پیش‌بینی‌کننده</h3>
          <p>
            منحنی افت تولید، پیش‌بینی درصد آب تولیدی، خرابی تجهیزات، دبی‌سنج مجازی و مدیریت هوشمند هشدارها با مدل‌های
            داده‌کاوی و هوش مصنوعی
          </p>
        </div>
        <div className="deh-foresight-grid">
          <div className="deh-panel chart-container">
            <h4>پیش‌بینی درصد آب تولیدی</h4>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={wcSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis dataKey="day" stroke="#555" />
                <YAxis stroke="#555" unit="%" />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="waterCut"
                  name="درصد آب تولیدی %"
                  stroke="#42a5f5"
                  fill="#1565c0"
                  fillOpacity={0.35}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="deh-panel chart-container">
            <h4>پیش‌بینی افت تولید (منحنی افت تولید) میدان</h4>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={declineSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis dataKey="month" stroke="#555" />
                <YAxis stroke="#555" />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="actual"
                  name="فعلی"
                  stroke="#66bb6a"
                  strokeWidth={2}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="پیش‌بینی"
                  stroke="#ffa726"
                  strokeDasharray="6 4"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="deh-panel">
            <h4>پیش‌بینی خرابی تجهیزات / پمپ</h4>
            <ul className="deh-action-list">
              {highRiskEquipment.map((w) => (
                <li key={w.id}>
                  <strong>{w.id}</strong>
                  <span className="tag warning">ریسک {w.equipmentRisk}%</span>
                  <p>هشدار قبل از خرابی — پیشنهاد برنامه‌ریزی تعمیرات پیشگیرانه پمپ درون‌چاهی الکتریکی</p>
                </li>
              ))}
              {highRiskEquipment.length === 0 && (
                <li>
                  <p className="deh-muted">ریسک تجهیزات در محدوده پایین است.</p>
                </li>
              )}
            </ul>
          </div>
          <div className="deh-panel">
            <h4>دبی‌سنج مجازی</h4>
            <p className="deh-muted">
              تخمین تولید هر چاه بدون دبی‌سنج فیزیکی جداگانه — مقرون‌به‌صرفه برای ۱۶ حلقه دهلران
            </p>
            <div className="deh-vfm-grid">
              {wells.slice(0, 8).map((w) => (
                <div key={w.id} className="deh-vfm-card">
                  <strong>{w.id}</strong>
                  <span>{w.vfmOilRate} bbl/d</span>
                  <small>Δ {(w.vfmOilRate - w.oilRate).toFixed(0)} vs مرجع</small>
                </div>
              ))}
            </div>
            <p className="deh-muted" style={{ marginTop: 8 }}>
              و {wells.length - 8} چاه دیگر در مدل دبی‌سنج مجازی میدان…
            </p>
          </div>
          <div className="deh-panel deh-alerts-smart">
            <h4>مدیریت هوشمند هشدارها</h4>
            <p className="deh-muted">اولویت‌بندی و کاهش هشدارهای کاذب با همبستگی چاه/تجهیزات</p>
            <ul className="deh-action-list">
              {prioritizedAlerts.map((a) => (
                <li key={a.id}>
                  <strong>{a.title}</strong>
                  <span className={`tag ${a.severity}`}>{a.priority}</span>
                  <p>{a.detail}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </div>
  )
}

function Stat({
  label,
  value,
  accent,
  tone,
}: {
  label: string
  value: string
  accent?: boolean
  tone?: 'ok' | 'bad'
}) {
  return (
    <div className={`deh-stat ${accent ? 'accent' : ''} ${tone || ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function categoryFa(cat: string) {
  if (cat === 'wellhead') return 'سرچاهی'
  if (cat === 'production') return 'تولید'
  if (cat === 'equipment') return 'تجهیزات'
  return 'تاسیسات'
}

type SensorLight = 'green' | 'yellow' | 'red'

function statusLabelFa(s: SensorLight) {
  if (s === 'green') return 'سالم'
  if (s === 'yellow') return 'هشدار'
  return 'مشکل'
}

function getSensorReading(key: string, w: WellLiveState): { display: string; status: SensorLight; value: number | null } {
  if (w.status === 'offline') {
    return { display: '—', status: 'red', value: null }
  }

  const numeric: Record<string, number | null> = {
    thp: w.thp,
    tht: w.tht,
    chp: Math.round(w.thp * 0.72),
    oil_rate: w.oilRate,
    gas_rate: w.gasRate,
    water_rate: w.waterRate,
    water_cut: w.waterCut,
    gor: Math.round((w.gasRate * 1000) / Math.max(1, w.oilRate)),
    esp_current: w.pumpOnline ? Math.round((28 + w.equipmentRisk * 0.15) * 10) / 10 : null,
    esp_vibration: w.pumpOnline ? Math.round((1.2 + w.equipmentRisk * 0.04) * 100) / 100 : null,
    esp_temp: w.pumpOnline ? Math.round(62 + w.equipmentRisk * 0.2) : null,
    manifold_p: Math.round(w.thp * 0.88),
    separator_p: Math.round(180 + w.waterCut),
    separator_l: Math.round(45 + w.waterCut * 0.25),
    pipeline_p: Math.round(w.thp * 0.65),
  }

  const value = numeric[key] ?? null
  if (value === null) {
    return { display: '—', status: 'red', value: null }
  }

  let status: SensorLight = 'green'

  switch (key) {
    case 'thp':
      if (value < 600 || value > 2200) status = 'red'
      else if (value < 800 || value > 1800) status = 'yellow'
      break
    case 'tht':
      if (value < 35 || value > 95) status = 'red'
      else if (value < 45 || value > 85) status = 'yellow'
      break
    case 'chp':
      if (value > w.thp * 0.95 || value < 200) status = 'red'
      else if (value > w.thp * 0.85) status = 'yellow'
      break
    case 'oil_rate':
      if (value < 150) status = 'red'
      else if (value < 300 || w.declinePct30d > 6) status = 'yellow'
      break
    case 'gas_rate':
      if (value < 50) status = 'red'
      else if (value < 120) status = 'yellow'
      break
    case 'water_rate':
      if (value > 800) status = 'red'
      else if (value > 450) status = 'yellow'
      break
    case 'water_cut':
      if (value >= 65) status = 'red'
      else if (value >= 45) status = 'yellow'
      break
    case 'gor':
      if (value > 2500 || value < 200) status = 'red'
      else if (value > 1800 || value < 400) status = 'yellow'
      break
    case 'esp_current':
      if (value > 55 || value < 15) status = 'red'
      else if (value > 45 || w.equipmentRisk >= 55) status = 'yellow'
      break
    case 'esp_vibration':
      if (value >= 5) status = 'red'
      else if (value >= 3) status = 'yellow'
      break
    case 'esp_temp':
      if (value >= 95) status = 'red'
      else if (value >= 80) status = 'yellow'
      break
    case 'manifold_p':
      if (value < 500 || value > 2000) status = 'red'
      else if (value < 700 || value > 1700) status = 'yellow'
      break
    case 'separator_p':
      if (value < 100 || value > 320) status = 'red'
      else if (value < 140 || value > 260) status = 'yellow'
      break
    case 'separator_l':
      if (value < 20 || value > 90) status = 'red'
      else if (value < 30 || value > 80) status = 'yellow'
      break
    case 'pipeline_p':
      if (value < 400 || value > 1600) status = 'red'
      else if (value < 550 || value > 1400) status = 'yellow'
      break
    default:
      status = w.status === 'critical' ? 'red' : w.status === 'warning' ? 'yellow' : 'green'
  }

  // Well-level escalation: critical well cannot show all green on equipment sensors
  if (w.status === 'critical' && (key.startsWith('esp_') || key === 'water_cut')) {
    status = status === 'green' ? 'yellow' : status
  }

  const display =
    Number.isInteger(value) || Math.abs(value - Math.round(value)) < 0.001
      ? String(Math.round(value))
      : String(value)

  return { display, status, value }
}

function buildPrioritizedAlerts(wells: WellLiveState[], openCount: number | string) {
  const critical = wells.filter((w) => w.status === 'critical')
  const highWc = wells.filter((w) => w.waterCut > 55)
  const items = [
    ...critical.map((w, i) => ({
      id: `c-${w.id}`,
      title: `اولویت بحرانی — ${w.nameFa}`,
      priority: 'P1',
      severity: 'critical' as WellHealthStatus,
      detail: `عملکرد غیرعادی / پمپ ${w.pumpOnline ? 'تحت تنش' : 'آفلاین'} · امتیاز سلامت ${w.healthScore}`,
      order: i,
    })),
    ...highWc.slice(0, 3).map((w, i) => ({
      id: `wc-${w.id}`,
      title: `درصد آب تولیدی بالا — ${w.id}`,
      priority: 'P2',
      severity: 'warning' as WellHealthStatus,
      detail: `درصد آب تولیدی ${w.waterCut}% — همبسته‌سازی برای کاهش هشدار کاذب انجام شد`,
      order: 10 + i,
    })),
    {
      id: 'fp-filter',
      title: 'فیلتر هشدار کاذب فعال',
      priority: 'Info',
      severity: 'healthy' as WellHealthStatus,
      detail: `از مجموعه هشدارهای خام، موارد تکراری/نویزی سرکوب شدند · هشدارهای باز: ${openCount}`,
      order: 99,
    },
  ]
  return items.sort((a, b) => a.order - b.order).slice(0, 6)
}
