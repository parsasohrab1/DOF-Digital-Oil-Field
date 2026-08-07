/** میدان دهلران — SOGF field configuration */

export const FIELD = {
  nameFa: 'میدان دهلران',
  nameEn: 'Dehloran Field',
  code: 'DEH',
  clientFa: 'شرکت ملی نفت مناطق مرکزی',
  clientEn: 'National Iranian Central Oilfields Company (CNIOC)',
  wellCount: 16,
  oilTypeFa: 'نفت سنگین',
  oilTypeEn: 'Heavy Oil',
  apiGravity: 29.8,
  regionFa: 'غرب ایران',
} as const

/** ۱۶ حلقه چاه دهلران */
export const DEHLORAN_WELLS = Array.from({ length: 16 }, (_, i) => {
  const n = String(i + 1).padStart(2, '0')
  return {
    id: `DEH-${n}`,
    nameFa: `چاه دهلران ${n}`,
    nameEn: `Dehloran Well ${n}`,
    // approximate relative map positions (0–100)
    x: 12 + (i % 4) * 22 + (i % 3) * 2,
    y: 15 + Math.floor(i / 4) * 20 + (i % 2) * 3,
  }
})

export type WellHealthStatus = 'healthy' | 'warning' | 'critical' | 'offline'

export const STATUS_LABEL_FA: Record<WellHealthStatus, string> = {
  healthy: 'سالم',
  warning: 'هشدار',
  critical: 'مشکل',
  offline: 'آفلاین',
}

export const STATUS_COLOR: Record<WellHealthStatus, string> = {
  healthy: '#2e7d32',
  warning: '#f9a825',
  critical: '#c62828',
  offline: '#616161',
}

/** متغیرهای اندازه‌گیری‌شده توسط سنسورهای چاه و تاسیسات */
export const SENSOR_VARIABLES = [
  { key: 'thp', nameFa: 'فشار سرچاهی', unit: 'psi', category: 'wellhead' },
  { key: 'tht', nameFa: 'دمای سرچاهی', unit: '°C', category: 'wellhead' },
  { key: 'chp', nameFa: 'فشار غلاف', unit: 'psi', category: 'wellhead' },
  { key: 'oil_rate', nameFa: 'دبی نفت', unit: 'bbl/d', category: 'production' },
  { key: 'gas_rate', nameFa: 'دبی گاز', unit: 'Mscf/d', category: 'production' },
  { key: 'water_rate', nameFa: 'دبی آب', unit: 'bbl/d', category: 'production' },
  { key: 'water_cut', nameFa: 'درصد آب تولیدی', unit: '%', category: 'production' },
  { key: 'gor', nameFa: 'نسبت گاز به نفت', unit: 'scf/bbl', category: 'production' },
  { key: 'esp_current', nameFa: 'جریان پمپ درون‌چاهی الکتریکی', unit: 'A', category: 'equipment' },
  { key: 'esp_vibration', nameFa: 'لرزش پمپ', unit: 'mm/s', category: 'equipment' },
  { key: 'esp_temp', nameFa: 'دمای موتور پمپ', unit: '°C', category: 'equipment' },
  { key: 'manifold_p', nameFa: 'فشار منیفولد', unit: 'psi', category: 'facility' },
  { key: 'separator_p', nameFa: 'فشار جداکننده', unit: 'psi', category: 'facility' },
  { key: 'separator_l', nameFa: 'سطح مایع جداکننده', unit: '%', category: 'facility' },
  { key: 'pipeline_p', nameFa: 'فشار خط لوله', unit: 'psi', category: 'facility' },
] as const

