/** پیش‌بینی عمر مفید باقی‌مانده تجهیزات میدان دهلران */

import { getDehloranLiveState, type WellLiveState } from './dehloranField'

export type RulUrgency = 'critical' | 'high' | 'medium' | 'low'

export interface DehloranRulPrediction {
  equipment_id: string
  equipment_type: string
  equipment_type_fa: string
  well_name?: string
  rul_hours: number
  rul_days: number
  confidence: number
  urgency: RulUrgency
  recommendation: string
  maintenance_window_days: number
}

function urgencyFromDays(days: number): RulUrgency {
  if (days < 14) return 'critical'
  if (days < 45) return 'high'
  if (days < 120) return 'medium'
  return 'low'
}

function recommendationFor(urgency: RulUrgency, typeFa: string): string {
  switch (urgency) {
    case 'critical':
      return `بازرسی فوری ${typeFa} و آماده‌سازی تعویض/اورهال`
    case 'high':
      return `تعمیرات را ظرف ۱ هفته برنامه‌ریزی کنید`
    case 'medium':
      return `تعمیرات را ظرف ۱ ماه در برنامه بگنجانید`
    default:
      return `پایش دوره‌ای کافی است؛ وضعیت پایدار`
  }
}

function espRul(w: WellLiveState): DehloranRulPrediction {
  // ریسک تجهیزات و وضعیت پمپ → عمر مفید باقی‌مانده
  const risk = w.equipmentRisk
  const baseDays = w.pumpOnline ? 320 - risk * 2.8 : 8
  const declinePenalty = w.declinePct30d * 4
  const rul_days = Math.max(3, Math.round(baseDays - declinePenalty))
  const urgency = !w.pumpOnline ? 'critical' : urgencyFromDays(rul_days)
  const confidence = Math.min(0.96, Math.max(0.72, 0.94 - risk * 0.002))

  return {
    equipment_id: `ESP-${w.id}`,
    equipment_type: 'esp',
    equipment_type_fa: 'پمپ درون‌چاهی الکتریکی',
    well_name: w.nameFa,
    rul_hours: rul_days * 24,
    rul_days,
    confidence,
    urgency,
    recommendation: !w.pumpOnline
      ? 'پمپ آفلاین است؛ تشخیص علت توقف و راه‌اندازی مجدد اولویت دارد'
      : recommendationFor(urgency, 'پمپ درون‌چاهی'),
    maintenance_window_days: Math.max(0, rul_days - 7),
  }
}

/** تجهیزات تسهیلات مشترک میدان */
function facilityRul(tick: number): DehloranRulPrediction[] {
  const items: Array<{
    id: string
    type: string
    typeFa: string
    days: number
    conf: number
  }> = [
    { id: 'SEP-DEH-01', type: 'separator', typeFa: 'جداکننده سه‌فازی', days: 210 + (tick % 17), conf: 0.88 },
    { id: 'COMP-DEH-02', type: 'compressor', typeFa: 'کمپرسور گاز', days: 78 + (tick % 9), conf: 0.91 },
    { id: 'MANF-DEH-01', type: 'manifold', typeFa: 'منیفولد تولید', days: 260 + (tick % 11), conf: 0.86 },
    { id: 'PIPE-DEH-MAIN', type: 'pipeline', typeFa: 'خط لوله صادرات', days: 340 + (tick % 13), conf: 0.84 },
    { id: 'GL-DEH-COMP', type: 'gas_lift', typeFa: 'کمپرسور گازرانی', days: 95 + (tick % 7), conf: 0.89 },
    { id: 'GEN-DEH-01', type: 'generator', typeFa: 'ژنراتور برق میدان', days: 155 + (tick % 15), conf: 0.87 },
    { id: 'CHOKE-DEH-HDR', type: 'choke', typeFa: 'شیر کنترل جریان هدر', days: 185 + (tick % 5), conf: 0.9 },
  ]

  return items.map((it) => {
    const urgency = urgencyFromDays(it.days)
    return {
      equipment_id: it.id,
      equipment_type: it.type,
      equipment_type_fa: it.typeFa,
      rul_hours: it.days * 24,
      rul_days: it.days,
      confidence: it.conf,
      urgency,
      recommendation: recommendationFor(urgency, it.typeFa),
      maintenance_window_days: Math.max(0, it.days - 7),
    }
  })
}

/** فهرست کامل پیش‌بینی عمر مفید باقی‌مانده برای میدان دهلران */
export function getDehloranRulPredictions(tick = Date.now()): DehloranRulPrediction[] {
  const wells = getDehloranLiveState(tick)
  const esp = wells.map(espRul)
  const facility = facilityRul(Math.floor(tick / 60000))
  return [...esp, ...facility].sort((a, b) => a.rul_days - b.rul_days)
}

export function getDehloranMaintenanceSchedule(
  predictions: DehloranRulPrediction[]
): Array<{
  equipment_id: string
  equipment_type: string
  equipment_type_fa: string
  maintenance_type: string
  maintenance_type_fa: string
  scheduled_date: string
  estimated_duration: number
  priority: string
  status: string
  status_fa: string
}> {
  const now = Date.now()
  return predictions
    .filter((p) => p.urgency === 'critical' || p.urgency === 'high' || p.urgency === 'medium')
    .slice(0, 10)
    .map((p, i) => {
      const daysAhead = Math.max(2, Math.min(p.maintenance_window_days, 45))
      const date = new Date(now + daysAhead * 86400000)
      return {
        equipment_id: p.equipment_id,
        equipment_type: p.equipment_type,
        equipment_type_fa: p.equipment_type_fa,
        maintenance_type: p.urgency === 'critical' ? 'corrective' : 'preventive',
        maintenance_type_fa: p.urgency === 'critical' ? 'اصلاحی' : 'پیشگیرانه',
        scheduled_date: date.toISOString().slice(0, 10),
        estimated_duration: p.equipment_type === 'esp' ? 8 : 4 + (i % 3) * 2,
        priority: p.urgency,
        status: 'scheduled',
        status_fa: 'زمان‌بندی‌شده',
      }
    })
}
