import { useEffect, useMemo, useState } from 'react'
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
} from 'recharts'
import { digitalTwinAPI } from '../api/services'
import { FIELD, DEHLORAN_WELLS } from '../data/dehloranField'
import {
  buildDehloranArDevices,
  buildDehloranArSessions,
  buildDehloranArAnchors,
  buildDehloranArBim,
  buildArTelemetrySeries,
  buildArOverlayPayload,
  STATUS_COLOR,
  STATUS_LABEL_FA,
  type ArAnchor,
} from '../data/dehloranAr'
import './ARIntegration.css'

export default function ARIntegration() {
  const [tick, setTick] = useState(Date.now())
  const [selectedDevice, setSelectedDevice] = useState('AR-DEH-01')
  const [selectedWell, setSelectedWell] = useState(DEHLORAN_WELLS[0].id)
  const [focusAnchor, setFocusAnchor] = useState<string | null>(null)
  const [hudLocked, setHudLocked] = useState(true)

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 8000)
    return () => window.clearInterval(id)
  }, [])

  const devices = useMemo(() => buildDehloranArDevices(tick), [tick])
  const sessions = useMemo(() => buildDehloranArSessions(devices, tick), [devices, tick])
  const anchors = useMemo(() => buildDehloranArAnchors(tick), [tick])
  const bim = useMemo(() => buildDehloranArBim(selectedWell, tick), [selectedWell, tick])
  const series = useMemo(() => buildArTelemetrySeries(selectedWell, tick), [selectedWell, tick])
  const localOverlay = useMemo(() => buildArOverlayPayload(selectedWell, tick), [selectedWell, tick])

  useEffect(() => {
    if (!devices.find((d) => d.deviceId === selectedDevice) && devices[0]) {
      setSelectedDevice(devices[0].deviceId)
    }
  }, [devices, selectedDevice])

  const selectedDeviceData = devices.find((d) => d.deviceId === selectedDevice)
  const focused: ArAnchor | undefined =
    anchors.find((a) => a.id === focusAnchor) ||
    anchors.find((a) => a.wellId === selectedWell) ||
    anchors[0]

  useEffect(() => {
    if (selectedDeviceData?.wellId) {
      setSelectedWell(selectedDeviceData.wellId)
      setFocusAnchor(`ANC-${selectedDeviceData.wellId}`)
    }
  }, [selectedDeviceData?.wellId])

  const { data: remoteOverlay } = useQuery({
    queryKey: ['ar-overlay-deh', selectedWell],
    queryFn: async () => {
      try {
        return await digitalTwinAPI.getAROverlay(selectedWell)
      } catch {
        return null
      }
    },
    refetchInterval: 12000,
    retry: 0,
  })

  const overlay = remoteOverlay?.anchors ? remoteOverlay : localOverlay

  return (
    <div className="ar-integration-page deh-ar" dir="rtl">
      <header className="deh-ar-hero">
        <div>
          <p className="deh-ar-client">{FIELD.clientFa}</p>
          <h1>واقعیت افزوده میدان — {FIELD.nameFa}</h1>
          <p className="deh-ar-meta">
            پوشش بصری ۱۶ حلقه · نمایشگر سربلند سرچاهی · مدل اطلاعات تأسیسات قطعات · دبی‌سنج مجازی و درصد آب تولیدی روی لنگرهای واقعیت افزوده
          </p>
        </div>
        <label className="deh-ar-lock">
          <input type="checkbox" checked={hudLocked} onChange={(e) => setHudLocked(e.target.checked)} />
          قفل نمایشگر سربلند روی لنگر
        </label>
      </header>

      <div className="ar-stats-grid">
        <div className="stat-card">
          <h3>دستگاه‌های آنلاین</h3>
          <div className="stat-value">
            {devices.filter((d) => d.connectionStatus === 'connected').length}
          </div>
          <div className="stat-label">از {devices.length} دستگاه میدان</div>
        </div>
        <div className="stat-card">
          <h3>نشست‌های فعال</h3>
          <div className="stat-value">{sessions.length}</div>
          <div className="stat-label">تکنسین در میدان دهلران</div>
        </div>
        <div className="stat-card">
          <h3>لنگرهای واقعیت افزوده</h3>
          <div className="stat-value">{anchors.length}</div>
          <div className="stat-label">چاه + تأسیسات</div>
        </div>
        <div className="stat-card">
          <h3>نقاط داده در نشست</h3>
          <div className="stat-value">
            {sessions.reduce((s, x) => s + x.dataPointsAccessed, 0)}
          </div>
          <div className="stat-label">تله‌متری زنده پوشش بصری</div>
        </div>
      </div>

      {/* —— Visual AR viewport —— */}
      <section className="deh-ar-viewport-wrap">
        <div className="deh-ar-viewport-head">
          <h2>نمای واقعیت افزوده (شبیه‌سازی فیلدی)</h2>
          <select
            value={selectedWell}
            onChange={(e) => {
              setSelectedWell(e.target.value)
              setFocusAnchor(`ANC-${e.target.value}`)
            }}
          >
            {DEHLORAN_WELLS.map((w) => (
              <option key={w.id} value={w.id}>
                {w.nameFa} ({w.id})
              </option>
            ))}
          </select>
        </div>

        <div className="deh-ar-viewport">
          <div className="deh-ar-sky" />
          <div className="deh-ar-ground" />
          <div className="deh-ar-reticle" />

          {anchors.map((a) => (
            <button
              key={a.id}
              type="button"
              className={`deh-ar-anchor ${a.kind} ${focused?.id === a.id ? 'focused' : ''}`}
              style={{
                left: `${a.x}%`,
                top: `${a.y}%`,
                borderColor: STATUS_COLOR[a.status],
              }}
              onClick={() => {
                setFocusAnchor(a.id)
                if (a.wellId.startsWith('DEH-')) setSelectedWell(a.wellId)
              }}
              title={a.labelFa}
            >
              <i style={{ background: STATUS_COLOR[a.status] }} />
              <span className="anc-label">{a.labelFa.replace('چاه دهلران ', 'D')}</span>
            </button>
          ))}

          {focused && hudLocked && (
            <div
              className="deh-ar-hud"
              style={{
                left: `min(${Math.min(focused.x + 6, 72)}%, 72%)`,
                top: `min(${Math.max(focused.y - 8, 8)}%, 70%)`,
                borderColor: STATUS_COLOR[focused.status],
              }}
            >
              <div className="hud-title">
                <strong>{focused.labelFa}</strong>
                <em style={{ color: STATUS_COLOR[focused.status] }}>
                  {STATUS_LABEL_FA[focused.status]}
                </em>
              </div>
              <div className="hud-grid">
                {focused.hud.thp != null && (
                  <div>
                    <span>فشار سرچاهی</span>
                    <b>{focused.hud.thp} psi</b>
                  </div>
                )}
                {focused.hud.tht != null && (
                  <div>
                    <span>دمای سرچاهی</span>
                    <b>{focused.hud.tht} °C</b>
                  </div>
                )}
                {focused.hud.oil != null && (
                  <div>
                    <span>نفت</span>
                    <b>{focused.hud.oil} bbl/d</b>
                  </div>
                )}
                {focused.hud.waterCut != null && (
                  <div>
                    <span>درصد آب تولیدی</span>
                    <b>{focused.hud.waterCut}%</b>
                  </div>
                )}
                {focused.hud.vfm != null && (
                  <div className="accent">
                    <span>دبی‌سنج مجازی</span>
                    <b>{focused.hud.vfm} bbl/d</b>
                  </div>
                )}
                {focused.hud.pumpOnline != null && (
                  <div>
                    <span>پمپ</span>
                    <b>{focused.hud.pumpOnline ? 'آنلاین' : 'آفلاین'}</b>
                  </div>
                )}
              </div>
              <p className="hud-hint">لنگر قفل شد · داده زنده میدان دهلران</p>
            </div>
          )}

          <div className="deh-ar-compass">N · میدان دهلران</div>
        </div>
      </section>

      <div className="ar-content-grid">
        <div className="devices-section">
          <h2>دستگاه‌های واقعیت افزوده میدان</h2>
          <div className="devices-list">
            {devices.map((device) => (
              <div
                key={device.deviceId}
                className={`device-card ${device.connectionStatus} ${
                  selectedDevice === device.deviceId ? 'selected' : ''
                }`}
                onClick={() => setSelectedDevice(device.deviceId)}
              >
                <div className="device-header">
                  <span className="device-id">{device.deviceId}</span>
                  <span className={`connection-status ${device.connectionStatus}`}>
                    {device.connectionStatus === 'connected' ? 'متصل' : 'قطع'}
                  </span>
                </div>
                <div className="device-info">
                  <p>
                    <strong>نوع:</strong> {device.deviceType}
                  </p>
                  <p>
                    <strong>کاربر:</strong> {device.userFa} ({device.roleFa})
                  </p>
                  <p>
                    <strong>موقعیت:</strong> {device.locationFa}
                  </p>
                  <p>
                    <strong>چاه:</strong> {device.wellId}
                  </p>
                  <p>
                    <strong>سیگنال:</strong> {device.signalDbm} dBm
                  </p>
                  <p>
                    <strong>آخرین به‌روزرسانی:</strong> {device.lastUpdateFa}
                  </p>
                </div>
                <div className="battery-indicator">
                  <div className="battery-bar">
                    <div
                      className={`battery-fill ${
                        device.batteryLevel > 50 ? 'high' : device.batteryLevel > 20 ? 'medium' : 'low'
                      }`}
                      style={{ width: `${device.batteryLevel}%` }}
                    />
                  </div>
                  <span className="bat-txt">{device.batteryLevel}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="sessions-section">
          <h2>نشست‌های فعال فیلدی</h2>
          {sessions.length > 0 ? (
            <div className="sessions-list">
              {sessions.map((session) => (
                <div key={session.sessionId} className="session-card">
                  <div className="session-header">
                    <h3>{session.userFa}</h3>
                    <span className="session-duration">{session.durationMin} دقیقه</span>
                  </div>
                  <div className="session-info">
                    <p>
                      <strong>ماموریت:</strong> {session.taskFa}
                    </p>
                    <p>
                      <strong>دستگاه:</strong> {session.deviceId}
                    </p>
                    <p>
                      <strong>چاه:</strong> {session.wellId}
                    </p>
                    <p>
                      <strong>شروع:</strong> {session.startTimeFa}
                    </p>
                    <p>
                      <strong>چک‌لیست:</strong> {session.checklistDone}/{session.checklistTotal}
                    </p>
                    <p>
                      <strong>حاشیه نویسی:</strong> {session.annotationsCreated}
                    </p>
                  </div>
                  <div className="components-list">
                    <strong>قطعات دیده‌شده در واقعیت افزوده:</strong>
                    <div className="components-tags">
                      {session.componentsViewed.map((comp) => (
                        <span key={comp} className="component-tag">
                          {comp}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="no-sessions">
              <p>نشست فعالی نیست</p>
            </div>
          )}
        </div>
      </div>

      <div className="bim-components-section">
        <h2>قطعات مدل اطلاعات تأسیسات قابل‌نمایش در واقعیت افزوده — {selectedWell}</h2>
        <p className="section-sub">
          هر قطعه با داده زنده و راهنمای بصری برای تکنسین هدست / تبلت
        </p>
        <div className="components-grid">
          {bim.map((component) => (
            <div key={component.componentId} className={`component-card ${component.status}`}>
              <div className="component-header">
                <h3>{component.nameFa}</h3>
                <span className={`status-badge ${component.status}`}>
                  {component.status === 'normal'
                    ? 'عادی'
                    : component.status === 'warning'
                      ? 'هشدار'
                      : 'بحرانی'}
                </span>
              </div>
              <div className="component-info">
                <p>
                  <strong>شناسه:</strong> {component.componentId}
                </p>
                <p>
                  <strong>نوع:</strong> {component.type}
                </p>
                <p>
                  <strong>محل:</strong> {component.locationFa}
                </p>
              </div>
              <div className="realtime-data">
                <h4>داده زنده روی نمایشگر سربلند</h4>
                {component.realTimeData.pressure != null && (
                  <p>
                    فشار: <strong>{component.realTimeData.pressure} psi</strong>
                  </p>
                )}
                {component.realTimeData.temperature != null && (
                  <p>
                    دما: <strong>{component.realTimeData.temperature} °C</strong>
                  </p>
                )}
                {component.realTimeData.flowRate != null && (
                  <p>
                    دبی: <strong>{component.realTimeData.flowRate} bbl/d</strong>
                  </p>
                )}
                {component.realTimeData.waterCut != null && (
                  <p>
                    درصد آب تولیدی: <strong>{component.realTimeData.waterCut}%</strong>
                  </p>
                )}
                {component.realTimeData.currentA != null && (
                  <p>
                    جریان پمپ درون‌چاهی الکتریکی: <strong>{component.realTimeData.currentA} A</strong>
                  </p>
                )}
              </div>
              <p className="ar-hint">{component.arHintFa}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="realtime-chart-section">
        <h2>روند تله‌متری روی پوشش بصری واقعیت افزوده — {selectedWell}</h2>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="t" stroke="#888" />
              <YAxis yAxisId="left" stroke="#888" />
              <YAxis yAxisId="right" orientation="right" stroke="#888" />
              <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #ccc', color: '#111' }} />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="pressure" stroke="#ef5350" name="فشار (psi)" dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="temperature" stroke="#ffa726" name="دما (°C)" dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="oil" stroke="#42a5f5" name="نفت (bbl/d)" dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="vfm" stroke="#66bb6a" name="دبی‌سنج مجازی" strokeDasharray="4 3" dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="waterCut" stroke="#ab47bc" name="درصد آب تولیدی %" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bim-components-section overlay-panel">
        <h2>بسته پوشش بصری ارسالی به هدست</h2>
        <pre>{JSON.stringify(overlay, null, 2)}</pre>
      </div>
    </div>
  )
}