function seeded(n: number) {
  const x = Math.sin(n * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

export type WellLiveState = {
  id: string
  nameFa: string
  status: WellHealthStatus
  pumpOnline: boolean
  thp: number
  tht: number
  oilRate: number
  gasRate: number
  waterRate: number
  waterCut: number
  vfmOilRate: number
  healthScore: number
  declinePct30d: number
  equipmentRisk: number
  lastSeenMin: number
}

/** Live synthetic state for Dehloran wells (stable per well, slight time drift) */
export function getDehloranLiveState(tick = Date.now()): WellLiveState[] {
  const t = Math.floor(tick / 15000)
  return DEHLORAN_WELLS.map((w, i) => {
    const r = seeded(i + 1)
    const drift = Math.sin((t + i) * 0.4) * 0.03
    const waterCut = Math.min(85, Math.max(8, 18 + r * 45 + drift * 10))
    const oilBase = 420 + (1 - r) * 680
    const oilRate = Math.max(40, oilBase * (1 - waterCut / 140) * (1 + drift))
    const waterRate = (oilRate * waterCut) / Math.max(1, 100 - waterCut)
    const gasRate = oilRate * (0.35 + r * 0.55)
    const thp = 980 + r * 900 + drift * 40
    const tht = 52 + r * 28 + drift * 2
    const healthScore = Math.round(100 - waterCut * 0.35 - (r > 0.85 ? 25 : r > 0.65 ? 12 : 0))
    const equipmentRisk = Math.round((r > 0.8 ? 55 : r > 0.55 ? 30 : 8) + Math.abs(drift) * 40)
    const pumpOnline = r > 0.08
    let status: WellHealthStatus = 'healthy'
    if (!pumpOnline || healthScore < 45) status = 'critical'
    else if (healthScore < 70 || equipmentRisk > 45 || waterCut > 55) status = 'warning'
    if (r < 0.06) status = 'offline'

    return {
      id: w.id,
      nameFa: w.nameFa,
      status,
      pumpOnline: status !== 'offline' && pumpOnline,
      thp: Math.round(thp),
      tht: Math.round(tht * 10) / 10,
      oilRate: Math.round(oilRate),
      gasRate: Math.round(gasRate),
      waterRate: Math.round(waterRate),
      waterCut: Math.round(waterCut * 10) / 10,
      vfmOilRate: Math.round(oilRate * (0.97 + seeded(i + 9) * 0.06)),
      healthScore: Math.max(20, Math.min(99, healthScore)),
      declinePct30d: Math.round((2 + r * 8 + (waterCut > 50 ? 3 : 0)) * 10) / 10,
      equipmentRisk: Math.min(95, equipmentRisk),
      lastSeenMin: status === 'offline' ? 45 + Math.floor(r * 90) : Math.floor(r * 4),
    }
  })
}

export function fieldTotals(wells: WellLiveState[]) {
  const online = wells.filter((w) => w.status !== 'offline')
  const oil = online.reduce((s, w) => s + w.oilRate, 0)
  const gas = online.reduce((s, w) => s + w.gasRate, 0)
  const water = online.reduce((s, w) => s + w.waterRate, 0)
  const avgWc =
    online.length === 0 ? 0 : online.reduce((s, w) => s + w.waterCut, 0) / online.length
  const healthy = wells.filter((w) => w.status === 'healthy').length
  const warning = wells.filter((w) => w.status === 'warning').length
  const critical = wells.filter((w) => w.status === 'critical').length
  const offline = wells.filter((w) => w.status === 'offline').length
  return { oil, gas, water, avgWc, healthy, warning, critical, offline, online: online.length }
}

/** Water-cut forecast next 90 days for field average */
export function waterCutForecast(currentAvg: number) {
  return Array.from({ length: 7 }, (_, i) => {
    const day = i * 15
    const wc = Math.min(92, currentAvg + i * (1.1 + currentAvg * 0.01))
    return { day: `D+${day}`, waterCut: Math.round(wc * 10) / 10 }
  })
}

/** Decline curve foresight (field oil rate) */
export function declineForecast(currentOil: number) {
  return Array.from({ length: 8 }, (_, i) => {
    const month = i
    const rate = currentOil * Math.exp(-0.045 * month)
    return {
      month: `M${month}`,
      actual: month === 0 ? Math.round(currentOil) : null,
      forecast: Math.round(rate),
    }
  })
}

export type WellForecastPoint = {
  month: string
  oil: number
  waterCut: number
  water: number
}

export type WellProductionForecast = {
  wellId: string
  nameFa: string
  currentOil: number
  currentWaterCut: number
  declinePct30d: number
  declineAnnualPct: number
  waterCutRise90d: number
  oilIn90d: number
  waterCutIn90d: number
  series: WellForecastPoint[]
  status: WellHealthStatus
}

/** پیش‌بینی افت تولید و Water Cut برای هر چاه دهلران (۱۲ ماه) */
export function buildWellProductionForecasts(tick = Date.now()): WellProductionForecast[] {
  const live = getDehloranLiveState(tick)
  return DEHLORAN_WELLS.map((w, i) => {
    const lw = live[i]
    const r = seeded(i + 1)
    // monthly decline rate from 30d figure (approx)
    const monthlyDecline = Math.max(0.008, (lw.declinePct30d / 100) * 0.85 + r * 0.01)
    const wcRisePerMonth = 0.4 + r * 1.1 + (lw.waterCut > 50 ? 0.6 : 0)
    const series: WellForecastPoint[] = Array.from({ length: 13 }, (_, m) => {
      const oil = Math.max(20, lw.oilRate * Math.exp(-monthlyDecline * m))
      const waterCut = Math.min(92, lw.waterCut + wcRisePerMonth * m)
      const water = (oil * waterCut) / Math.max(1, 100 - waterCut)
      return {
        month: m === 0 ? 'اکنون' : `M+${m}`,
        oil: Math.round(oil),
        waterCut: Math.round(waterCut * 10) / 10,
        water: Math.round(water),
      }
    })
    const at3 = series[3]
    return {
      wellId: w.id,
      nameFa: w.nameFa,
      currentOil: lw.oilRate,
      currentWaterCut: lw.waterCut,
      declinePct30d: lw.declinePct30d,
      declineAnnualPct: Math.round((1 - Math.exp(-monthlyDecline * 12)) * 1000) / 10,
      waterCutRise90d: Math.round((at3.waterCut - lw.waterCut) * 10) / 10,
      oilIn90d: at3.oil,
      waterCutIn90d: at3.waterCut,
      series,
      status: lw.status,
    }
  })
}


export type DehloranWell3DPayload = {
  wellName: string
  totalDepth: number
  depthData: Array<{
    depth: number
    pressure: number
    temperature: number
    flowRate: number
    status: 'normal' | 'warning' | 'critical'
  }>
  surfaceData: {
    wellheadPressure: number
    wellheadTemperature: number
    flowRate: number
  }
  trajectory?: {
    md_points: Array<{ md: number; inclination: number; azimuth: number }>
  }
  riskZones?: Array<{
    name: string
    fromDepth: number
    toDepth: number
    severity: 'warning' | 'critical'
  }>
  bop?: {
    type: string
    pressureRating: number
    stackHeight: number
    status: 'open' | 'closed' | 'maintenance'
  }
  casings?: Array<{
    depth: number
    outerDiameter: number
    innerDiameter: number
    type: 'conductor' | 'surface' | 'intermediate' | 'production'
    cementThickness: number
  }>
  wellheadEquipment?: {
    christmasTree: { height: number; width: number; status: 'open' | 'closed' }
    masterValve: { position: number; status: 'open' | 'closed' }
    wingValve: { position: number; status: 'open' | 'closed' }
    chokeValve: { position: number; status: 'open' | 'closed' }
    pressureGauges: Array<{ name: string; value: number; unit: string }>
    flowMeter: { flowRate: number; unit: string }
  }
}

/** Full 3D twin payload for a Dehloran well (API fallback / enrichment) */
export function buildDehloranWell3DData(wellId: string, tick = Date.now()): DehloranWell3DPayload {
  const live = getDehloranLiveState(tick).find((w) => w.id === wellId)
  const idx = Math.max(0, DEHLORAN_WELLS.findIndex((w) => w.id === wellId))
  const r = seeded(idx + 1)
  const totalDepth = Math.round(2200 + r * 900) // ~2200–3100 m typical
  const thp = live?.thp ?? Math.round(980 + r * 900)
  const tht = live?.tht ?? Math.round(52 + r * 28)
  const oil = live?.oilRate ?? Math.round(420 + (1 - r) * 680)
  const statusMap =
    live?.status === 'critical'
      ? 'critical'
      : live?.status === 'warning'
        ? 'warning'
        : 'normal'

  const depthData = Array.from({ length: 24 }, (_, i) => {
    const depth = Math.round((totalDepth / 23) * i)
    const frac = i / 23
    const pressure = Math.round(thp + frac * (2800 + r * 1200))
    const temperature = Math.round((tht + frac * (45 + r * 25)) * 10) / 10
    const flowRate = Math.round(oil * (1 - frac * 0.15))
    let status: 'normal' | 'warning' | 'critical' = 'normal'
    if (i > 18 && r > 0.7) status = 'warning'
    if (i > 20 && r > 0.85) status = 'critical'
    if (statusMap === 'critical' && i > 16) status = 'critical'
    return { depth, pressure, temperature, flowRate, status }
  })

  return {
    wellName: wellId,
    totalDepth,
    depthData,
    surfaceData: {
      wellheadPressure: thp,
      wellheadTemperature: tht,
      flowRate: oil,
    },
    trajectory: {
      md_points: [
        { md: 0, inclination: 0, azimuth: 0 },
        { md: Math.round(totalDepth * 0.35), inclination: 8 + r * 10, azimuth: 120 + idx * 8 },
        { md: Math.round(totalDepth * 0.7), inclination: 18 + r * 12, azimuth: 135 + idx * 6 },
        { md: totalDepth, inclination: 22 + r * 8, azimuth: 140 + idx * 5 },
      ],
    },
    riskZones:
      r > 0.55
        ? [
            {
              name: 'لایه فشار بالا / High-pressure zone',
              fromDepth: Math.round(totalDepth * 0.72),
              toDepth: Math.round(totalDepth * 0.82),
              severity: r > 0.8 ? 'critical' : 'warning',
            },
          ]
        : [],
    bop: {
      type: 'جلوگیری‌کننده حلقوی و رام (۱۵ هزار psi)',
      pressureRating: 15000,
      stackHeight: 3.5,
      status: live?.pumpOnline === false ? 'maintenance' : 'open',
    },
    casings: [
      { depth: 80, outerDiameter: 30, innerDiameter: 28, type: 'conductor', cementThickness: 1.5 },
      { depth: 450, outerDiameter: 20, innerDiameter: 18.5, type: 'surface', cementThickness: 1.2 },
      { depth: Math.round(totalDepth * 0.55), outerDiameter: 13.375, innerDiameter: 12.4, type: 'intermediate', cementThickness: 1.0 },
      { depth: totalDepth, outerDiameter: 9.625, innerDiameter: 8.7, type: 'production', cementThickness: 0.8 },
    ],
    wellheadEquipment: {
      christmasTree: { height: 2.5, width: 1.2, status: live?.status === 'offline' ? 'closed' : 'open' },
      masterValve: { position: live?.status === 'offline' ? 0 : 100, status: live?.status === 'offline' ? 'closed' : 'open' },
      wingValve: { position: 70 + Math.round(r * 20), status: 'open' },
      chokeValve: { position: 40 + Math.round(r * 35), status: 'open' },
      pressureGauges: [
        { name: 'فشار سرچاهی', value: thp, unit: 'psi' },
        { name: 'فشار لوله مغزی', value: Math.round(thp * 0.92), unit: 'psi' },
        { name: 'فشار غلاف', value: Math.round(thp * 0.35), unit: 'psi' },
      ],
      flowMeter: {
        flowRate: live?.vfmOilRate ?? oil,
        unit: 'bbl/day',
      },
    },
  }
}

export function buildAllDehloranWells3D(tick = Date.now()): Record<string, DehloranWell3DPayload> {
  const out: Record<string, DehloranWell3DPayload> = {}
  for (const w of DEHLORAN_WELLS) {
    out[w.id] = buildDehloranWell3DData(w.id, tick)
  }
  return out
}

