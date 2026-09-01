import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { mlAPI } from '../api/services'
import {
  ML_MODEL_TYPES,
  getLocalMlModels,
  getLocalMlVersions,
  compareLocalMlVersions,
  getLocalAbTest,
  setLocalAbTest,
  setLocalDriftBaseline,
  detectLocalDrift,
} from '../data/dehloranMl'
import './MLModels.css'

function pct(value: number | undefined): string {
  if (value === undefined || value === null) return '—'
  return `${(value * 100).toFixed(1)}%`
}

export default function MLModels() {
  const queryClient = useQueryClient()
  const [selectedType, setSelectedType] = useState('anomaly_detection')
  const [baselineVersion, setBaselineVersion] = useState('')
  const [candidateVersion, setCandidateVersion] = useState('')
  const [candidateWeight, setCandidateWeight] = useState(0.2)
  const [compareResult, setCompareResult] = useState<any>(null)
  const [compareError, setCompareError] = useState<string | null>(null)
  const [driftFeatures, setDriftFeatures] = useState(
    '[{"pressure": 318, "temperature": 84, "flow_rate": 448}, {"pressure": 322, "temperature": 86, "flow_rate": 452}]'
  )
  const [driftResult, setDriftResult] = useState<any>(null)
  const [driftError, setDriftError] = useState<string | null>(null)

  const modelsQuery = useQuery({
    queryKey: ['ml-models'],
    queryFn: async () => {
      try {
        return await mlAPI.getModels()
      } catch {
        return getLocalMlModels()
      }
    },
  })

  const versionsQuery = useQuery({
    queryKey: ['ml-versions', selectedType],
    queryFn: async () => {
      try {
        return await mlAPI.getModelVersions(selectedType)
      } catch {
        return getLocalMlVersions(selectedType)
      }
    },
    enabled: !!selectedType,
  })

  const abTestQuery = useQuery({
    queryKey: ['ml-ab-test', selectedType],
    queryFn: async () => {
      try {
        return await mlAPI.getABTestConfig(selectedType)
      } catch {
        return getLocalAbTest(selectedType)
      }
    },
    enabled: !!selectedType,
  })

  const compareMutation = useMutation({
    mutationFn: async () => {
      try {
        return await mlAPI.compareModelVersions(selectedType, baselineVersion, candidateVersion)
      } catch {
        return compareLocalMlVersions(selectedType, baselineVersion, candidateVersion)
      }
    },
    onSuccess: (data) => { setCompareResult(data); setCompareError(null) },
    onError: (err: any) => setCompareError(err?.message || 'مقایسه ناموفق بود'),
  })

  const abTestMutation = useMutation({
    mutationFn: async () => {
      const config = {
        baseline_version: baselineVersion,
        candidate_version: candidateVersion,
        candidate_weight: candidateWeight,
      }
      try {
        return await mlAPI.configureABTest(selectedType, config)
      } catch {
        return setLocalAbTest(selectedType, config)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ml-ab-test', selectedType] })
    },
  })

  const driftBaselineMutation = useMutation({
    mutationFn: async (features: Record<string, number>[]) => {
      try {
        return await mlAPI.setDriftBaseline(selectedType, features)
      } catch {
        return setLocalDriftBaseline(selectedType, features)
      }
    },
    onError: (err: any) => setDriftError(err?.response?.data?.detail || err?.message || 'تنظیم خط پایه ناموفق بود'),
  })

  const driftDetectMutation = useMutation({
    mutationFn: async (features: Record<string, number>[]) => {
      try {
        return await mlAPI.detectDrift(selectedType, features)
      } catch {
        return detectLocalDrift(selectedType, features)
      }
    },
    onSuccess: (data) => { setDriftResult(data); setDriftError(null) },
    onError: (err: any) => setDriftError(err?.response?.data?.detail || err?.message || 'تشخیص انحراف ناموفق بود'),
  })

  const versions = versionsQuery.data?.versions || []
  const abTest = abTestQuery.data?.ab_test

  // بک‌اند به دسته‌ای از نمونه‌ها (List[Dict[str, float]]) برای محاسبهٔ خط پایهٔ
  // میانگین/انحراف‌معیار نیاز دارد -- یک قرائت تکی هم پذیرفته و به یک دستهٔ
  // تک‌نمونه‌ای تبدیل می‌شود.
  function parseFeatureSamples(text: string): Record<string, number>[] {
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) return parsed
    return [parsed]
  }

  const handleDriftBaseline = () => {
    try {
      setDriftError(null)
      driftBaselineMutation.mutate(parseFeatureSamples(driftFeatures))
    } catch {
      setDriftError('JSON نامعتبر است: یک آبجکت {"پارامتر": مقدار} یا آرایه‌ای از آن‌ها وارد کنید')
    }
  }

  const handleDriftDetect = () => {
    try {
      setDriftError(null)
      driftDetectMutation.mutate(parseFeatureSamples(driftFeatures))
    } catch {
      setDriftError('JSON نامعتبر است: یک آبجکت {"پارامتر": مقدار} یا آرایه‌ای از آن‌ها وارد کنید')
    }
  }

  const typeLabel = (id: string) => ML_MODEL_TYPES.find((t) => t.id === id)?.labelFa || id

  return (
    <div className="ml-models-page" dir="rtl">
      <div className="ml-models-header">
        <h2>مدیریت مدل‌های یادگیری ماشین</h2>
        <select value={selectedType} onChange={(e) => setSelectedType(e.target.value)}>
          {ML_MODEL_TYPES.map((t) => (
            <option key={t.id} value={t.id}>{t.labelFa}</option>
          ))}
        </select>
      </div>

      <div className="ml-models-grid">
        <section className="ml-card">
          <h3>مدل‌های ثبت‌شده</h3>
          {modelsQuery.isLoading ? <p>در حال بارگذاری...</p> : (
            <ul className="model-list">
              {(modelsQuery.data?.models || []).map((m: any) => (
                <li key={m.name || m.model_type}>
                  <strong>{typeLabel(m.name || m.model_type)}</strong>
                  <span>{m.status || m.stage || 'فعال'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="ml-card">
          <h3>تاریخچهٔ نگارش‌ها</h3>
          {versionsQuery.isLoading ? <p>در حال بارگذاری نگارش‌ها...</p> : versions.length === 0 ? (
            <p className="muted">نگارشی در ریجیستری یافت نشد.</p>
          ) : (
            <table className="versions-table">
              <thead>
                <tr>
                  <th>نگارش</th>
                  <th>مرحله</th>
                  <th>شاخص‌ها</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((v: any) => (
                  <tr key={v.version}>
                    <td>v{v.version}</td>
                    <td>{v.stage || v.current_stage || '—'}</td>
                    <td>
                      {v.metrics ? Object.entries(v.metrics).slice(0, 3).map(([k, val]) => (
                        <span key={k} className="metric-tag">{k}: {typeof val === 'number' ? val.toFixed(3) : String(val)}</span>
                      )) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="ml-card">
          <h3>مقایسهٔ نگارش‌ها</h3>
          <div className="form-row">
            <input placeholder="نگارش پایه" value={baselineVersion} onChange={(e) => setBaselineVersion(e.target.value)} />
            <input placeholder="نگارش کاندید" value={candidateVersion} onChange={(e) => setCandidateVersion(e.target.value)} />
            <button onClick={() => compareMutation.mutate()} disabled={!baselineVersion || !candidateVersion || compareMutation.isPending}>
              {compareMutation.isPending ? 'در حال مقایسه...' : 'مقایسه'}
            </button>
          </div>
          {compareError && <p className="error">{compareError}</p>}
          {compareResult && (
            <div className="compare-result">
              <div>پایه: v{compareResult.baseline?.version ?? baselineVersion}</div>
              <div>کاندید: v{compareResult.candidate?.version ?? candidateVersion}</div>
              {compareResult.metric_deltas && Object.keys(compareResult.metric_deltas).length > 0 ? (
                <ul>
                  {Object.entries(compareResult.metric_deltas).map(([k, v]: [string, any]) => (
                    <li key={k}>
                      {k}: {Number(v.baseline).toFixed(4)} &larr; {Number(v.candidate).toFixed(4)}{' '}
                      <span className={v.delta >= 0 ? 'delta-up' : 'delta-down'}>
                        ({v.delta >= 0 ? '+' : ''}{Number(v.delta).toFixed(4)})
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">شاخص مشترکی بین این دو نگارش یافت نشد.</p>
              )}
            </div>
          )}
        </section>

        <section className="ml-card">
          <h3>پیکربندی A/B Test</h3>
          {abTest ? (
            <div className="ab-active">
              <div>پایه: v{abTest.baseline_version}</div>
              <div>کاندید: v{abTest.candidate_version} ({pct(abTest.candidate_weight)} ترافیک)</div>
            </div>
          ) : (
            <p className="muted">هیچ A/B Test فعالی وجود ندارد.</p>
          )}
          <div className="form-row">
            <label>
              سهم کاندید
              <input type="range" min={0.05} max={0.5} step={0.05} value={candidateWeight}
                onChange={(e) => setCandidateWeight(parseFloat(e.target.value))} />
              {pct(candidateWeight)}
            </label>
            <button onClick={() => abTestMutation.mutate()} disabled={!baselineVersion || !candidateVersion || abTestMutation.isPending}>
              {abTestMutation.isPending ? 'در حال ذخیره...' : 'شروع A/B Test'}
            </button>
          </div>
        </section>

        <section className="ml-card full-width">
          <h3>تشخیص انحراف داده (Drift Detection)</h3>
          <p className="muted">
            ابتدا با نمونه‌های تاریخی (آرایه‌ای از قرائت‌ها، یا یک نمونهٔ تکی) «تنظیم خط پایه» را بزنید،
            سپس با قرائت‌های اخیر «تشخیص انحراف» را برای مقایسه با آن اجرا کنید.
          </p>
          <textarea rows={3} value={driftFeatures} onChange={(e) => setDriftFeatures(e.target.value)}
            placeholder='[{"pressure": 320, "temperature": 85}, ...]' />
          <div className="form-row">
            <button onClick={handleDriftBaseline} disabled={driftBaselineMutation.isPending}>
              تنظیم خط پایه
            </button>
            <button onClick={handleDriftDetect} disabled={driftDetectMutation.isPending}>
              تشخیص انحراف
            </button>
          </div>
          {driftError && <p className="error">{driftError}</p>}
          {driftBaselineMutation.isSuccess && (
            <p className="success">
              خط پایه از {driftBaselineMutation.data?.baseline?.sample_size ?? 0} نمونه ذخیره شد.
            </p>
          )}
          {driftResult && (
            <div className={`drift-result ${driftResult.drift_detected ? 'drift-alert' : ''}`}>
              <strong>{driftResult.drift_detected ? 'انحراف داده تشخیص داده شد' : 'انحرافی یافت نشد'}</strong>
              {' '}(امتیاز z تجمیعی: {Number(driftResult.aggregate_score).toFixed(2)}, آستانه: {driftResult.threshold})
              {driftResult.feature_drift && (
                <ul>
                  {Object.entries(driftResult.feature_drift).map(([k, v]: [string, any]) => (
                    <li key={k} className={v.drift ? 'drift-alert' : ''}>
                      {k}: پایه={Number(v.baseline_mean).toFixed(2)}, فعلی={Number(v.current_mean).toFixed(2)}, z={Number(v.z_score).toFixed(2)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
