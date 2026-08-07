/**
 * SCADA / PLC — معماری هدفمند میدان دهلران
 * OPC-UA برای RTU سرچاهی و اسکادای تأسیسات
 * Modbus TCP برای VFD پمپ ESP و PLC فرآیند
 */
import {
  DEHLORAN_WELLS,
  FIELD,
  getDehloranLiveState,
  type WellLiveState,
} from './dehloranField'

export type ProtocolKind = 'OPC-UA' | 'Modbus-TCP' | 'MQTT-Bridge'
export type ConnStatus = 'online' | 'degraded' | 'offline'
export type TagQuality = 'good' | 'uncertain' | 'bad'

export type ScadaConnection = {
  id: string
  nameFa: string
  nameEn: string
  protocol: ProtocolKind
  role: string
  host: string
  port: number
  status: ConnStatus
  scanMs: number
  tagsCount: number
  purpose: string
  asset: string
}

export type ScadaTag = {
  id: string
  connectionId: string
  protocol: ProtocolKind
  address: string
  nameFa: string
  nameEn: string
  unit: string
  dataType: 'Float' | 'Int16' | 'Bool' | 'String'
  writable: boolean
  value: number | boolean | string
  quality: TagQuality
  wellId?: string
  category: 'wellhead' | 'esp' | 'facility' | 'safety' | 'control'
  purpose: string
}

export type ModbusRegister = {
  connectionId: string
  address: number
  nameFa: string
  nameEn: string
  type: 'Holding' | 'Input' | 'Coil'
  scale: number
  unit: string
  value: number | boolean
  purpose: string
  wellId?: string
}

export type PipelineHop = {
  from: string
  to: string
  rateHz: number
  status: 'ok' | 'lag' | 'fail'
}

