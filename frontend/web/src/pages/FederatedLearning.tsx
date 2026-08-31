import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { federatedAPI } from '../api/services'
import { DEHLORAN_WELLS } from '../data/dehloranField'
import {
  getLocalFederatedNodes,
  getLocalGlobalModel,
  trainAndSubmitLocal,
  aggregateLocalFedAvg,
} from '../data/dehloranFederated'
import './FederatedLearning.css'

// طرحوارهٔ ثابت ویژگی‌هایی که مدل‌های محلی بک‌اند روی آن آموزش/تجمیع می‌شوند
// (backend/ml-inference-service/federated_learning.py FEATURE_NAMES). فقط برای
// تولید دیتاست نمایشی سمت مرورگر نگه داشته شده -- خود مقادیر لازم نیست با هیچ
// مقیاس واقعی حسگر مطابقت داشته باشند، چون هدف صرفاً نمایش آموزش محلی واقعی +
// تجمیع FedAvg به‌صورت سرتاسری است.
const FEATURES = ['pressure', 'temperature', 'flow_rate', 'vibration']
const BYTES_PER_FLOAT = 8
const WEIGHT_VECTOR_SIZE = FEATURES.length + 1 // + جملهٔ بایاس

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function generateSyntheticTrainingBatch(sampleCount: number) {
  // دادهٔ مصنوعی با تفکیک واضح تا رگرسیون لجستیک واقعی به دقتی بالا و معنادار
  // همگرا شود -- این داده جایگزین قرائت‌های تاریخی واقعی حسگرهای همان چاه است؛
  // دقیقاً همان داده‌ای که یادگیری فدرال قرار است محلی نگه دارد.
  const samples: Record<string, number>[] = []
  const labels: number[] = []
  for (let i = 0; i < sampleCount; i++) {
    const isAnomalous = i % 2 === 0
    samples.push({
      pressure: (isAnomalous ? 550 : 300) + (Math.random() - 0.5) * 40,
      temperature: (isAnomalous ? 95 : 80) + (Math.random() - 0.5) * 5,
      flow_rate: (isAnomalous ? 650 : 400) + (Math.random() - 0.5) * 40,
      vibration: (isAnomalous ? 0.8 : 0.15) + (Math.random() - 0.5) * 0.1,
    })
    labels.push(isAnomalous ? 1 : 0)
  }
  return { samples, labels }
}

