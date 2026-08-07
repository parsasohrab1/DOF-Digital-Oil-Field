/** هشدارهای زنده میدان دهلران برای تب هشدارها و ارسال پیامک */

import { FIELD, getDehloranLiveState, type WellLiveState } from './dehloranField'

export type AlertSeverity = 'critical' | 'warning' | 'info'
export type AlertStatus = 'open' | 'acknowledged' | 'resolved'

export interface DehloranAlert {
  alert_id: string
  well_name: string
  severity: AlertSeverity
  message: string
  status: AlertStatus
  timestamp: string
  metadata_json: Record<string, unknown>
  erp_work_order_id?: string
}

const SMS_OUTBOX_KEY = 'sogf_sms_outbox'
const SMS_RECIPIENTS_KEY = 'sogf_sms_recipients'

function minutesAgoIso(min: number) {
  return new Date(Date.now() - min * 60_000).toISOString()
}

function wellAlerts(w: WellLiveState): DehloranAlert[] {
  const list: DehloranAlert[] = []
  const base = {
    well_name: w.id,
    status: 'open' as AlertStatus,
  }

  if (w.status === 'offline') {
    list.push({
      ...base,
      alert_id: `ALT-${w.id}-OFF`,
      severity: 'critical',
      message: `قطع ارتباط چاه ${w.nameFa} — آخرین مشاهده ${w.lastSeenMin} دقیقه پیش`,
      timestamp: minutesAgoIso(w.lastSeenMin),
      metadata_json: { sensor: 'comm', category: 'connectivity', sms_priority: 1 },
    })
  }

  if (!w.pumpOnline && w.status !== 'offline') {
    list.push({
      ...base,
      alert_id: `ALT-${w.id}-ESP`,
      severity: 'critical',
      message: `توقف پمپ درون‌چاهی الکتریکی در ${w.nameFa} — ریسک تجهیزات ${w.equipmentRisk}٪`,
      timestamp: minutesAgoIso(8 + (w.equipmentRisk % 20)),
      metadata_json: { sensor: 'esp', category: 'equipment', sms_priority: 1 },
    })
  }

  if (w.waterCut >= 55) {
    list.push({
      ...base,
      alert_id: `ALT-${w.id}-WC`,
      severity: w.waterCut >= 70 ? 'critical' : 'warning',
      message: `افزایش درصد آب تولیدی در ${w.nameFa}: ${w.waterCut}٪ (آستانه ۵۵٪)`,
      timestamp: minutesAgoIso(15 + Math.round(w.waterCut / 5)),
      metadata_json: { sensor: 'water_cut', category: 'production', value: w.waterCut },
    })
  }

  if (w.equipmentRisk >= 45 && w.pumpOnline) {
    list.push({
      ...base,
      alert_id: `ALT-${w.id}-EQ`,
      severity: w.equipmentRisk >= 65 ? 'critical' : 'warning',
      message: `ریسک خرابی تجهیزات در ${w.nameFa}: ${w.equipmentRisk}٪ — لرزش/جریان پمپ خارج از محدوده`,
      timestamp: minutesAgoIso(22),
      metadata_json: { sensor: 'esp_vibration', category: 'equipment', value: w.equipmentRisk },
    })
  }

  if (w.declinePct30d >= 7) {
    list.push({
      ...base,
      alert_id: `ALT-${w.id}-DEC`,
      severity: 'warning',
      message: `افت تولید ۳۰روزه ${w.nameFa}: ${w.declinePct30d}٪ — بررسی شیر کنترل جریان و فشار سرچاهی`,
      timestamp: minutesAgoIso(40),
      metadata_json: { sensor: 'oil_rate', category: 'production', value: w.declinePct30d },
    })
  }

  if (w.thp > 1600) {
    list.push({
      ...base,
      alert_id: `ALT-${w.id}-THP`,
      severity: 'warning',
      message: `فشار سرچاهی بالا در ${w.nameFa}: ${w.thp} psi`,
      timestamp: minutesAgoIso(12),
      metadata_json: { sensor: 'thp', category: 'wellhead', value: w.thp },
    })
  }

  if (w.healthScore < 55 && w.status !== 'offline') {
    list.push({
      ...base,
      alert_id: `ALT-${w.id}-HLTH`,
      severity: w.healthScore < 40 ? 'critical' : 'warning',
      message: `کاهش امتیاز سلامت ${w.nameFa} به ${w.healthScore}`,
      timestamp: minutesAgoIso(18),
      metadata_json: { sensor: 'health', category: 'integrity', value: w.healthScore },
    })
  }

  return list
}

