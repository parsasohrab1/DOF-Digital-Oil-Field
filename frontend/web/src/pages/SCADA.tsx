import { useEffect, useMemo, useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts'
import { FIELD, DEHLORAN_WELLS, STATUS_COLOR, STATUS_LABEL_FA, getDehloranLiveState } from '../data/dehloranField'
import {
  getScadaConnections,
  getScadaTags,
  getModbusMap,
  getDataPipeline,
  scadaSummary,
  tagHistory,
  lightFromQuality,
  getPadOverviews,
  getFacilityHmi,
  getScadaAlarms,
  getInterlocks,
  getOperatorTips,
  getControlSetpoints,
  PROTOCOL_LABEL_FA,
  type ScadaConnection,
  type ScadaTag,
  type ConnStatus,
  type ControlSetpoint,
} from '../data/dehloranScada'
import './SCADA.css'

type Tab = 'overview' | 'control' | 'alarms' | 'tags' | 'pipeline'

const STATUS_FA: Record<ConnStatus, string> = {
  online: 'آنلاین',
  degraded: 'افت کیفیت',
  offline: 'قطع',
}

const STATUS_COLOR_CONN: Record<ConnStatus, string> = {
  online: '#2e7d32',
  degraded: '#f9a825',
  offline: '#c62828',
}

const QUALITY_FA = { good: 'خوب', uncertain: 'مشکوک', bad: 'بد' } as const
const SEV_FA = { critical: 'بحرانی', warning: 'هشدار', info: 'اطلاع' } as const
const IL_FA = { armed: 'آماده', tripped: 'فعال‌شده', bypassed: 'بای‌پس' } as const

const REG_TYPE_FA: Record<string, string> = {
  Holding: 'ست‌پوینت نوشتني',
  Input: 'فیدبک خواندنی',
  Coil: 'اینترلاک بولین',
}

const TOOLTIP = { background: '#ffffff', border: '1px solid #ccc', borderRadius: 8, color: '#111' }

export default function SCADA() {
  const [tick, setTick] = useState(Date.now())
  const [tab, setTab] = useState<Tab>('overview')
  const [selectedConn, setSelectedConn] = useState('OPC-RTU-PAD-A')
  const [selectedWell, setSelectedWell] = useState('DEH-01')
  const [selectedTagId, setSelectedTagId] = useState('DEH-01.THP')
  const [connOverride, setConnOverride] = useState<Record<string, ConnStatus>>({})
  const [writeLog, setWriteLog] = useState<string[]>([])
  const [setpoints, setSetpoints] = useState<ControlSetpoint[]>([])

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 8000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    setSetpoints(getControlSetpoints(tick, selectedWell))
  }, [tick, selectedWell])

  const connections = useMemo(() => {
    return getScadaConnections(tick).map((c) =>
      connOverride[c.id] ? { ...c, status: connOverride[c.id] } : c
    )
  }, [tick, connOverride])

  const summary = useMemo(() => {
    const base = scadaSummary(tick)
    const online = connections.filter((c) => c.status === 'online').length
    const degraded = connections.filter((c) => c.status === 'degraded').length
    const offline = connections.filter((c) => c.status === 'offline').length
    return { ...base, online, degraded, offline }
  }, [tick, connections])

  const tags = useMemo(() => getScadaTags(tick), [tick])
  const wells = useMemo(() => getDehloranLiveState(tick), [tick])
  const pads = useMemo(() => getPadOverviews(tick), [tick])
  const facility = useMemo(() => getFacilityHmi(tick), [tick])
  const alarms = useMemo(() => getScadaAlarms(tick), [tick])
  const interlocks = useMemo(() => getInterlocks(tick), [tick])
  const tips = useMemo(() => getOperatorTips(tick), [tick])
  const modbus = useMemo(() => getModbusMap(tick, selectedWell), [tick, selectedWell])
  const pipeline = useMemo(() => getDataPipeline(tick), [tick])

  const connTags = useMemo(
    () => tags.filter((t) => t.connectionId === selectedConn),
    [tags, selectedConn]
  )
  const wellTags = useMemo(
    () => tags.filter((t) => t.wellId === selectedWell || t.category === 'facility'),
    [tags, selectedWell]
  )

  const selectedTag: ScadaTag | undefined =
    tags.find((t) => t.id === selectedTagId) || tags[0]

  const history = useMemo(() => {
    if (!selectedTag || typeof selectedTag.value !== 'number') return []
    return tagHistory(selectedTag.id, selectedTag.value)
  }, [selectedTag])

  const padOilChart = useMemo(
    () => pads.map((p) => ({ pad: `پد ${p.pad}`, oil: p.oil, alarms: p.alarms })),
    [pads]
  )

  const qualityBars = useMemo(() => {
    const g = tags.filter((t) => t.quality === 'good').length
    const u = tags.filter((t) => t.quality === 'uncertain').length
    const b = tags.filter((t) => t.quality === 'bad').length
    return [
      { name: 'خوب', value: g, color: '#2e7d32' },
      { name: 'مشکوک', value: u, color: '#f9a825' },
      { name: 'بد', value: b, color: '#c62828' },
    ]
  }, [tags])

  const selectedWellLive = wells.find((w) => w.id === selectedWell)

  const toggleConn = (c: ScadaConnection) => {
    const next: ConnStatus =
      c.status === 'online' ? 'offline' : c.status === 'offline' ? 'online' : 'online'
    setConnOverride((prev) => ({ ...prev, [c.id]: next }))
    setWriteLog((prev) =>
      [
        `${new Date().toLocaleTimeString('fa-IR')} — ${c.nameFa}: ${STATUS_FA[c.status]} → ${STATUS_FA[next]}`,
        ...prev,
      ].slice(0, 24)
    )
  }

  const applySetpoint = (sp: ControlSetpoint) => {
    setWriteLog((prev) =>
      [
        `${new Date().toLocaleTimeString('fa-IR')} — ارسال ست‌پوینت «${sp.nameFa}» = ${sp.value} ${sp.unit} → آدرس ${sp.address} (صف فرمان و کنترل)`,
        ...prev,
      ].slice(0, 24)
    )
  }

  const ackAlarm = (title: string) => {
    setWriteLog((prev) =>
      [`${new Date().toLocaleTimeString('fa-IR')} — تأیید آلارم: ${title}`, ...prev].slice(0, 24)
    )
  }

  return (
    <div className="scada-page deh-scada" dir="rtl">
      <header className="scada-hero">
        <div>
          <p className="scada-client">{FIELD.clientFa}</p>
          <h2>اسکادا و کنترل‌گر منطقی — {FIELD.nameFa}</h2>
          <p className="scada-meta">
            پایش زنده ۱۶ حلقه، تأسیسات سطح، آلارم صنعتی، اینترلاک ایمنی و ارسال ست‌پوینت کنترل برای نفت سنگین
            درجه سنگینی {FIELD.apiGravity}
          </p>
        </div>
        <div className="scada-tabs">
          {(
            [
              ['overview', 'نمای عملیاتی'],
              ['control', 'کنترل و ست‌پوینت'],
              ['alarms', 'آلارم و اینترلاک'],
              ['tags', 'تگ‌ها و رجیسترها'],
              ['pipeline', 'مسیر داده'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={tab === id ? 'active' : ''}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      <div className="scada-kpis">
        <div className="skpi">
          <span>اتصالات میدانی</span>
          <strong>
            {summary.online}/{summary.connections}
          </strong>
          <small>
            افت {summary.degraded} · قطع {summary.offline}
          </small>
        </div>
        <div className="skpi">
          <span>آلارم‌های باز</span>
          <strong>{alarms.length}</strong>
          <small>
            بحرانی {alarms.filter((a) => a.severity === 'critical').length} · هشدار{' '}
            {alarms.filter((a) => a.severity === 'warning').length}
          </small>
        </div>
        <div className="skpi">
          <span>نفت صادراتی تأسیسات</span>
          <strong>{facility.exportOil.toLocaleString()}</strong>
          <small>بشکه در روز</small>
        </div>
        <div className="skpi">
          <span>نقاط پویش / ثانیه</span>
          <strong>{summary.pointsPerSec.toLocaleString()}</strong>
          <small>تگ قابل‌نوشتن {summary.writable}</small>
        </div>
      </div>

      {tab === 'overview' && (
        <div className="scada-grid">
          <section className="scada-card wide">
            <h3>نمای پدهای تولید</h3>
            <div className="pad-grid">
              {pads.map((p) => (
                <button
                  key={p.pad}
                  type="button"
                  className={`pad-card ${p.status}`}
                  onClick={() => {
                    setSelectedWell(p.wellIds[0])
                    setSelectedConn(`OPC-RTU-PAD-${p.pad}`)
                    setTab('control')
                  }}
                >
                  <div className="pad-top">
                    <strong>{p.nameFa}</strong>
                    <em style={{ color: STATUS_COLOR_CONN[p.status] }}>{STATUS_FA[p.status]}</em>
                  </div>
                  <div className="pad-metrics">
                    <div>
                      <small>نفت</small>
                      <b>{p.oil.toLocaleString()}</b>
                    </div>
                    <div>
                      <small>آب تولیدی</small>
                      <b>{p.avgWc}%</b>
                    </div>
                    <div>
                      <small>فشار سرچاهی</small>
                      <b>{p.avgThp}</b>
                    </div>
                    <div>
                      <small>آنلاین / آلارم</small>
                      <b>
                        {p.online}/4 · {p.alarms}
                      </b>
                    </div>
                  </div>
                  <div className="pad-wells">
                    {p.wellIds.map((id) => {
                      const w = wells.find((x) => x.id === id)!
                      return (
                        <span key={id} style={{ background: STATUS_COLOR[w.status] }}>
                          {id.replace('DEH-', '')}
                        </span>
                      )
                    })}
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="scada-card">
            <h3>مقایسه دبی نفت پدها</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={padOilChart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="pad" stroke="#888" />
                <YAxis stroke="#888" />
                <Tooltip contentStyle={TOOLTIP} />
                <Bar dataKey="oil" name="نفت (بشکه/روز)" fill="#42a5f5" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </section>

          <section className="scada-card">
            <h3>کیفیت تگ‌های زنده</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={qualityBars}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="name" stroke="#888" />
                <YAxis stroke="#888" />
                <Tooltip contentStyle={TOOLTIP} />
                <Bar dataKey="value" name="تعداد" radius={[4, 4, 0, 0]}>
                  {qualityBars.map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </section>

          <section className="scada-card wide">
            <h3>پنل تأسیسات سطح</h3>
            <div className="facility-grid">
              <FacilityStat label="فشار منیفولد" value={facility.manifoldPsi} unit="psi" />
              <FacilityStat label="فشار جداکننده" value={facility.separatorPsi} unit="psi" />
              <FacilityStat label="سطح جداکننده" value={facility.separatorLevel} unit="%" warn={facility.separatorLevel > 78 || facility.separatorLevel < 28} />
              <FacilityStat label="نفت صادراتی" value={facility.exportOil} unit="bbl/d" />
              <FacilityStat label="فشار خط لوله" value={facility.pipelinePsi} unit="psi" />
              <FacilityStat label="هدر گاز لیفت" value={facility.gasLiftHeader} unit="psi" />
              <FacilityStat label="فشار تزریق آب" value={facility.waterInjectionPsi} unit="psi" />
            </div>
            <ul className="advice-list">
              {facility.advice.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </section>

          <section className="scada-card">
            <h3>راهنمای اپراتور</h3>
            <ul className="tip-list">
              {tips.map((t, i) => (
                <li key={i} className={t.priority}>
                  <strong>{t.title}</strong>
                  <p>{t.detail}</p>
                </li>
              ))}
            </ul>
          </section>

          <section className="scada-card">
            <h3>اتصالات (خلاصه)</h3>
            <div className="conn-mini">
              {connections.map((c) => (
                <div key={c.id} className={`conn-mini-row ${c.status}`}>
                  <span>{c.nameFa}</span>
                  <em style={{ color: STATUS_COLOR_CONN[c.status] }}>{STATUS_FA[c.status]}</em>
                  <button type="button" onClick={() => toggleConn(c)}>
                    {c.status === 'online' ? 'قطع' : 'وصل'}
                  </button>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {tab === 'control' && (
        <div className="scada-grid">
          <section className="scada-card">
            <h3>انتخاب چاه برای کنترل</h3>
            <div className="well-chips">
              {DEHLORAN_WELLS.map((w) => {
                const live = wells.find((x) => x.id === w.id)!
                return (
                  <button
                    key={w.id}
                    type="button"
                    className={selectedWell === w.id ? 'active' : ''}
                    style={{ borderColor: STATUS_COLOR[live.status] }}
                    onClick={() => setSelectedWell(w.id)}
                  >
                    {w.id.replace('DEH-', '')}
                  </button>
                )
              })}
            </div>
            {selectedWellLive && (
              <div className="well-control-summary">
                <p>
                  <strong>{selectedWellLive.nameFa}</strong> — {STATUS_LABEL_FA[selectedWellLive.status]}
                </p>
                <p>
                  نفت {selectedWellLive.oilRate} · آب تولیدی {selectedWellLive.waterCut}% · فشار سرچاهی{' '}
                  {selectedWellLive.thp} psi · پمپ{' '}
                  {selectedWellLive.pumpOnline ? 'آنلاین' : 'آفلاین'}
                </p>
              </div>
            )}
          </section>

          <section className="scada-card wide-2">
            <h3>
              ست‌پوینت‌های قابل ارسال
              <small>تغییر مقدار و ارسال به صف فرمان و کنترل — برای ایمنی واقعی نیاز به تأیید دو نفره است</small>
            </h3>
            <div className="sp-list">
              {setpoints.map((sp) => (
                <div key={sp.key} className="sp-row">
                  <div className="sp-label">
                    <strong>{sp.nameFa}</strong>
                    <span>{sp.purpose}</span>
                    <small dir="ltr">آدرس {sp.address}</small>
                  </div>
                  <input
                    type="range"
                    min={sp.min}
                    max={sp.max}
                    step={1}
                    value={sp.value}
                    onChange={(e) => {
                      const v = Number(e.target.value)
                      setSetpoints((prev) =>
                        prev.map((x) => (x.key === sp.key ? { ...x, value: v } : x))
                      )
                    }}
                  />
                  <div className="sp-val">
                    <b>
                      {sp.value} {sp.unit}
                    </b>
                    <button type="button" className="primary" onClick={() => applySetpoint(sp)}>
                      ارسال
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="scada-card">
            <h3>روند تگ مرتبط</h3>
            <div className="tag-pick">
              <select value={selectedTagId} onChange={(e) => setSelectedTagId(e.target.value)}>
                {wellTags
                  .filter((t) => typeof t.value === 'number')
                  .slice(0, 30)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.nameFa}
                    </option>
                  ))}
              </select>
            </div>
            {selectedTag && typeof selectedTag.value === 'number' && (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="t" stroke="#888" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#888" />
                  <Tooltip contentStyle={TOOLTIP} />
                  <Line type="monotone" dataKey="value" stroke="#66bb6a" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </section>

          <section className="scada-card">
            <h3>لاگ فرمان‌ها</h3>
            {writeLog.length === 0 ? (
              <p className="muted">هنوز فرمانی ارسال نشده است.</p>
            ) : (
              <ul className="write-log">
                {writeLog.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {tab === 'alarms' && (
        <div className="scada-grid">
          <section className="scada-card wide-2">
            <h3>
              آلارم‌های صنعتی زنده
              <small>بر اساس وضعیت چاه، کیفیت تگ و تأسیسات سطح</small>
            </h3>
            <div className="alarm-list">
              {alarms.length === 0 && <p className="muted">آلارم بازی وجود ندارد.</p>}
              {alarms.map((a) => (
                <div key={a.id} className={`alarm-card ${a.severity}`}>
                  <div className="alarm-head">
                    <strong>{a.title}</strong>
                    <em>{SEV_FA[a.severity]}</em>
                  </div>
                  <p>{a.detail}</p>
                  <p className="alarm-action">اقدام پیشنهادی: {a.action}</p>
                  <div className="alarm-foot">
                    <span>{a.source}</span>
                    <span>{a.at}</span>
                    {a.wellId && <span>{a.wellId}</span>}
                    <button type="button" onClick={() => ackAlarm(a.title)}>
                      تأیید
                    </button>
                    {a.tagId && (
                      <button
                        type="button"
                        className="primary"
                        onClick={() => {
                          setSelectedTagId(a.tagId!)
                          if (a.wellId) setSelectedWell(a.wellId)
                          setTab('tags')
                        }}
                      >
                        مشاهده تگ
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="scada-card">
            <h3>اینترلاک‌های ایمنی</h3>
            <ul className="interlock-list">
              {interlocks.map((il) => (
                <li key={il.id} className={il.state}>
                  <div>
                    <strong>{il.nameFa}</strong>
                    <em>{IL_FA[il.state]}</em>
                  </div>
                  <p>شرط: {il.condition}</p>
                  <p>اثر: {il.effect}</p>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}

      {tab === 'tags' && (
        <div className="scada-grid">
          <section className="scada-card">
            <h3>اتصال و چاه</h3>
            <div className="mini-conn-list">
              {connections.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={selectedConn === c.id ? 'active' : ''}
                  onClick={() => setSelectedConn(c.id)}
                >
                  <strong>{c.nameFa}</strong>
                  <span style={{ color: STATUS_COLOR_CONN[c.status] }}>{STATUS_FA[c.status]}</span>
                </button>
              ))}
            </div>
            <div className="well-chips">
              {DEHLORAN_WELLS.map((w) => (
                <button
                  key={w.id}
                  type="button"
                  className={selectedWell === w.id ? 'active' : ''}
                  onClick={() => {
                    setSelectedWell(w.id)
                    setSelectedTagId(`${w.id}.THP`)
                  }}
                >
                  {w.id.replace('DEH-', '')}
                </button>
              ))}
            </div>
          </section>

          <section className="scada-card wide-2">
            <h3>
              تگ‌های زنده — {connections.find((c) => c.id === selectedConn)?.nameFa || selectedConn}
              <small>
                {PROTOCOL_LABEL_FA[connections.find((c) => c.id === selectedConn)?.protocol || 'OPC-UA']}
              </small>
            </h3>
            <div className="tag-table-wrap">
              <table className="tag-table">
                <thead>
                  <tr>
                    <th>کیفیت</th>
                    <th>نام</th>
                    <th>آدرس</th>
                    <th>مقدار</th>
                    <th>هدف عملیاتی</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {(selectedConn.startsWith('OPC-FACILITY')
                    ? tags.filter((t) => t.category === 'facility')
                    : selectedConn.startsWith('MB-')
                      ? tags.filter((t) => t.connectionId === selectedConn && (!t.wellId || t.wellId === selectedWell))
                      : connTags.length
                        ? connTags
                        : wellTags.filter((t) => t.protocol === 'OPC-UA' && t.wellId === selectedWell)
                  ).map((t) => (
                    <tr key={t.id} className={selectedTagId === t.id ? 'sel' : ''}>
                      <td>
                        <i className={`qlight ${lightFromQuality(t.quality)}`} title={QUALITY_FA[t.quality]} />
                      </td>
                      <td>
                        <strong>{t.nameFa}</strong>
                      </td>
                      <td dir="ltr" className="mono">
                        {t.address}
                      </td>
                      <td>
                        <b>
                          {typeof t.value === 'boolean' ? (t.value ? 'فعال' : 'غیرفعال') : t.value}
                        </b>{' '}
                        {t.unit}
                      </td>
                      <td className="purpose">{t.purpose}</td>
                      <td>
                        <button type="button" onClick={() => setSelectedTagId(t.id)}>
                          روند
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ marginTop: '1rem' }}>رجیسترهای کنترل‌گر — {selectedWell}</h3>
            <div className="tag-table-wrap">
              <table className="tag-table">
                <thead>
                  <tr>
                    <th>آدرس</th>
                    <th>نوع</th>
                    <th>نام</th>
                    <th>مقدار</th>
                    <th>هدف</th>
                  </tr>
                </thead>
                <tbody>
                  {modbus.map((r) => (
                    <tr key={`${r.connectionId}-${r.address}`}>
                      <td className="mono" dir="ltr">
                        {r.address}
                      </td>
                      <td>
                        <span className={`reg-type ${r.type.toLowerCase()}`}>
                          {REG_TYPE_FA[r.type] || r.type}
                        </span>
                      </td>
                      <td>
                        <strong>{r.nameFa}</strong>
                      </td>
                      <td>
                        <b>
                          {typeof r.value === 'boolean' ? (r.value ? '۱' : '۰') : r.value}
                        </b>{' '}
                        {r.unit}
                      </td>
                      <td className="purpose">{r.purpose}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {tab === 'pipeline' && (
        <div className="scada-grid">
          <section className="scada-card wide">
            <h3>مسیر داده از میدان تا داشبورد</h3>
            <div className="pipeline">
              {pipeline.map((hop, i) => (
                <div key={i} className={`pipe-hop ${hop.status}`}>
                  <div className="pipe-from">{hop.from}</div>
                  <div className="pipe-arrow">← {hop.rateHz} هرتز →</div>
                  <div className="pipe-to">{hop.to}</div>
                  <em>
                    {hop.status === 'ok' ? 'پایدار' : hop.status === 'lag' ? 'تأخیر' : 'قطع'}
                  </em>
                </div>
              ))}
            </div>
            <ul className="pipe-notes">
              <li>پایانه‌های سرچاهی چهار پد، فشار و دمای سرچاه و وضعیت ایمنی را می‌خوانند.</li>
              <li>درایو پمپ و کنترل‌گر فرآیند، سرعت پمپ و شیر کنترل جریان را برای حفظ دبی می‌نویسند.</li>
              <li>تأسیسات سطح (منیفولد، جداکننده، خط لوله) برای تطبیق تولید و جلوگیری از سرریز پایش می‌شود.</li>
              <li>هدف: کاهش توقف تولید، ایمنی توقف اضطراری، و تغذیه اپراتور هوشمند داشبورد.</li>
            </ul>
          </section>

          <section className="scada-card wide">
            <h3>لاگ عملیات</h3>
            {writeLog.length === 0 ? (
              <p className="muted">رویداد عملیاتی ثبت نشده است.</p>
            ) : (
              <ul className="write-log">
                {writeLog.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

function FacilityStat({
  label,
  value,
  unit,
  warn,
}: {
  label: string
  value: number
  unit: string
  warn?: boolean
}) {
  return (
    <div className={`facility-stat ${warn ? 'warn' : ''}`}>
      <span>{label}</span>
      <strong>
        {value.toLocaleString()} <small>{unit}</small>
      </strong>
    </div>
  )
}
