import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { federatedAPI } from '../api/services'
import './FederatedLearning.css'

// Fixed feature schema the backend's local models are trained/averaged on
// (backend/ml-inference-service/federated_learning.py FEATURE_NAMES). Kept
// here only to generate a demo dataset client-side -- the values themselves
// never need to match any real sensor scale, since this is purely to show
// real local training + FedAvg aggregation running end to end.
const FEATURES = ['pressure', 'temperature', 'flow_rate', 'vibration']
const BYTES_PER_FLOAT = 8
const WEIGHT_VECTOR_SIZE = FEATURES.length + 1 // + bias term

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function generateSyntheticTrainingBatch(sampleCount: number) {
  // Clearly-separable synthetic data so the real logistic regression fit
  // converges to a high, meaningful accuracy -- this is demo data standing
  // in for what would otherwise be a well's own historical sensor readings,
  // which is exactly the raw data federated learning is meant to keep local.
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
  const [wellNameInput, setWellNameInput] = useState('PROD-001')
  const [locationInput, setLocationInput] = useState('Field A')
  const [aggregateError, setAggregateError] = useState<string | null>(null)

  const nodesQuery = useQuery({
    queryKey: ['federated-nodes'],
    queryFn: () => federatedAPI.getNodes(),
    refetchInterval: 5000,
  })

  const globalModelQuery = useQuery({
    queryKey: ['federated-global-model'],
    queryFn: () => federatedAPI.getGlobalModel(),
    refetchInterval: 5000,
  })

  const trainMutation = useMutation({
    mutationFn: () => {
      const { samples, labels } = generateSyntheticTrainingBatch(60)
      return federatedAPI.trainAndSubmit(nodeIdInput, {
        well_name: wellNameInput,
        location: locationInput,
        samples,
        labels,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['federated-nodes'] })
    },
  })

  const aggregateMutation = useMutation({
    mutationFn: () => federatedAPI.aggregate(2),
    onSuccess: () => {
      setAggregateError(null)
      queryClient.invalidateQueries({ queryKey: ['federated-nodes'] })
      queryClient.invalidateQueries({ queryKey: ['federated-global-model'] })
    },
    onError: (err: any) => setAggregateError(err?.response?.data?.detail || 'Aggregation failed'),
  })

  const nodes = nodesQuery.data?.nodes || []
  const globalModel = globalModelQuery.data?.global_model
  const roundHistory = globalModelQuery.data?.round_history || []

  // Real bandwidth comparison: raw sensor readings each node trained on
  // (data_size samples x number of features) vs. the fixed-size weight
  // vector actually transmitted per node -- this is what federated learning
  // saves, computed from the real registered nodes rather than a hardcoded
  // number.
  const totalRawSamples = nodes.reduce((sum: number, n: any) => sum + n.data_size, 0)
  const rawBytes = totalRawSamples * FEATURES.length * BYTES_PER_FLOAT
  const transmittedBytes = nodes.length * WEIGHT_VECTOR_SIZE * BYTES_PER_FLOAT
  const bandwidthData = [
    { approach: 'Raw data (if centralized)', bytes: rawBytes },
    { approach: 'Federated (weights only)', bytes: transmittedBytes },
  ]
  const bandwidthReductionPct = rawBytes > 0 ? (1 - transmittedBytes / rawBytes) * 100 : 0

  return (
    <div className="federated-learning-page">
      <div className="page-header">
        <h1>Federated Learning</h1>
        <p>Privacy-preserving distributed training with minimal bandwidth usage</p>
      </div>

      <div className="fl-stats-grid">
        <div className="stat-card">
          <h3>Participating Nodes</h3>
          <div className="stat-value">{nodes.length}</div>
          <div className="stat-label">Syncing: {nodes.filter((n: any) => n.status === 'syncing').length}</div>
        </div>
        <div className="stat-card">
          <h3>Global Model Accuracy</h3>
          <div className="stat-value">{pct(globalModel?.global_accuracy)}</div>
          <div className="stat-label">{globalModel?.convergence_status || 'no rounds yet'}</div>
        </div>
        <div className="stat-card">
          <h3>Bandwidth Saved</h3>
          <div className="stat-value">{bandwidthReductionPct > 0 ? `${bandwidthReductionPct.toFixed(1)}%` : '—'}</div>
          <div className="stat-label">vs. transmitting raw readings</div>
        </div>
        <div className="stat-card">
          <h3>Data Privacy</h3>
          <div className="stat-value">100%</div>
          <div className="stat-label">Only model weights leave each node</div>
        </div>
      </div>

      <div className="fl-content-grid">
        <div className="nodes-section">
          <h2>Edge Nodes</h2>

          <div className="node-register-form">
            <div className="form-row">
              <input placeholder="Node ID" value={nodeIdInput} onChange={(e) => setNodeIdInput(e.target.value)} />
              <input placeholder="Well name" value={wellNameInput} onChange={(e) => setWellNameInput(e.target.value)} />
              <input placeholder="Location" value={locationInput} onChange={(e) => setLocationInput(e.target.value)} />
            </div>
            <button onClick={() => trainMutation.mutate()} disabled={trainMutation.isPending}>
              {trainMutation.isPending ? 'Training locally...' : 'Simulate Local Training + Submit'}
            </button>
            <p className="muted">
              Fits a real logistic-regression model on a synthetic demo batch generated in the
              browser, then submits only the resulting weights (never the samples) to the coordinator.
            </p>
            {trainMutation.isError && <p className="error">Training/submit failed.</p>}
          </div>

          {nodes.length === 0 ? (
            <p className="muted">No edge nodes have submitted an update yet.</p>
          ) : (
            <div className="nodes-list">
              {nodes.map((node: any) => (
                <div key={node.node_id} className={`node-card ${node.status}`}>
                  <div className="node-header">
                    <span className="node-id">{node.node_id}</span>
                    <span className={`node-status ${node.status}`}>{node.status}</span>
                  </div>
                  <div className="node-info">
                    <p><strong>Location:</strong> {node.location}</p>
                    <p><strong>Well:</strong> {node.well_name}</p>
                    <p><strong>Local Accuracy:</strong> {pct(node.local_accuracy)}</p>
                    <p><strong>Samples Trained On:</strong> {node.data_size}</p>
                    <p><strong>Last Sync:</strong> {new Date(node.last_sync).toLocaleString()}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="global-model-section">
          <h2>Global Model</h2>
          <div className="form-row">
            <button onClick={() => aggregateMutation.mutate()} disabled={aggregateMutation.isPending || nodes.length < 2}>
              {aggregateMutation.isPending ? 'Aggregating...' : 'Run FedAvg Aggregation Round'}
            </button>
          </div>
          {nodes.length < 2 && <p className="muted">Need at least 2 nodes to aggregate.</p>}
          {aggregateError && <p className="error">{aggregateError}</p>}

          {globalModel?.has_global_model ? (
            <div className="global-model-card">
              <div className="model-header">
                <h3>Round {globalModel.round}</h3>
                <span className={`convergence-status ${globalModel.convergence_status}`}>
                  {globalModel.convergence_status}
                </span>
              </div>
              <div className="model-metrics">
                <div className="metric-item">
                  <span className="metric-label">Global Accuracy</span>
                  <span className="metric-value">{pct(globalModel.global_accuracy)}</span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Participating Nodes</span>
                  <span className="metric-value">{globalModel.participating_nodes}</span>
                </div>
              </div>

              {roundHistory.length > 0 && (
                <div className="training-history">
                  <h3>Aggregation Round History</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={roundHistory}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="round" />
                      <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                      <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
                      <Legend />
                      <Line type="monotone" dataKey="global_accuracy" stroke="#3498db" name="Global Accuracy" />
                      <Line type="monotone" dataKey="avg_local_accuracy" stroke="#2ecc71" name="Avg Local Accuracy" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          ) : (
            <p className="muted">No aggregation round has run yet.</p>
          )}
        </div>
      </div>

      <div className="comparison-section">
        <h2>Bandwidth &amp; Privacy Comparison</h2>
        <div className="comparison-grid">
          <div className="comparison-chart">
            <h3>Bandwidth Usage (estimated from registered nodes)</h3>
            {nodes.length === 0 ? (
              <p className="muted">Register at least one node to see a comparison.</p>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={bandwidthData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="approach" />
                  <YAxis tickFormatter={(v) => `${(v / 1024).toFixed(1)} KB`} />
                  <Tooltip formatter={(v: number) => `${(v / 1024).toFixed(2)} KB`} />
                  <Legend />
                  <Bar dataKey="bytes" fill="#8884d8" name="Bytes transmitted" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="privacy-benefits">
            <h3>Privacy Benefits</h3>
            <div className="benefit-list">
              <div className="benefit-item">
                <span className="benefit-icon">🔒</span>
                <div>
                  <h4>Data Stays Local</h4>
                  <p>Raw sensor data never leaves the edge device -- only the fitted model's weights are sent.</p>
                </div>
              </div>
              <div className="benefit-item">
                <span className="benefit-icon">📊</span>
                <div>
                  <h4>Only Weights Transmitted</h4>
                  <p>Each node sends a fixed {WEIGHT_VECTOR_SIZE}-value weight vector ({WEIGHT_VECTOR_SIZE * BYTES_PER_FLOAT} bytes), regardless of how much local data it trained on.</p>
                </div>
              </div>
              <div className="benefit-item">
                <span className="benefit-icon">⚡</span>
                <div>
                  <h4>Reduced Bandwidth</h4>
                  <p>{bandwidthReductionPct > 0 ? `${bandwidthReductionPct.toFixed(1)}% reduction` : 'Reduction'} vs transmitting raw readings, and the gap grows with every additional sample trained on locally.</p>
                </div>
              </div>
              <div className="benefit-item">
                <span className="benefit-icon">🛡️</span>
                <div>
                  <h4>Weighted Aggregation</h4>
                  <p>The global model is a data-size-weighted average (FedAvg) of every node's local weights -- nodes with more data have proportionally more influence.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