function facilityAlerts(): DehloranAlert[] {
  return [
    {
      alert_id: 'ALT-SEP-DEH-01-LEVEL',
      well_name: 'تسهیلات / جداکننده',
      severity: 'warning',
      message: 'سطح مایع جداکننده سه‌فازی نزدیک حد بالا — کنترل شیر خروجی',
      status: 'open',
      timestamp: minutesAgoIso(25),
      metadata_json: { sensor: 'separator_l', category: 'facility' },
    },
    {
      alert_id: 'ALT-COMP-DEH-02-VIB',
      well_name: 'تسهیلات / کمپرسور',
      severity: 'critical',
      message: 'لرزش غیرعادی کمپرسور گاز — احتمال خرابی یاتاقان',
      status: 'open',
      timestamp: minutesAgoIso(9),
      metadata_json: { sensor: 'comp_vibration', category: 'facility', sms_priority: 1 },
    },
    {
      alert_id: 'ALT-PIPE-DEH-MAIN-P',
      well_name: 'تسهیلات / خط لوله',
      severity: 'warning',
      message: 'افت فشار خط لوله صادرات نسبت به ست‌پوینت — بررسی نشتی/شیر',
      status: 'open',
      timestamp: minutesAgoIso(33),
      metadata_json: { sensor: 'pipeline_p', category: 'facility' },
    },
    {
      alert_id: 'ALT-GL-DEH-COMP',
      well_name: 'تسهیلات / گازرانی',
      severity: 'info',
      message: 'کاهش ظرفیت کمپرسور گازرانی — برنامه‌ریزی سرویس پیشگیرانه',
      status: 'acknowledged',
      timestamp: minutesAgoIso(120),
      metadata_json: { sensor: 'gas_lift', category: 'facility' },
    },
  ]
}

/** فهرست هشدارهای میدان برای نمایش و ارسال پیامک */
export function getDehloranAlerts(tick = Date.now()): DehloranAlert[] {
  const wells = getDehloranLiveState(tick)
  const fromWells = wells.flatMap(wellAlerts)
  const all = [...fromWells, ...facilityAlerts()]
  const rank = { critical: 0, warning: 1, info: 2 }
  return all.sort((a, b) => {
    const d = rank[a.severity] - rank[b.severity]
    if (d !== 0) return d
    return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  })
}

export function buildAlertSmsText(alert: {
  alert_id: string
  well_name: string
  severity: string
  message: string
}) {
  const sev =
    alert.severity === 'critical' ? 'بحرانی' : alert.severity === 'warning' ? 'هشدار' : 'اطلاع'
  return (
    `هوشمندسازی میادین — هشدار ${sev}\n` +
    `چاه/محل: ${alert.well_name}\n` +
    `${alert.message}\n` +
    `کد: ${alert.alert_id}\n` +
    `${FIELD.nameFa}`
  )
}

export type LocalSmsEntry = {
  id: string
  phone: string
  phone_display: string
  message: string
  effective_provider: string
  result: { status: string }
  at: string
  meta?: Record<string, unknown>
}

export type LocalSmsRecipient = {
  phone: string
  phone_display: string
  label: string
  enabled: boolean
  severities: string[]
}

function displayPhone(phone: string) {
  const p = phone.replace(/\s/g, '')
  if (p.length < 4) return p
  return `${p.slice(0, 4)}***${p.slice(-2)}`
}

export function loadLocalSmsRecipients(): LocalSmsRecipient[] {
  try {
    return JSON.parse(localStorage.getItem(SMS_RECIPIENTS_KEY) || '[]')
  } catch {
    return []
  }
}

export function saveLocalSmsRecipient(phone: string, label: string): LocalSmsRecipient {
  const entry: LocalSmsRecipient = {
    phone,
    phone_display: displayPhone(phone),
    label: label || 'اپراتور',
    enabled: true,
    severities: ['critical', 'warning'],
  }
  const list = loadLocalSmsRecipients().filter((r) => r.phone !== phone)
  list.unshift(entry)
  localStorage.setItem(SMS_RECIPIENTS_KEY, JSON.stringify(list.slice(0, 10)))
  return entry
}

export function loadLocalSmsOutbox(): LocalSmsEntry[] {
  try {
    return JSON.parse(localStorage.getItem(SMS_OUTBOX_KEY) || '[]')
  } catch {
    return []
  }
}

export function pushLocalSms(phone: string, message: string, meta?: Record<string, unknown>): LocalSmsEntry {
  const entry: LocalSmsEntry = {
    id: `sms-local-${Date.now()}`,
    phone,
    phone_display: displayPhone(phone),
    message,
    effective_provider: 'local-mock',
    result: { status: 'queued' },
    at: new Date().toISOString(),
    meta,
  }
  const box = loadLocalSmsOutbox()
  box.unshift(entry)
  localStorage.setItem(SMS_OUTBOX_KEY, JSON.stringify(box.slice(0, 40)))
  return entry
}

export function getLocalSmsStatus(phoneFallback?: string) {
  const recipients = loadLocalSmsRecipients()
  if (recipients.length === 0 && phoneFallback) {
    return {
      provider: 'local-mock',
      detail: 'حالت محلی — شماره هنوز ثبت نشده؛ پس از ثبت، پیامک در صف مرورگر ذخیره می‌شود',
      recipients: [],
    }
  }
  return {
    provider: 'local-mock',
    detail: 'حالت محلی (بدون درگاه) — پیامک‌ها در صف مرورگر ذخیره می‌شوند',
    recipients,
  }
}
