/**
 * DVR (Data Validation & Reconciliation) datasets for میدان دهلران
 * هدفمند: کیفیت داده سنسورهای سرچاهی/تولید/تجهیزات، outlier، mass-balance
 */
import { DEHLORAN_WELLS, FIELD, getDehloranLiveState, SENSOR_VARIABLES } from './dehloranField'

function seeded(n: number) {
  const x = Math.sin(n * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

export type DvrQualityScore = {
  sensor_id: string
  well_id: string
  variable_fa: string
  category: string
  quality_score: number
  completeness: number
  accuracy: number
  timeliness: number
  consistency: number
  validity: number
  timestamp: string
  issues: string[]
}

export type DvrValidationResult = {
  sensor_id: string
  well_id: string
  timestamp: string
  value: number
  unit: string
  is_valid: boolean
  validation_score: number
  violations: string[]
  quality_metrics: Record<string, number>
  rule_checks: Array<{ rule: string; passed: boolean; detail: string }>
}

export type DvrOutlier = {
  sensor_id: string
  value: number
  expected_range: string
  outlier_score: number
  method: string
  timestamp: string
  severity: 'low' | 'medium' | 'high'
  reason_fa: string
}

export type DvrReconciliationRow = {
  well_id: string
  measured_oil: number
  vfm_oil: number
  reconciled_oil: number
  imbalance_pct: number
  water_cut_measured: number
  water_cut_reconciled: number
  status: 'balanced' | 'minor' | 'material'
}

/** کلید سنسور: DEH-01.thp */
export function dvrSensorId(wellId: string, varKey: string) {
  return `${wellId}.${varKey}`
}

export function parseDvrSensorId(sensorId: string) {
  const [wellId, varKey] = sensorId.split('.')
  return { wellId, varKey }
}

const PRIMARY_VARS = [
  'thp',
  'tht',
  'oil_rate',
  'gas_rate',
  'water_rate',
  'water_cut',
  'esp_current',
  'esp_vibration',
] as const

/** کیفیت داده برای سنسورهای کلیدی همه ۱۶ چاه */
export function buildDehloranDvrQuality(tick = Date.now()): DvrQualityScore[] {
  const now = new Date(tick).toISOString()
  const live = getDehloranLiveState(tick)
  const rows: DvrQualityScore[] = []

  for (let wi = 0; wi < DEHLORAN_WELLS.length; wi++) {
    const well = DEHLORAN_WELLS[wi]
    const lw = live[wi]
    for (let vi = 0; vi < PRIMARY_VARS.length; vi++) {
      const key = PRIMARY_VARS[vi]
      const meta = SENSOR_VARIABLES.find((s) => s.key === key)!
      const r = seeded(wi * 17 + vi * 3 + 1)
      let completeness = 0.92 + r * 0.08
      let accuracy = 0.88 + r * 0.1
      let timeliness = 0.9 + r * 0.09
      let consistency = 0.86 + r * 0.12
      let validity = 0.9 + r * 0.08
      const issues: string[] = []

      if (lw.status === 'offline') {
        completeness = 0.35 + r * 0.1
        timeliness = 0.2 + r * 0.15
        issues.push('قطع ارتباط / داده دیرهنگام')
      } else if (lw.status === 'critical') {
        accuracy -= 0.12
        consistency -= 0.1
        issues.push('نوسان غیرعادی نسبت به baseline میدان')
      }
      if (key === 'water_cut' && lw.waterCut > 55) {
        consistency -= 0.08
        issues.push('درصد آب تولیدی بالا — نیاز به اعتبارسنجی با تست جداکننده')
      }
      if (key === 'esp_vibration' && lw.equipmentRisk > 50) {
        validity -= 0.1
        issues.push('لرزش پمپ خارج از باند عملیاتی')
      }
      if (key === 'oil_rate') {
        const delta = Math.abs(lw.oilRate - lw.vfmOilRate) / Math.max(1, lw.oilRate)
        if (delta > 0.08) {
          consistency -= 0.15
          issues.push(`اختلاف اندازه‌گیری با دبی‌سنج مجازی ${(delta * 100).toFixed(1)}%`)
        }
      }

      completeness = clamp01(completeness)
      accuracy = clamp01(accuracy)
      timeliness = clamp01(timeliness)
      consistency = clamp01(consistency)
      validity = clamp01(validity)
      const quality_score =
        completeness * 0.2 +
        accuracy * 0.25 +
        timeliness * 0.15 +
        consistency * 0.2 +
        validity * 0.2

      rows.push({
        sensor_id: dvrSensorId(well.id, key),
        well_id: well.id,
        variable_fa: meta.nameFa,
        category: meta.category,
        quality_score: round3(quality_score),
        completeness: round3(completeness),
        accuracy: round3(accuracy),
        timeliness: round3(timeliness),
        consistency: round3(consistency),
        validity: round3(validity),
        timestamp: now,
        issues,
      })
    }
  }
  return rows
}

export function buildDehloranValidation(
  sensorId: string,
  tick = Date.now()
): DvrValidationResult {
  const { wellId, varKey } = parseDvrSensorId(sensorId)
  const live = getDehloranLiveState(tick).find((w) => w.id === wellId)
  const meta = SENSOR_VARIABLES.find((s) => s.key === varKey)
  const value = sensorNumeric(varKey, live)
  const unit = meta?.unit || ''
  const violations: string[] = []
  const rule_checks: DvrValidationResult['rule_checks'] = []

  // Range rules for Dehloran heavy oil
  const ranges: Record<string, [number, number]> = {
    thp: [400, 3500],
    tht: [20, 120],
    oil_rate: [0, 2500],
    gas_rate: [0, 5000],
    water_rate: [0, 4000],
    water_cut: [0, 95],
    esp_current: [0, 80],
    esp_vibration: [0, 12],
  }
  const [lo, hi] = ranges[varKey] || [Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY]
  const inRange = value >= lo && value <= hi
  rule_checks.push({
    rule: 'physical_range',
    passed: inRange,
    detail: `بازه مجاز دهلران [${lo}, ${hi}] ${unit}`,
  })
  if (!inRange) violations.push(`مقدار خارج از بازه فیزیکی مجاز میدان دهلران`)

  if (varKey === 'water_cut' && live && live.waterCut > 70) {
    rule_checks.push({
      rule: 'high_water_cut_alert',
      passed: false,
      detail: 'درصد آب تولیدی > 70% — تأیید با تست جداکننده پیشنهادی است',
    })
    violations.push('درصد آب تولیدی بحرانی برای نفت سنگین درجه سنگینی ۲۹٫۸')
  } else {
    rule_checks.push({
      rule: 'high_water_cut_alert',
      passed: true,
      detail: 'درصد آب تولیدی در محدوده قابل‌قبول عملیاتی',
    })
  }

  if (varKey === 'oil_rate' && live) {
    const delta = Math.abs(live.oilRate - live.vfmOilRate) / Math.max(1, live.oilRate)
    const ok = delta <= 0.1
    rule_checks.push({
      rule: 'vfm_consistency',
      passed: ok,
      detail: `اختلاف با دبی‌سنج مجازی ${(delta * 100).toFixed(1)}% (آستانه ۱۰%)`,
    })
    if (!ok) violations.push('ناسازگاری دبی اندازه‌گیری‌شده با دبی‌سنج مجازی')
  }

  if (live?.status === 'offline') {
    rule_checks.push({
      rule: 'freshness',
      passed: false,
      detail: `آخرین داده ${live.lastSeenMin} دقیقه پیش`,
    })
    violations.push('داده غیرفعال / تازگی ناکافی')
  } else {
    rule_checks.push({
      rule: 'freshness',
      passed: true,
      detail: 'داده در پنجره زمانی قابل‌قبول',
    })
  }

  const passed = rule_checks.filter((c) => c.passed).length
  const validation_score = passed / rule_checks.length

  return {
    sensor_id: sensorId,
    well_id: wellId,
    timestamp: new Date(tick).toISOString(),
    value,
    unit,
    is_valid: violations.length === 0,
    validation_score: round3(validation_score),
    violations,
    quality_metrics: {
      range_ok: inRange ? 1 : 0,
      rules_passed: passed,
      rules_total: rule_checks.length,
    },
    rule_checks,
  }
}

export function buildDehloranOutliers(sensorId: string, tick = Date.now()): DvrOutlier[] {
  const { wellId, varKey } = parseDvrSensorId(sensorId)
  const live = getDehloranLiveState(tick).find((w) => w.id === wellId)
  const base = sensorNumeric(varKey, live)
  const out: DvrOutlier[] = []
  const n = 5 + Math.floor(seeded(wellId.length + varKey.length) * 4)

  for (let i = 0; i < n; i++) {
    const r = seeded(i * 9 + wellId.charCodeAt(4) + varKey.length)
    if (r < 0.45 && live?.status !== 'critical' && live?.status !== 'warning') continue
    const spike = base * (1 + (r - 0.5) * 0.55)
    const z = 2.2 + r * 2.8
    const severity: DvrOutlier['severity'] = z > 4 ? 'high' : z > 3 ? 'medium' : 'low'
    out.push({
      sensor_id: sensorId,
      value: Math.round(spike * 10) / 10,
      expected_range: `${(base * 0.85).toFixed(0)}–${(base * 1.15).toFixed(0)}`,
      outlier_score: Math.round(z * 100) / 100,
      method: 'zscore',
      timestamp: new Date(tick - i * 3600_000).toISOString(),
      severity,
      reason_fa:
        severity === 'high'
          ? 'انحراف شدید از میانگین متحرک ۲۴ساعته چاه'
          : 'نقطه پرت نسبت به الگوی تولید دهلران',
    })
  }
  return out.sort((a, b) => b.outlier_score - a.outlier_score)
}

/** موازنه جرمی نفت: اندازه‌گیری vs VFM در سطح چاه و میدان */
export function buildDehloranReconciliation(tick = Date.now()): {
  field: {
    name: string
    client: string
    measured_oil_total: number
    vfm_oil_total: number
    reconciled_oil_total: number
    field_imbalance_pct: number
    material_wells: number
  }
  wells: DvrReconciliationRow[]
} {
  const live = getDehloranLiveState(tick)
  const wells: DvrReconciliationRow[] = live.map((w) => {
    const measured = w.oilRate
    const vfm = w.vfmOilRate
    const reconciled = Math.round((measured * 0.45 + vfm * 0.55) )
    const imbalance_pct =
      Math.round((Math.abs(measured - vfm) / Math.max(1, (measured + vfm) / 2)) * 1000) / 10
    let status: DvrReconciliationRow['status'] = 'balanced'
    if (imbalance_pct > 8) status = 'material'
    else if (imbalance_pct > 3) status = 'minor'
    return {
      well_id: w.id,
      measured_oil: measured,
      vfm_oil: vfm,
      reconciled_oil: reconciled,
      imbalance_pct,
      water_cut_measured: w.waterCut,
      water_cut_reconciled: Math.round((w.waterCut * 0.9 + 2) * 10) / 10,
      status,
    }
  })

  const measured_oil_total = wells.reduce((s, w) => s + w.measured_oil, 0)
  const vfm_oil_total = wells.reduce((s, w) => s + w.vfm_oil, 0)
  const reconciled_oil_total = wells.reduce((s, w) => s + w.reconciled_oil, 0)
  const field_imbalance_pct =
    Math.round(
      (Math.abs(measured_oil_total - vfm_oil_total) /
        Math.max(1, (measured_oil_total + vfm_oil_total) / 2)) *
        1000
    ) / 10

  return {
    field: {
      name: FIELD.nameFa,
      client: FIELD.clientFa,
      measured_oil_total,
      vfm_oil_total,
      reconciled_oil_total,
      field_imbalance_pct,
      material_wells: wells.filter((w) => w.status === 'material').length,
    },
    wells,
  }
}

export function dvrFieldSummary(scores: DvrQualityScore[]) {
  if (!scores.length) {
    return { avgQuality: 0, below70: 0, below90: 0, sensors: 0, wells: 0 }
  }
  const avg = scores.reduce((s, x) => s + x.quality_score, 0) / scores.length
  return {
    avgQuality: Math.round(avg * 1000) / 10,
    below70: scores.filter((s) => s.quality_score < 0.7).length,
    below90: scores.filter((s) => s.quality_score < 0.9).length,
    sensors: scores.length,
    wells: new Set(scores.map((s) => s.well_id)).size,
  }
}

function sensorNumeric(varKey: string, live?: ReturnType<typeof getDehloranLiveState>[0]): number {
  if (!live) return 0
  const map: Record<string, number> = {
    thp: live.thp,
    tht: live.tht,
    oil_rate: live.oilRate,
    gas_rate: live.gasRate,
    water_rate: live.waterRate,
    water_cut: live.waterCut,
    esp_current: live.pumpOnline ? 28 + live.equipmentRisk * 0.15 : 0,
    esp_vibration: live.pumpOnline ? 1.2 + live.equipmentRisk * 0.04 : 0,
  }
  return map[varKey] ?? 0
}

function clamp01(v: number) {
  return Math.max(0.05, Math.min(0.995, v))
}

function round3(v: number) {
  return Math.round(v * 1000) / 1000
}
