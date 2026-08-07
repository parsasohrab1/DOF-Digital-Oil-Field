/**
 * AR / واقعیت افزوده — داده هدفمند میدان دهلران
 * پوشش: دستگاه‌های فیلدی، نشست‌ها، لنگرهای AR، BIM overlays، تله‌متری زنده
 */
import {
  DEHLORAN_WELLS,
  FIELD,
  STATUS_COLOR,
  STATUS_LABEL_FA,
  getDehloranLiveState,
  type WellHealthStatus,
} from './dehloranField'

function seeded(n: number) {
  const x = Math.sin(n * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

export type ArDeviceType = 'HoloLens 2' | 'RealWear Navigator' | 'تبلت واقعیت افزوده میدان'

export type ArDevice = {
  deviceId: string
  deviceType: ArDeviceType
  userFa: string
  roleFa: string
  locationFa: string
  wellId: string
  connectionStatus: 'connected' | 'disconnected'
  batteryLevel: number
  activeSession: boolean
  signalDbm: number
  lastUpdateFa: string
}

export type ArSession = {
  sessionId: string
  deviceId: string
  userFa: string
  wellId: string
  startTimeFa: string
  durationMin: number
  taskFa: string
  componentsViewed: string[]
  annotationsCreated: number
  dataPointsAccessed: number
  checklistDone: number
  checklistTotal: number
}

export type ArAnchor = {
  id: string
  labelFa: string
  kind: 'wellhead' | 'esp' | 'manifold' | 'separator' | 'pipeline'
  x: number // % in viewport
  y: number
  wellId: string
  status: WellHealthStatus
  hud: {
    thp?: number
    tht?: number
    oil?: number
    waterCut?: number
    vfm?: number
    pumpOnline?: boolean
  }
}

export type ArBimComponent = {
  componentId: string
  nameFa: string
  type: 'pump' | 'valve' | 'sensor' | 'pipeline' | 'tree' | 'separator'
  locationFa: string
  wellId: string
  status: 'normal' | 'warning' | 'critical'
  realTimeData: {
    pressure?: number
    temperature?: number
    flowRate?: number
    waterCut?: number
    currentA?: number
  }
  arHintFa: string
}

const TECHNICIANS = [
  { name: 'مهندس رضایی', role: 'تکنسین سرچاهی' },
  { name: 'مهندس کریمی', role: 'متخصص پمپ درون‌چاهی الکتریکی' },
  { name: 'مهندس احمدی', role: 'بازرس ایمنی' },
  { name: 'مهندس موسوی', role: 'اپراتور تولید' },
  { name: 'مهندس نوری', role: 'پشتیبان میدان' },
]

export function buildDehloranArDevices(tick = Date.now()): ArDevice[] {
  const live = getDehloranLiveState(tick)
  const types: ArDeviceType[] = ['HoloLens 2', 'RealWear Navigator', 'تبلت واقعیت افزوده میدان']
  return Array.from({ length: 5 }, (_, i) => {
    const well = DEHLORAN_WELLS[i * 3]
    const lw = live.find((w) => w.id === well.id) || live[i]
    const r = seeded(i + 11)
    const connected = i !== 4 || r > 0.3
    const tech = TECHNICIANS[i]
    return {
      deviceId: `AR-DEH-${String(i + 1).padStart(2, '0')}`,
      deviceType: types[i % 3],
      userFa: tech.name,
      roleFa: tech.role,
      locationFa: `پلتفرم ${well.nameFa}`,
      wellId: well.id,
      connectionStatus: connected ? 'connected' : 'disconnected',
      batteryLevel: connected ? Math.round(35 + r * 60) : 0,
      activeSession: connected && i < 3,
      signalDbm: connected ? Math.round(-55 - r * 25) : -110,
      lastUpdateFa: connected ? 'همین الان' : `${10 + Math.floor(r * 20)} دقیقه پیش`,
    }
  })
}

export function buildDehloranArSessions(devices: ArDevice[], tick = Date.now()): ArSession[] {
  return devices
    .filter((d) => d.activeSession)
    .map((d, i) => {
      const r = seeded(i + 30)
      const comps = [
        `درخت کریسمس ${d.wellId}`,
        `پمپ درون‌چاهی الکتریکی ${d.wellId}`,
        `شیر اصلی ${d.wellId}`,
        `سنسور فشار سرچاهی ${d.wellId}`,
        `منیفولد جریان`,
      ].slice(0, 3 + Math.floor(r * 2))
      return {
        sessionId: `SES-DEH-${String(i + 1).padStart(3, '0')}`,
        deviceId: d.deviceId,
        userFa: d.userFa,
        wellId: d.wellId,
        startTimeFa: `${8 + i}:${String(10 + i * 7).padStart(2, '0')}`,
        durationMin: Math.round(12 + r * 40),
        taskFa:
          i === 0
            ? 'بازرسی سرچاهی و ثبت درصد آب تولیدی'
            : i === 1
              ? 'عیب‌یابی لرزش پمپ درون‌چاهی الکتریکی'
              : 'تأیید هم‌خوانی دبی‌سنج مجازی با اندازه‌گیری',
        componentsViewed: comps,
        annotationsCreated: Math.round(1 + r * 5),
        dataPointsAccessed: Math.round(20 + r * 80),
        checklistDone: Math.round(4 + r * 6),
        checklistTotal: 10,
      }
    })
}

/** لنگرهای بصری AR روی نقشه میدان (۱۶ چاه + چند تأسیسات) */
export function buildDehloranArAnchors(tick = Date.now()): ArAnchor[] {
  const live = getDehloranLiveState(tick)
  const wellAnchors: ArAnchor[] = DEHLORAN_WELLS.map((w) => {
    const lw = live.find((x) => x.id === w.id)!
    return {
      id: `ANC-${w.id}`,
      labelFa: w.nameFa,
      kind: 'wellhead',
      x: w.x,
      y: w.y,
      wellId: w.id,
      status: lw.status,
      hud: {
        thp: lw.thp,
        tht: lw.tht,
        oil: lw.oilRate,
        waterCut: lw.waterCut,
        vfm: lw.vfmOilRate,
        pumpOnline: lw.pumpOnline,
      },
    }
  })

  const facilities: ArAnchor[] = [
    {
      id: 'ANC-MANIFOLD',
      labelFa: 'منیفولد تولید دهلران',
      kind: 'manifold',
      x: 78,
      y: 42,
      wellId: 'FAC-01',
      status: 'healthy',
      hud: { thp: 920, oil: live.reduce((s, w) => s + (w.status === 'offline' ? 0 : w.oilRate), 0) },
    },
    {
      id: 'ANC-SEP',
      labelFa: 'جداکننده سه‌فازی',
      kind: 'separator',
      x: 88,
      y: 58,
      wellId: 'FAC-02',
      status: 'warning',
      hud: { thp: 210, tht: 48, waterCut: 34 },
    },
  ]

  return [...wellAnchors, ...facilities]
}

export function buildDehloranArBim(wellId: string, tick = Date.now()): ArBimComponent[] {
  const lw = getDehloranLiveState(tick).find((w) => w.id === wellId) || getDehloranLiveState(tick)[0]
  const st =
    lw.status === 'critical' ? 'critical' : lw.status === 'warning' ? 'warning' : 'normal'

  return [
    {
      componentId: `${wellId}-TREE`,
      nameFa: 'درخت کریسمس / Christmas Tree',
      type: 'tree',
      locationFa: 'سرچاه',
      wellId,
      status: st,
      realTimeData: { pressure: lw.thp, temperature: lw.tht, flowRate: lw.oilRate },
      arHintFa: 'شیر اصلی و بال را در واقعیت افزوده هایلایت کنید — وضعیت باز/بسته روی نمایشگر سربلند',
    },
    {
      componentId: `${wellId}-ESP`,
      nameFa: 'پمپ درون‌چاهی الکتریکی',
      type: 'pump',
      locationFa: 'لوله مغزی',
      wellId,
      status: lw.equipmentRisk > 50 ? 'warning' : lw.pumpOnline ? 'normal' : 'critical',
      realTimeData: {
        currentA: lw.pumpOnline ? Math.round(28 + lw.equipmentRisk * 0.15) : 0,
        temperature: lw.pumpOnline ? Math.round(62 + lw.equipmentRisk * 0.2) : undefined,
        flowRate: lw.oilRate,
      },
      arHintFa: 'لرزش و آمپر را روی پلاک پمپ نشان دهید — هشدار خرابی پیش‌بینانه',
    },
    {
      componentId: `${wellId}-MV`,
      nameFa: 'شیر اصلی (Master Valve)',
      type: 'valve',
      locationFa: 'درخت کریسمس',
      wellId,
      status: lw.status === 'offline' ? 'critical' : 'normal',
      realTimeData: { pressure: Math.round(lw.thp * 0.92) },
      arHintFa: 'درصد باز بودن شیر را به‌صورت گیج مجازی روی قطعه نشان دهید',
    },
    {
      componentId: `${wellId}-THP`,
      nameFa: 'سنسور فشار سرچاهی',
      type: 'sensor',
      locationFa: 'Tubing Head',
      wellId,
      status: 'normal',
      realTimeData: { pressure: lw.thp, temperature: lw.tht },
      arHintFa: 'روند ۱۵ دقیقه‌ای فشار را به‌صورت اسپارک‌لاین واقعیت افزوده نمایش دهید',
    },
    {
      componentId: `${wellId}-VFM`,
      nameFa: 'دبی‌سنج مجازی با پوشش بصری',
      type: 'sensor',
      locationFa: 'مدل نرم‌افزاری',
      wellId,
      status: Math.abs(lw.oilRate - lw.vfmOilRate) / Math.max(1, lw.oilRate) > 0.08 ? 'warning' : 'normal',
      realTimeData: { flowRate: lw.vfmOilRate, waterCut: lw.waterCut },
      arHintFa: 'مقایسه دبی‌سنج مجازی با دبی مرجع — بدون نیاز به دبی‌سنج فیزیکی جداگانه',
    },
    {
      componentId: `${wellId}-FL`,
      nameFa: 'خط جریان تولید',
      type: 'pipeline',
      locationFa: 'Flowline به منیفولد',
      wellId,
      status: 'normal',
      realTimeData: {
        flowRate: lw.oilRate + lw.waterRate,
        temperature: Math.round(lw.tht - 4),
        pressure: Math.round(lw.thp * 0.88),
      },
      arHintFa: 'مسیر لوله را روی زمین با رنگ وضعیت سلامت کدگذاری کنید',
    },
  ]
}

export function buildArTelemetrySeries(wellId: string, tick = Date.now()) {
  const lw = getDehloranLiveState(tick).find((w) => w.id === wellId) || getDehloranLiveState(tick)[0]
  return Array.from({ length: 24 }, (_, i) => {
    const drift = Math.sin((i + wellId.length) * 0.45) * 0.04
    return {
      t: `${i}`,
      pressure: Math.round(lw.thp * (1 + drift)),
      temperature: Math.round((lw.tht + drift * 8) * 10) / 10,
      oil: Math.round(lw.oilRate * (1 + drift * 0.5)),
      waterCut: Math.round((lw.waterCut + drift * 5) * 10) / 10,
      vfm: Math.round(lw.vfmOilRate * (1 + drift * 0.3)),
    }
  })
}

export function buildArOverlayPayload(wellId: string, tick = Date.now()) {
  const lw = getDehloranLiveState(tick).find((w) => w.id === wellId) || getDehloranLiveState(tick)[0]
  const well = DEHLORAN_WELLS.find((w) => w.id === wellId)
  return {
    field: FIELD.nameFa,
    client: FIELD.clientFa,
    well_id: wellId,
    well_name_fa: well?.nameFa,
    oil_api: FIELD.apiGravity,
    status: lw.status,
    status_fa: STATUS_LABEL_FA[lw.status],
    status_color: STATUS_COLOR[lw.status],
    anchors: [
      { id: 'hud-thp', label: 'فشار سرچاهی', value: lw.thp, unit: 'psi' },
      { id: 'hud-tht', label: 'دمای سرچاهی', value: lw.tht, unit: '°C' },
      { id: 'hud-oil', label: 'نفت', value: lw.oilRate, unit: 'bbl/d' },
      { id: 'hud-wc', label: 'درصد آب تولیدی', value: lw.waterCut, unit: '%' },
      { id: 'hud-vfm', label: 'دبی‌سنج مجازی', value: lw.vfmOilRate, unit: 'bbl/d' },
    ],
    equipment: {
      pump_online: lw.pumpOnline,
      equipment_risk: lw.equipmentRisk,
      health_score: lw.healthScore,
    },
    guidance_fa: [
      'هدست را به سمت درخت کریسمس بگیرید تا لنگر قفل شود',
      'برای پمپ درون‌چاهی الکتریکی روی پلاک موتور فوکوس کنید',
      'در صورت درصد آب تولیدی بالا، چک‌لیست جداکننده را باز کنید',
    ],
    timestamp: new Date(tick).toISOString(),
  }
}

export { STATUS_COLOR, STATUS_LABEL_FA }