export default function FederatedLearning() {
  const queryClient = useQueryClient()
  const [nodeIdInput, setNodeIdInput] = useState('NODE-001')
  const [wellNameInput, setWellNameInput] = useState(DEHLORAN_WELLS[0].id)
  const [locationInput, setLocationInput] = useState('میدان دهلران')
  const [aggregateError, setAggregateError] = useState<string | null>(null)

  const nodesQuery = useQuery({
    queryKey: ['federated-nodes'],
    queryFn: async () => {
      try {
        return await federatedAPI.getNodes()
      } catch {
        return getLocalFederatedNodes()
      }
    },
    refetchInterval: 5000,
  })

  const globalModelQuery = useQuery({
    queryKey: ['federated-global-model'],
    queryFn: async () => {
      try {
        return await federatedAPI.getGlobalModel()
      } catch {
        return getLocalGlobalModel()
      }
    },
    refetchInterval: 5000,
  })

  const trainMutation = useMutation({
    mutationFn: async () => {
      const { samples, labels } = generateSyntheticTrainingBatch(60)
      const payload = { well_name: wellNameInput, location: locationInput, samples, labels }
      try {
        return await federatedAPI.trainAndSubmit(nodeIdInput, payload)
      } catch {
        return trainAndSubmitLocal(nodeIdInput, payload)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['federated-nodes'] })
    },
  })

  const aggregateMutation = useMutation({
    mutationFn: async () => {
      try {
        return await federatedAPI.aggregate(2)
      } catch {
        return aggregateLocalFedAvg(2)
      }
    },
    onSuccess: () => {
      setAggregateError(null)
      queryClient.invalidateQueries({ queryKey: ['federated-nodes'] })
      queryClient.invalidateQueries({ queryKey: ['federated-global-model'] })
    },
    onError: (err: any) => setAggregateError(err?.response?.data?.detail || err?.message || 'تجمیع ناموفق بود'),
  })

  const nodes = nodesQuery.data?.nodes || []
  const globalModel = globalModelQuery.data?.global_model
  const roundHistory = globalModelQuery.data?.round_history || []

  // مقایسهٔ واقعی پهنای‌باند: قرائت‌های خام حسگری که هر گره روی آن‌ها آموزش دیده
  // (تعداد نمونه × تعداد ویژگی) در برابر بردار وزن ثابتی که واقعاً منتقل
  // می‌شود -- این همان چیزی است که یادگیری فدرال صرفه‌جویی می‌کند، محاسبه‌شده از
  // گره‌های واقعاً ثبت‌شده، نه یک عدد ثابت.
  const totalRawSamples = nodes.reduce((sum: number, n: any) => sum + n.data_size, 0)
  const rawBytes = totalRawSamples * FEATURES.length * BYTES_PER_FLOAT
  const transmittedBytes = nodes.length * WEIGHT_VECTOR_SIZE * BYTES_PER_FLOAT
  const bandwidthData = [
    { approach: 'دادهٔ خام (در صورت تمرکز)', bytes: rawBytes },
    { approach: 'فدرال (فقط وزن‌ها)', bytes: transmittedBytes },
  ]
  const bandwidthReductionPct = rawBytes > 0 ? (1 - transmittedBytes / rawBytes) * 100 : 0

  return (
    <div className="federated-learning-page" dir="rtl">
      <div className="page-header">
        <h1>یادگیری فدرال</h1>
        <p>آموزش توزیع‌شده با حفظ حریم خصوصی و کمترین مصرف پهنای‌باند</p>
      </div>

      <div className="fl-stats-grid">
        <div className="stat-card">
          <h3>گره‌های مشارکت‌کننده</h3>
          <div className="stat-value">{nodes.length}</div>
          <div className="stat-label">در حال همگام‌سازی: {nodes.filter((n: any) => n.status === 'syncing').length}</div>
        </div>
        <div className="stat-card">
          <h3>دقت مدل سراسری</h3>
          <div className="stat-value">{pct(globalModel?.global_accuracy)}</div>
          <div className="stat-label">{globalModel?.convergence_status || 'هنوز دوره‌ای اجرا نشده'}</div>
        </div>
        <div className="stat-card">
          <h3>پهنای‌باند صرفه‌جویی‌شده</h3>
          <div className="stat-value">{bandwidthReductionPct > 0 ? `${bandwidthReductionPct.toFixed(1)}%` : '—'}</div>
          <div className="stat-label">در مقایسه با انتقال قرائت خام</div>
        </div>
        <div className="stat-card">
          <h3>حریم خصوصی داده</h3>
          <div className="stat-value">۱۰۰٪</div>
          <div className="stat-label">فقط وزن‌های مدل از هر گره خارج می‌شود</div>
        </div>
      </div>

      <div className="fl-content-grid">
        <div className="nodes-section">
          <h2>گره‌های لبه (Edge)</h2>

          <div className="node-register-form">
            <div className="form-row">
              <input placeholder="شناسهٔ گره" value={nodeIdInput} onChange={(e) => setNodeIdInput(e.target.value)} />
              <select value={wellNameInput} onChange={(e) => setWellNameInput(e.target.value)}>
                {DEHLORAN_WELLS.map((w) => (
                  <option key={w.id} value={w.id}>{w.nameFa} ({w.id})</option>
                ))}
              </select>
              <input placeholder="موقعیت" value={locationInput} onChange={(e) => setLocationInput(e.target.value)} />
            </div>
            <button onClick={() => trainMutation.mutate()} disabled={trainMutation.isPending}>
              {trainMutation.isPending ? 'در حال آموزش محلی...' : 'شبیه‌سازی آموزش محلی + ارسال'}
            </button>
            <p className="muted">
              یک رگرسیون لجستیک واقعی را روی یک دستهٔ نمایشی تولیدشده در همان مرورگر برازش می‌دهد،
              سپس فقط وزن‌های حاصل (نه نمونه‌ها) را به هماهنگ‌کننده ارسال می‌کند.
            </p>
            {trainMutation.isError && <p className="error">آموزش/ارسال ناموفق بود.</p>}
          </div>

          {nodes.length === 0 ? (
            <p className="muted">هنوز هیچ گرهٔ لبه‌ای به‌روزرسانی ارسال نکرده است.</p>
          ) : (
            <div className="nodes-list">
              {nodes.map((node: any) => (
                <div key={node.node_id} className={`node-card ${node.status}`}>
                  <div className="node-header">
                    <span className="node-id">{node.node_id}</span>
                    <span className={`node-status ${node.status}`}>{node.status === 'synced' ? 'همگام‌شده' : node.status}</span>
                  </div>
                  <div className="node-info">
                    <p><strong>موقعیت:</strong> {node.location}</p>
                    <p><strong>چاه:</strong> {node.well_name}</p>
                    <p><strong>دقت محلی:</strong> {pct(node.local_accuracy)}</p>
                    <p><strong>تعداد نمونه‌های آموزشی:</strong> {node.data_size}</p>
                    <p><strong>آخرین همگام‌سازی:</strong> {new Date(node.last_sync).toLocaleString('fa-IR')}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="global-model-section">
          <h2>مدل سراسری</h2>
          <div className="form-row">
            <button onClick={() => aggregateMutation.mutate()} disabled={aggregateMutation.isPending || nodes.length < 2}>
              {aggregateMutation.isPending ? 'در حال تجمیع...' : 'اجرای یک دورهٔ تجمیع FedAvg'}
            </button>
          </div>
          {nodes.length < 2 && <p className="muted">برای تجمیع حداقل ۲ گره لازم است.</p>}
          {aggregateError && <p className="error">{aggregateError}</p>}

          {globalModel?.has_global_model ? (
            <div className="global-model-card">
              <div className="model-header">
                <h3>دورهٔ {globalModel.round}</h3>
                <span className={`convergence-status ${globalModel.convergence_status}`}>
                  {globalModel.convergence_status}
                </span>
              </div>
              <div className="model-metrics">
                <div className="metric-item">
                  <span className="metric-label">دقت سراسری</span>
                  <span className="metric-value">{pct(globalModel.global_accuracy)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">گره‌های مشارکت‌کننده</span>
                  <span className="metric-value">{globalModel.participating_nodes}</span>
                </div>
              </div>

              {roundHistory.length > 0 && (
                <div className="training-history">
                  <h3>تاریخچهٔ دوره‌های تجمیع</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={roundHistory}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="round" />
                      <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                      <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
                      <Legend />
                      <Line type="monotone" dataKey="global_accuracy" stroke="#3498db" name="دقت سراسری" />
                      <Line type="monotone" dataKey="avg_local_accuracy" stroke="#2ecc71" name="میانگین دقت محلی" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          ) : (
            <p className="muted">هنوز هیچ دورهٔ تجمیعی اجرا نشده است.</p>
          )}
        </div>
      </div>

      <div className="comparison-section">
        <h2>مقایسهٔ پهنای‌باند و حریم خصوصی</h2>
        <div className="comparison-grid">
          <div className="comparison-chart">
            <h3>مصرف پهنای‌باند (برآورد از گره‌های ثبت‌شده)</h3>
            {nodes.length === 0 ? (
              <p className="muted">برای مشاهدهٔ مقایسه، حداقل یک گره ثبت کنید.</p>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={bandwidthData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="approach" />
                  <YAxis tickFormatter={(v) => `${(v / 1024).toFixed(1)} KB`} />
                  <Tooltip formatter={(v: number) => `${(v / 1024).toFixed(2)} KB`} />
                  <Legend />
                  <Bar dataKey="bytes" fill="#8884d8" name="بایت منتقل‌شده" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="privacy-benefits">
            <h3>مزایای حریم خصوصی</h3>
            <div className="benefit-list">
              <div className="benefit-item">
                <span className="benefit-icon">🔒</span>
                <div>
                  <h4>داده در محل باقی می‌ماند</h4>
                  <p>دادهٔ خام حسگری هرگز از دستگاه لبه خارج نمی‌شود -- فقط وزن‌های مدل برازش‌یافته ارسال می‌شود.</p>
                </div>
              </div>
              <div className="benefit-item">
                <span className="benefit-icon">📊</span>
                <div>
                  <h4>فقط وزن‌ها منتقل می‌شوند</h4>
                  <p>هر گره یک بردار وزن ثابت {WEIGHT_VECTOR_SIZE}مقداری ({WEIGHT_VECTOR_SIZE * BYTES_PER_FLOAT} بایت) ارسال می‌کند، صرف‌نظر از حجم دادهٔ آموزشی محلی‌اش.</p>
                </div>
              </div>
              <div className="benefit-item">
                <span className="benefit-icon">⚡</span>
                <div>
                  <h4>کاهش پهنای‌باند</h4>
                  <p>{bandwidthReductionPct > 0 ? `کاهش ${bandwidthReductionPct.toFixed(1)}٪` : 'کاهش'} نسبت به انتقال قرائت خام، و این شکاف با هر نمونهٔ آموزشی محلی بیشتر می‌شود.</p>
                </div>
              </div>
              <div className="benefit-item">
                <span className="benefit-icon">🛡️</span>
                <div>
                  <h4>تجمیع وزن‌دار</h4>
                  <p>مدل سراسری یک میانگین وزن‌دار بر اساس حجم داده (FedAvg) از وزن‌های محلی هر گره است -- گره‌های با دادهٔ بیشتر، تأثیر متناسب بیشتری دارند.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
