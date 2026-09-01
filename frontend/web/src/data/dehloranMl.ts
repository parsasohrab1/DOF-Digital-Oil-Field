/** داده و منطق محلی مدیریت مدل‌های یادگیری ماشین (بدون نیاز به بک‌اند) */

export type MlModelType = 'anomaly_detection' | 'failure_prediction' | 'time_series_forecast'

export const ML_MODEL_TYPES: { id: MlModelType; labelFa: string }[] = [
  { id: 'anomaly_detection', labelFa: 'تشخیص ناهنجاری' },
  { id: 'failure_prediction', labelFa: 'پیش‌بینی خرابی' },
  { id: 'time_series_forecast', labelFa: 'پیش‌بینی سری‌زمانی' },
]

interface LocalModelVersion {
  version: number
  stage: string
  metrics: Record<string, number>
}

const VERSION_HISTORY: Record<MlModelType, LocalModelVersion[]> = {
  anomaly_detection: [
    { version: 1, stage: 'بایگانی‌شده', metrics: { accuracy: 0.881, precision: 0.84, recall: 0.79 } },
    { version: 2, stage: 'آزمایشی', metrics: { accuracy: 0.912, precision: 0.88, recall: 0.85 } },
    { version: 3, stage: 'تولید', metrics: { accuracy: 0.934, precision: 0.91, recall: 0.89 } },
  ],
  failure_prediction: [
    { version: 1, stage: 'بایگانی‌شده', metrics: { accuracy: 0.79, f1: 0.74 } },
    { version: 2, stage: 'تولید', metrics: { accuracy: 0.86, f1: 0.82 } },
  ],
  time_series_forecast: [
    { version: 1, stage: 'تولید', metrics: { mae: 4.2, rmse: 6.1 } },
  ],
}

export function getLocalMlModels() {
  return {
    models: ML_MODEL_TYPES.map((t) => ({
      name: t.id,
      model_type: t.id,
      status: 'active',
    })),
  }
}

export function getLocalMlVersions(modelType: string) {
  return { versions: VERSION_HISTORY[modelType as MlModelType] || [] }
}

export function compareLocalMlVersions(modelType: string, baseline: string, candidate: string) {
  const versions = VERSION_HISTORY[modelType as MlModelType] || []
  const b = versions.find((v) => String(v.version) === String(baseline))
  const c = versions.find((v) => String(v.version) === String(candidate))
  if (!b || !c) {
    throw new Error('نگارش موردنظر در تاریخچهٔ محلی یافت نشد')
  }
  const metric_deltas: Record<string, { baseline: number; candidate: number; delta: number }> = {}
  for (const key of Object.keys(b.metrics)) {
    if (key in c.metrics) {
      metric_deltas[key] = {
        baseline: b.metrics[key],
        candidate: c.metrics[key],
        delta: c.metrics[key] - b.metrics[key],
      }
    }
  }
  return { baseline: { version: b.version }, candidate: { version: c.version }, metric_deltas }
}

interface LocalAbTest {
  baseline_version: string
  candidate_version: string
  candidate_weight: number
}

const localAbTests: Partial<Record<MlModelType, LocalAbTest>> = {}

export function getLocalAbTest(modelType: string) {
  return { ab_test: localAbTests[modelType as MlModelType] || null }
}

export function setLocalAbTest(modelType: string, config: LocalAbTest) {
  localAbTests[modelType as MlModelType] = config
  return { ab_test: config }
}

interface LocalDriftBaseline {
  means: Record<string, number>
  stds: Record<string, number>
  sample_size: number
}

const localDriftBaselines: Partial<Record<MlModelType, LocalDriftBaseline>> = {}

function computeStats(samples: Record<string, number>[]) {
  const keys = Object.keys(samples[0] || {})
  const means: Record<string, number> = {}
  const stds: Record<string, number> = {}
  for (const k of keys) {
    const vals = samples.map((s) => s[k]).filter((v) => typeof v === 'number')
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length
    const variance = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length
    means[k] = mean
    stds[k] = Math.sqrt(variance) || 1
  }
  return { means, stds }
}

export function setLocalDriftBaseline(modelType: string, samples: Record<string, number>[]) {
  const { means, stds } = computeStats(samples)
  const baseline = { means, stds, sample_size: samples.length }
  localDriftBaselines[modelType as MlModelType] = baseline
  return { baseline }
}

export function detectLocalDrift(modelType: string, samples: Record<string, number>[], threshold = 2.0) {
  const baseline = localDriftBaselines[modelType as MlModelType]
  if (!baseline) {
    throw new Error('ابتدا باید خط پایه (Baseline) برای این مدل تنظیم شود')
  }
  const { means: currentMeans } = computeStats(samples)
  const feature_drift: Record<string, { baseline_mean: number; current_mean: number; z_score: number; drift: boolean }> = {}
  let maxZ = 0
  let anyDrift = false
  for (const k of Object.keys(baseline.means)) {
    if (!(k in currentMeans)) continue
    const z = Math.abs((currentMeans[k] - baseline.means[k]) / baseline.stds[k])
    const drift = z > threshold
    if (drift) anyDrift = true
    maxZ = Math.max(maxZ, z)
    feature_drift[k] = { baseline_mean: baseline.means[k], current_mean: currentMeans[k], z_score: z, drift }
  }
  return { drift_detected: anyDrift, aggregate_score: maxZ, threshold, feature_drift }
}