function seeded(n: number) {
  const x = Math.sin(n * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

export function getScadaConnections(tick = Date.now()): ScadaConnection[] {
  const t = Math.floor(tick / 20000)
  const wells = getDehloranLiveState(tick)
  const offlineWells = wells.filter((w) => w.status === 'offline').length

  const base: Omit<ScadaConnection, 'status' | 'tagsCount'>[] = [
    {
      id: 'OPC-RTU-PAD-A',
      nameFa: 'پایانه راه دور پد A (چاه ۱–۴)',
      nameEn: 'Well Pad A RTU',
      protocol: 'OPC-UA',
      role: 'Wellhead RTU',
      host: '10.40.10.11',
      port: 4840,
      scanMs: 1000,
      purpose: 'خواندن فشار سرچاهی، دمای سرچاهی، فشار غلاف و وضعیت شیرهای سرچاهی پد A',
      asset: 'DEH-01…04',
    },
    {
      id: 'OPC-RTU-PAD-B',
      nameFa: 'پایانه راه دور پد B (چاه ۵–۸)',
      nameEn: 'Well Pad B RTU',
      protocol: 'OPC-UA',
      role: 'Wellhead RTU',
      host: '10.40.10.12',
      port: 4840,
      scanMs: 1000,
      purpose: 'تله‌متری سرچاهی و اینترلاک ایمنی پد B',
      asset: 'DEH-05…08',
    },
    {
      id: 'OPC-RTU-PAD-C',
      nameFa: 'پایانه راه دور پد C (چاه ۹–۱۲)',
      nameEn: 'Well Pad C RTU',
      protocol: 'OPC-UA',
      role: 'Wellhead RTU',
      host: '10.40.10.13',
      port: 4840,
      scanMs: 1000,
      purpose: 'فشار/دما و وضعیت شیر کنترل جریان پد C',
      asset: 'DEH-09…12',
    },
    {
      id: 'OPC-RTU-PAD-D',
      nameFa: 'پایانه راه دور پد D (چاه ۱۳–۱۶)',
      nameEn: 'Well Pad D RTU',
      protocol: 'OPC-UA',
      role: 'Wellhead RTU',
      host: '10.40.10.14',
      port: 4840,
      scanMs: 1000,
      purpose: 'تله‌متری پد D و سیگنال توقف اضطراری محلی',
      asset: 'DEH-13…16',
    },
    {
      id: 'OPC-FACILITY',
      nameFa: 'اسکادای تأسیسات سطح',
      nameEn: 'Surface Facility SCADA',
      protocol: 'OPC-UA',
      role: 'Facility SCADA',
      host: '10.40.20.5',
      port: 4840,
      scanMs: 2000,
      purpose: 'منیفولد، جداکننده، خط لوله و سطح مخازن',
      asset: 'Separator / Manifold',
    },
    {
      id: 'MB-ESP-VFD',
      nameFa: 'شبکه درایو فرکانس متغیر پمپ‌های درون‌چاهی الکتریکی',
      nameEn: 'ESP VFD Network',
      protocol: 'Modbus-TCP',
      role: 'Drive PLC',
      host: '10.40.30.20',
      port: 502,
      scanMs: 500,
      purpose: 'سرعت، جریان، لرزش و دمای موتور پمپ درون‌چاهی الکتریکی',
      asset: 'ESP Drives',
    },
    {
      id: 'MB-PROCESS-PLC',
      nameFa: 'کنترل‌گر منطقی برنامه‌پذیر فرآیند تولید',
      nameEn: 'Production Process PLC',
      protocol: 'Modbus-TCP',
      role: 'Process PLC',
      host: '10.40.30.30',
      port: 502,
      scanMs: 500,
      purpose: 'ست‌پوینت شیر کنترل جریان، گاز لیفت و اینترلاک فرآیند',
      asset: 'Process Control',
    },
    {
      id: 'MQTT-EDGE',
      nameFa: 'پل لبه بی‌سیم',
      nameEn: 'Edge MQTT Bridge',
      protocol: 'MQTT-Bridge',
      role: 'Edge Gateway',
      host: '10.40.40.8',
      port: 1883,
      scanMs: 5000,
      purpose: 'سنسورهای کمکی بی‌سیم و همگام‌سازی با صف پیام کافکا',
      asset: 'Edge / Soft sensors',
    },
  ]

  return base.map((c, i) => {
    const r = seeded(i + 1 + t)
    let status: ConnStatus = 'online'
    if (c.id.includes('PAD-D') && offlineWells > 0) status = 'degraded'
    if (c.protocol === 'MQTT-Bridge' && r > 0.82) status = 'degraded'
    if (r > 0.97) status = 'offline'
    const tagsCount =
      c.protocol === 'OPC-UA' && c.role === 'Wellhead RTU'
        ? 28
        : c.protocol === 'OPC-UA'
          ? 36
          : c.protocol === 'Modbus-TCP'
            ? 48
            : 12
    return { ...c, status, tagsCount }
  })
}

function qualityFromWell(w: WellLiveState): TagQuality {
  if (w.status === 'offline') return 'bad'
  if (w.status === 'critical' || w.status === 'warning') return 'uncertain'
  return 'good'
}

export function lightFromQuality(q: TagQuality): 'green' | 'yellow' | 'red' {
  if (q === 'good') return 'green'
  if (q === 'uncertain') return 'yellow'
  return 'red'
}

export function getScadaTags(tick = Date.now(), wellFilter?: string): ScadaTag[] {
  const wells = getDehloranLiveState(tick)
  const tags: ScadaTag[] = []

  const padOf = (i: number) => {
    if (i < 4) return 'OPC-RTU-PAD-A'
    if (i < 8) return 'OPC-RTU-PAD-B'
    if (i < 12) return 'OPC-RTU-PAD-C'
    return 'OPC-RTU-PAD-D'
  }

  wells.forEach((w, i) => {
    if (wellFilter && w.id !== wellFilter) return
    const conn = padOf(i)
    const q = qualityFromWell(w)
    const n = w.id.replace('DEH-', '')

    tags.push(
      {
        id: `${w.id}.THP`,
        connectionId: conn,
        protocol: 'OPC-UA',
        address: `ns=2;s=Wells.${w.id}.THP`,
        nameFa: `فشار سرچاهی ${n}`,
        nameEn: `${w.id} THP`,
        unit: 'psi',
        dataType: 'Float',
        writable: false,
        value: w.thp,
        quality: q,
        wellId: w.id,
        category: 'wellhead',
        purpose: 'پایش فشار سرچاه برای کنترل تولید و ایمنی',
      },
      {
        id: `${w.id}.THT`,
        connectionId: conn,
        protocol: 'OPC-UA',
        address: `ns=2;s=Wells.${w.id}.THT`,
        nameFa: `دمای سرچاهی ${n}`,
        nameEn: `${w.id} THT`,
        unit: '°C',
        dataType: 'Float',
        writable: false,
        value: w.tht,
        quality: q,
        wellId: w.id,
        category: 'wellhead',
        purpose: 'پایش دمای سیال سرچاه',
      },
      {
        id: `${w.id}.CHP`,
        connectionId: conn,
        protocol: 'OPC-UA',
        address: `ns=2;s=Wells.${w.id}.CHP`,
        nameFa: `فشار غلاف ${n}`,
        nameEn: `${w.id} CHP`,
        unit: 'psi',
        dataType: 'Float',
        writable: false,
        value: Math.round(w.thp * 0.72),
        quality: q,
        wellId: w.id,
        category: 'wellhead',
        purpose: 'تشخیص نشتی غلاف و یکپارچگی چاه',
      },
      {
        id: `${w.id}.CHOKE_POS`,
        connectionId: 'MB-PROCESS-PLC',
        protocol: 'Modbus-TCP',
        address: `Holding[${40010 + i}]`,
        nameFa: `موقعیت شیر کنترل جریان ${n}`,
        nameEn: `${w.id} Choke %`,
        unit: '%',
        dataType: 'Float',
        writable: true,
        value: Math.round(40 + seeded(i + 2) * 35),
        quality: w.status === 'offline' ? 'bad' : 'good',
        wellId: w.id,
        category: 'control',
        purpose: 'ست‌پوینت دستی/اپراتور هوشمند برای تنظیم دبی',
      },
      {
        id: `${w.id}.ESP_HZ`,
        connectionId: 'MB-ESP-VFD',
        protocol: 'Modbus-TCP',
        address: `Holding[${41000 + i * 10}]`,
        nameFa: `فرکانس پمپ درون‌چاهی الکتریکی ${n}`,
        nameEn: `${w.id} ESP Hz`,
        unit: 'Hz',
        dataType: 'Float',
        writable: true,
        value: w.pumpOnline ? Math.round(45 + seeded(i + 5) * 15) : 0,
        quality: w.pumpOnline ? qualityFromWell(w) : 'bad',
        wellId: w.id,
        category: 'esp',
        purpose: 'کنترل سرعت پمپ برای حفظ دبی هدف',
      },
      {
        id: `${w.id}.ESP_AMP`,
        connectionId: 'MB-ESP-VFD',
        protocol: 'Modbus-TCP',
        address: `Input[${30010 + i}]`,
        nameFa: `جریان پمپ درون‌چاهی الکتریکی ${n}`,
        nameEn: `${w.id} ESP Current`,
        unit: 'A',
        dataType: 'Float',
        writable: false,
        value: w.pumpOnline ? Math.round((28 + w.equipmentRisk * 0.15) * 10) / 10 : 0,
        quality: w.pumpOnline ? qualityFromWell(w) : 'bad',
        wellId: w.id,
        category: 'esp',
        purpose: 'تشخیص اضافه جریان و خرابی قریب‌الوقوع',
      },
      {
        id: `${w.id}.ESD`,
        connectionId: conn,
        protocol: 'OPC-UA',
        address: `ns=2;s=Wells.${w.id}.ESD_TRIP`,
        nameFa: `تریپ توقف اضطراری ${n}`,
        nameEn: `${w.id} ESD`,
        unit: '',
        dataType: 'Bool',
        writable: false,
        value: w.status === 'critical' && seeded(i + 9) > 0.7,
        quality: 'good',
        wellId: w.id,
        category: 'safety',
        purpose: 'وضعیت توقف اضطراری سرچاه',
      }
    )
  })

  if (!wellFilter) {
    const online = wells.filter((w) => w.status !== 'offline')
    const avgWc =
      online.reduce((s, w) => s + w.waterCut, 0) / Math.max(1, online.length)
    const oil = online.reduce((s, w) => s + w.oilRate, 0)

    tags.push(
      {
        id: 'FAC.MANIFOLD_P',
        connectionId: 'OPC-FACILITY',
        protocol: 'OPC-UA',
        address: 'ns=2;s=Facility.Manifold.Pressure',
        nameFa: 'فشار منیفولد',
        nameEn: 'Manifold Pressure',
        unit: 'psi',
        dataType: 'Float',
        writable: false,
        value: Math.round(900 + avgWc * 4),
        quality: 'good',
        category: 'facility',
        purpose: 'پایداری جمع‌آوری سیال از ۱۶ چاه',
      },
      {
        id: 'FAC.SEP_P',
        connectionId: 'OPC-FACILITY',
        protocol: 'OPC-UA',
        address: 'ns=2;s=Facility.Separator.Pressure',
        nameFa: 'فشار جداکننده',
        nameEn: 'Separator Pressure',
        unit: 'psi',
        dataType: 'Float',
        writable: true,
        value: Math.round(160 + avgWc * 0.8),
        quality: 'good',
        category: 'facility',
        purpose: 'ست‌پوینت جداسازی نفت/گاز/آب',
      },
      {
        id: 'FAC.SEP_LEVEL',
        connectionId: 'OPC-FACILITY',
        protocol: 'OPC-UA',
        address: 'ns=2;s=Facility.Separator.Level',
        nameFa: 'سطح مایع جداکننده',
        nameEn: 'Separator Level',
        unit: '%',
        dataType: 'Float',
        writable: false,
        value: Math.round(45 + avgWc * 0.3),
        quality: avgWc > 60 ? 'uncertain' : 'good',
        category: 'facility',
        purpose: 'جلوگیری از سرریز / خشک شدن جداکننده',
      },
      {
        id: 'FAC.EXPORT_OIL',
        connectionId: 'OPC-FACILITY',
        protocol: 'OPC-UA',
        address: 'ns=2;s=Facility.Export.OilRate',
        nameFa: 'دبی صادرات نفت',
        nameEn: 'Export Oil Rate',
        unit: 'bbl/d',
        dataType: 'Float',
        writable: false,
        value: Math.round(oil * 0.98),
        quality: 'good',
        category: 'facility',
        purpose: 'تطبیق تولید میدان با اندازه‌گیری صادرات',
      },
      {
        id: 'FAC.PIPELINE_P',
        connectionId: 'OPC-FACILITY',
        protocol: 'OPC-UA',
        address: 'ns=2;s=Facility.Pipeline.Pressure',
        nameFa: 'فشار خط لوله',
        nameEn: 'Pipeline Pressure',
        unit: 'psi',
        dataType: 'Float',
        writable: false,
        value: Math.round(720 + seeded(42) * 80),
        quality: 'good',
        category: 'facility',
        purpose: 'پایش یکپارچگی خط انتقال',
      }
    )
  }

  return tags
}

export function getModbusMap(tick = Date.now(), wellId?: string): ModbusRegister[] {
  const wells = getDehloranLiveState(tick).filter((w) => !wellId || w.id === wellId)
  const regs: ModbusRegister[] = []

  wells.slice(0, wellId ? 1 : 8).forEach((w) => {
    const idx = DEHLORAN_WELLS.findIndex((x) => x.id === w.id)
    const base = 41000 + idx * 10
    regs.push(
      {
        connectionId: 'MB-ESP-VFD',
        address: base,
        nameFa: `ست‌پوینت سرعت پمپ درون‌چاهی الکتریکی ${w.id}`,
        nameEn: 'ESP Speed SP',
        type: 'Holding',
        scale: 0.1,
        unit: 'Hz',
        value: w.pumpOnline ? Math.round(45 + seeded(idx + 2) * 15) : 0,
        purpose: 'نوشتن سرعت هدف به درایو',
        wellId: w.id,
      },
      {
        connectionId: 'MB-ESP-VFD',
        address: base + 1,
        nameFa: `جریان واقعی پمپ درون‌چاهی الکتریکی ${w.id}`,
        nameEn: 'ESP Current Feedback',
        type: 'Input',
        scale: 0.1,
        unit: 'A',
        value: w.pumpOnline ? Math.round((28 + w.equipmentRisk * 0.15) * 10) / 10 : 0,
        purpose: 'فیدبک حفاظتی اضافه جریان',
        wellId: w.id,
      },
      {
        connectionId: 'MB-ESP-VFD',
        address: base + 2,
        nameFa: `لرزش موتور ${w.id}`,
        nameEn: 'Motor Vibration',
        type: 'Input',
        scale: 0.01,
        unit: 'mm/s',
        value: w.pumpOnline ? Math.round((1.2 + w.equipmentRisk * 0.04) * 100) / 100 : 0,
        purpose: 'هشدار مکانیکی قبل از خرابی',
        wellId: w.id,
      },
      {
        connectionId: 'MB-PROCESS-PLC',
        address: 40010 + idx,
        nameFa: `ست‌پوینت شیر کنترل جریان ${w.id}`,
        nameEn: 'Choke Setpoint',
        type: 'Holding',
        scale: 1,
        unit: '%',
        value: Math.round(40 + seeded(idx + 4) * 35),
        purpose: 'کنترل دبی از طریق چوک',
        wellId: w.id,
      },
      {
        connectionId: 'MB-PROCESS-PLC',
        address: 10 + idx,
        nameFa: `مجوز تولید ${w.id}`,
        nameEn: 'Produce Permit',
        type: 'Coil',
        scale: 1,
        unit: '',
        value: w.status !== 'offline' && w.status !== 'critical',
        purpose: 'اجازه باز بودن مسیر تولید',
        wellId: w.id,
      }
    )
  })

  return regs
}

export function getDataPipeline(tick = Date.now()): PipelineHop[] {
  const conns = getScadaConnections(tick)
  const degraded = conns.filter((c) => c.status !== 'online').length
  return [
    { from: 'پایانه راه دور / کنترل‌گر منطقی', to: 'پروتکل ارتباط باز صنعتی / مودباس', rateHz: 2.4, status: degraded ? 'lag' : 'ok' },
    { from: 'پروتکل صنعتی', to: 'ورود داده', rateHz: 1.8, status: 'ok' },
    { from: 'ورود داده', to: 'صف پیام کافکا (داده خام سنسور)', rateHz: 1.8, status: 'ok' },
    { from: 'کافکا', to: 'پایگاه سری‌زمانی + داشبورد', rateHz: 1.5, status: degraded > 2 ? 'lag' : 'ok' },
    { from: 'کنترل‌گر منطقی قابل‌نوشتن', to: 'فرمان و کنترل', rateHz: 0.2, status: 'ok' },
  ]
}

export function scadaSummary(tick = Date.now()) {
  const conns = getScadaConnections(tick)
  const tags = getScadaTags(tick)
  const online = conns.filter((c) => c.status === 'online').length
  const degraded = conns.filter((c) => c.status === 'degraded').length
  const offline = conns.filter((c) => c.status === 'offline').length
  const good = tags.filter((t) => t.quality === 'good').length
  const bad = tags.filter((t) => t.quality === 'bad').length
  const writable = tags.filter((t) => t.writable).length
  const pointsPerSec = conns
    .filter((c) => c.status !== 'offline')
    .reduce((s, c) => s + c.tagsCount / (c.scanMs / 1000), 0)

  return {
    connections: conns.length,
    online,
    degraded,
    offline,
    tags: tags.length,
    good,
    bad,
    uncertain: tags.length - good - bad,
    writable,
    pointsPerSec: Math.round(pointsPerSec),
    opcua: conns.filter((c) => c.protocol === 'OPC-UA').length,
    modbus: conns.filter((c) => c.protocol === 'Modbus-TCP').length,
  }
}

export function tagHistory(tagId: string, baseValue: number, points = 24) {
  const idx = tagId.split('').reduce((s, c) => s + c.charCodeAt(0), 0)
  return Array.from({ length: points }, (_, i) => {
    const wave = Math.sin((i / points) * Math.PI * 2 + seeded(idx) * 5) * 0.04
    return {
      t: `${String(i).padStart(2, '0')}:00`,
      value: Math.round(baseValue * (1 + wave) * 10) / 10,
    }
  })
}

export const PROTOCOL_LABEL_FA: Record<ProtocolKind, string> = {
  'OPC-UA': 'پروتکل ارتباط باز صنعتی',
  'Modbus-TCP': 'مودباس',
  'MQTT-Bridge': 'پل پیام‌رسان بی‌سیم',
}

export type ScadaAlarm = {
  id: string
  severity: 'critical' | 'warning' | 'info'
  wellId?: string
  source: string
  title: string
  detail: string
  action: string
  tagId?: string
  at: string
}

export type PadOverview = {
  pad: string
  nameFa: string
  wellIds: string[]
  oil: number
  avgWc: number
  avgThp: number
  online: number
  alarms: number
  status: ConnStatus
}

export type FacilityHmi = {
  manifoldPsi: number
  separatorPsi: number
  separatorLevel: number
  exportOil: number
  pipelinePsi: number
  gasLiftHeader: number
  waterInjectionPsi: number
  advice: string[]
}

export type Interlock = {
  id: string
  nameFa: string
  state: 'armed' | 'tripped' | 'bypassed'
  condition: string
  effect: string
}

export type OperatorTip = {
  title: string
  detail: string
  priority: 'high' | 'medium' | 'low'
}

/** نمای پدهای تولید برای اپراتور اسکادا */
export function getPadOverviews(tick = Date.now()): PadOverview[] {
  const wells = getDehloranLiveState(tick)
  const conns = getScadaConnections(tick)
  const pads = [
    { pad: 'A', nameFa: 'پد الف — چاه‌های ۱ تا ۴', ids: wells.slice(0, 4), connId: 'OPC-RTU-PAD-A' },
    { pad: 'B', nameFa: 'پد ب — چاه‌های ۵ تا ۸', ids: wells.slice(4, 8), connId: 'OPC-RTU-PAD-B' },
    { pad: 'C', nameFa: 'پد ج — چاه‌های ۹ تا ۱۲', ids: wells.slice(8, 12), connId: 'OPC-RTU-PAD-C' },
    { pad: 'D', nameFa: 'پد د — چاه‌های ۱۳ تا ۱۶', ids: wells.slice(12, 16), connId: 'OPC-RTU-PAD-D' },
  ]
  return pads.map((p) => {
    const onlineWells = p.ids.filter((w) => w.status !== 'offline')
    const oil = onlineWells.reduce((s, w) => s + w.oilRate, 0)
    const avgWc =
      onlineWells.length === 0
        ? 0
        : onlineWells.reduce((s, w) => s + w.waterCut, 0) / onlineWells.length
    const avgThp =
      onlineWells.length === 0
        ? 0
        : onlineWells.reduce((s, w) => s + w.thp, 0) / onlineWells.length
    const alarms = p.ids.filter((w) => w.status === 'warning' || w.status === 'critical').length
    const conn = conns.find((c) => c.id === p.connId)
    return {
      pad: p.pad,
      nameFa: p.nameFa,
      wellIds: p.ids.map((w) => w.id),
      oil: Math.round(oil),
      avgWc: Math.round(avgWc * 10) / 10,
      avgThp: Math.round(avgThp),
      online: onlineWells.length,
      alarms,
      status: conn?.status || 'online',
    }
  })
}

/** پنل تأسیسات سطح (جداکننده / منیفولد / خط لوله) */
export function getFacilityHmi(tick = Date.now()): FacilityHmi {
  const wells = getDehloranLiveState(tick).filter((w) => w.status !== 'offline')
  const oil = wells.reduce((s, w) => s + w.oilRate, 0)
  const avgWc = wells.reduce((s, w) => s + w.waterCut, 0) / Math.max(1, wells.length)
  const manifoldPsi = Math.round(900 + avgWc * 4)
  const separatorPsi = Math.round(160 + avgWc * 0.8)
  const separatorLevel = Math.round(45 + avgWc * 0.3)
  const pipelinePsi = Math.round(720 + seeded(42) * 80)
  const advice: string[] = []
  if (separatorLevel > 78) advice.push('سطح جداکننده بالاست — دبی خروجی آب/نفت را افزایش دهید.')
  if (separatorLevel < 28) advice.push('سطح جداکننده پایین است — از خشک شدن پمپ خروجی جلوگیری کنید.')
  if (separatorPsi > 240) advice.push('فشار جداکننده نزدیک سقف — شیر گاز خروجی را بازتر کنید.')
  if (avgWc > 55) advice.push('درصد آب تولیدی میدان بالاست — تزریق و چوک چاه‌های پرآب را بازبینی کنید.')
  if (pipelinePsi < 600) advice.push('فشار خط لوله پایین — احتمال نشتی یا افت پمپ ایستگاه را بررسی کنید.')
  if (advice.length === 0) advice.push('تأسیسات سطح در محدوده پایدار است — پایش دوره‌ای ادامه یابد.')
  return {
    manifoldPsi,
    separatorPsi,
    separatorLevel,
    exportOil: Math.round(oil * 0.98),
    pipelinePsi,
    gasLiftHeader: Math.round(850 + seeded(7) * 120),
    waterInjectionPsi: Math.round(1400 + seeded(9) * 200),
    advice,
  }
}

/** آلارم‌های صنعتی استخراج‌شده از تگ‌ها و وضعیت چاه */
export function getScadaAlarms(tick = Date.now()): ScadaAlarm[] {
  const wells = getDehloranLiveState(tick)
  const tags = getScadaTags(tick)
  const alarms: ScadaAlarm[] = []
  const now = new Date(tick).toLocaleTimeString('fa-IR')

  wells.forEach((w) => {
    if (w.status === 'critical') {
      alarms.push({
        id: `alm-${w.id}-crit`,
        severity: 'critical',
        wellId: w.id,
        source: 'پایانه سرچاهی',
        title: `وضعیت بحرانی ${w.nameFa}`,
        detail: `امتیاز سلامت ${w.healthScore} · درصد آب ${w.waterCut}% · ریسک تجهیزات ${w.equipmentRisk}%`,
        action: 'بررسی فشار سرچاهی، جریان پمپ و تریپ توقف اضطراری؛ در صورت نیاز چاه را ایمن کنید.',
        tagId: `${w.id}.THP`,
        at: now,
      })
    } else if (w.status === 'warning') {
      alarms.push({
        id: `alm-${w.id}-warn`,
        severity: 'warning',
        wellId: w.id,
        source: 'پایش تولید',
        title: `هشدار عملکرد ${w.id}`,
        detail: `افت ۳۰روزه ${w.declinePct30d}% · آب تولیدی ${w.waterCut}%`,
        action: 'ست‌پوینت شیر کنترل جریان و سرعت پمپ را با اپراتور هوشمند هماهنگ کنید.',
        tagId: `${w.id}.CHOKE_POS`,
        at: now,
      })
    }
    if (!w.pumpOnline) {
      alarms.push({
        id: `alm-${w.id}-esp`,
        severity: 'critical',
        wellId: w.id,
        source: 'درایو پمپ درون‌چاهی',
        title: `پمپ ${w.id} خارج از سرویس`,
        detail: 'فرکانس و جریان پمپ صفر است.',
        action: 'وضعیت درایو فرکانس متغیر، اینترلاک و تغذیه را بررسی کنید.',
        tagId: `${w.id}.ESP_HZ`,
        at: now,
      })
    }
  })

  tags
    .filter((t) => t.quality === 'bad')
    .slice(0, 6)
    .forEach((t) => {
      alarms.push({
        id: `alm-q-${t.id}`,
        severity: 'warning',
        wellId: t.wellId,
        source: t.connectionId,
        title: `کیفیت بد تگ — ${t.nameFa}`,
        detail: `آدرس ${t.address}`,
        action: 'کابل‌کشی، مبدل و ارتباط پایانه راه دور را بررسی کنید.',
        tagId: t.id,
        at: now,
      })
    })

  const fac = getFacilityHmi(tick)
  if (fac.separatorLevel > 78 || fac.separatorLevel < 28) {
    alarms.push({
      id: 'alm-sep-level',
      severity: fac.separatorLevel > 85 || fac.separatorLevel < 22 ? 'critical' : 'warning',
      source: 'اسکادای تأسیسات',
      title: 'سطح غیرعادی جداکننده',
      detail: `سطح فعلی ${fac.separatorLevel}%`,
      action: 'کنترل سطح و شیرهای خروجی نفت/آب را تنظیم کنید.',
      tagId: 'FAC.SEP_LEVEL',
      at: now,
    })
  }

  const order = { critical: 0, warning: 1, info: 2 }
  return alarms.sort((a, b) => order[a.severity] - order[b.severity]).slice(0, 18)
}

export function getInterlocks(tick = Date.now()): Interlock[] {
  const wells = getDehloranLiveState(tick)
  const critical = wells.some((w) => w.status === 'critical')
  const offlinePump = wells.some((w) => !w.pumpOnline)
  return [
    {
      id: 'il-esd',
      nameFa: 'توقف اضطراری سرچاه',
      state: critical ? 'tripped' : 'armed',
      condition: 'فشار غیرمجاز یا فرمان دستی ایمنی',
      effect: 'بستن شیر اصلی و قطع مسیر تولید چاه آسیب‌دیده',
    },
    {
      id: 'il-esp-overcurrent',
      nameFa: 'اضافه‌جریان پمپ درون‌چاهی',
      state: offlinePump ? 'tripped' : 'armed',
      condition: 'جریان موتور بالاتر از حد حفاظتی',
      effect: 'توقف درایو و قفل فرمان افزایش سرعت تا رفع علت',
    },
    {
      id: 'il-sep-hh',
      nameFa: 'سطح بالای جداکننده',
      state: getFacilityHmi(tick).separatorLevel > 80 ? 'tripped' : 'armed',
      condition: 'سطح مایع > ۸۰٪',
      effect: 'کاهش ورودی منیفولد و افزایش خروجی',
    },
    {
      id: 'il-choke-permit',
      nameFa: 'مجوز تغییر شیر کنترل جریان',
      state: 'armed',
      condition: 'نشست فرمان و کنترل + تأیید نقش اپراتور',
      effect: 'اجازه نوشتن ست‌پوینت روی کنترل‌گر منطقی فرآیند',
    },
    {
      id: 'il-comm-loss',
      nameFa: 'قطع ارتباط پایانه راه دور',
      state: getScadaConnections(tick).some((c) => c.status === 'offline') ? 'tripped' : 'armed',
      condition: 'عدم پاسخ بیش از سه دوره پویش',
      effect: 'نگه‌داشت آخرین مقدار ایمن و هشدار به اتاق کنترل',
    },
  ]
}

export function getOperatorTips(tick = Date.now()): OperatorTip[] {
  const pads = getPadOverviews(tick)
  const fac = getFacilityHmi(tick)
  const tips: OperatorTip[] = [
    {
      title: 'اولویت پایش',
      detail: 'ابتدا پد با بیشترین آلارم و سپس جداکننده سطح را چک کنید.',
      priority: 'high',
    },
    {
      title: 'هماهنگی با اپراتور هوشمند',
      detail: 'قبل از نوشتن دستی سرعت پمپ یا شیر کنترل جریان، اپراتور هوشمند داشبورد را موقتاً خاموش کنید.',
      priority: 'medium',
    },
    {
      title: 'نفت سنگین دهلران',
      detail: `درجه سنگینی حدود ${FIELD.apiGravity} — از افت ناگهانی دمای سرچاهی که می‌تواند ویسکوزیته را بالا ببرد غافل نشوید.`,
      priority: 'medium',
    },
  ]
  const worst = [...pads].sort((a, b) => b.alarms - a.alarms)[0]
  if (worst && worst.alarms > 0) {
    tips.unshift({
      title: `تمرکز روی ${worst.nameFa}`,
      detail: `${worst.alarms} آلارم · دبی نفت پد ${worst.oil.toLocaleString()} بشکه در روز`,
      priority: 'high',
    })
  }
  if (fac.advice[0]) {
    tips.push({ title: 'تأسیسات سطح', detail: fac.advice[0], priority: 'medium' })
  }
  return tips
}

export type ControlSetpoint = {
  key: string
  wellId: string
  nameFa: string
  unit: string
  min: number
  max: number
  value: number
  address: string
  purpose: string
}

export function getControlSetpoints(tick = Date.now(), wellId: string): ControlSetpoint[] {
  const regs = getModbusMap(tick, wellId)
  const out: ControlSetpoint[] = []
  for (const r of regs) {
    if (r.type !== 'Holding' || typeof r.value !== 'number') continue
    const isEsp = r.address >= 41000
    out.push({
      key: `${r.connectionId}-${r.address}`,
      wellId: r.wellId || wellId,
      nameFa: r.nameFa,
      unit: r.unit,
      min: isEsp ? 40 : 10,
      max: isEsp ? 70 : 100,
      value: r.value,
      address: String(r.address),
      purpose: r.purpose,
    })
  }
  const sep = getScadaTags(tick).find((t) => t.id === 'FAC.SEP_P')
  if (sep && typeof sep.value === 'number') {
    out.push({
      key: 'fac-sep-p',
      wellId: 'FACILITY',
      nameFa: sep.nameFa,
      unit: sep.unit,
      min: 100,
      max: 280,
      value: sep.value,
      address: sep.address,
      purpose: sep.purpose,
    })
  }
  return out
}
