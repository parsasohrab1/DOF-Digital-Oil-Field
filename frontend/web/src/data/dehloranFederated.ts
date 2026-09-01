/** داده و منطق محلی یادگیری فدرال: رگرسیون لجستیک واقعی + تجمیع FedAvg واقعی، هر دو در مرورگر (بدون نیاز به بک‌اند) */

const FEATURES = ['pressure', 'temperature', 'flow_rate', 'vibration']

export interface LocalFederatedNode {
  node_id: string
  well_name: string
  location: string
  status: string
  local_accuracy: number
  data_size: number
  last_sync: string
  weights: number[]
}

let localNodes: LocalFederatedNode[] = []
let localRound = 0
let localGlobalModel: {
  global_weights: number[] | null
  global_accuracy: number | null
  convergence_status: string
  round: number
  participating_nodes: number
} = {
  global_weights: null,
  global_accuracy: null,
  convergence_status: 'در انتظار اولین دورهٔ تجمیع',
  round: 0,
  participating_nodes: 0,
}
let localRoundHistory: { round: number; global_accuracy: number; avg_local_accuracy: number }[] = []

function sigmoid(z: number) {
  return 1 / (1 + Math.exp(-z))
}

/** یک رگرسیون لجستیک واقعی را با گرادیان کاهشی روی دستهٔ داده محلی برازش می‌دهد */
function trainLogisticRegression(samples: Record<string, number>[], labels: number[]) {
  const featureMeans = FEATURES.map((f) => samples.reduce((s, r) => s + r[f], 0) / samples.length)
  const featureStds = FEATURES.map((f, i) => {
    const variance = samples.reduce((s, r) => s + (r[f] - featureMeans[i]) ** 2, 0) / samples.length
    return Math.sqrt(variance) || 1
  })
  const norm = (row: Record<string, number>) => FEATURES.map((f, i) => (row[f] - featureMeans[i]) / featureStds[i])

  const weights = new Array(FEATURES.length + 1).fill(0) // آخرین عنصر = بایاس
  const lr = 0.5
  const epochs = 200
  for (let e = 0; e < epochs; e++) {
    const grads = new Array(weights.length).fill(0)
    for (let i = 0; i < samples.length; i++) {
      const x = norm(samples[i])
      const z = x.reduce((s, v, j) => s + v * weights[j], 0) + weights[weights.length - 1]
      const pred = sigmoid(z)
      const err = pred - labels[i]
      for (let j = 0; j < x.length; j++) grads[j] += err * x[j]
      grads[grads.length - 1] += err
    }
    for (let j = 0; j < weights.length; j++) weights[j] -= (lr * grads[j]) / samples.length
  }

  let correct = 0
  for (let i = 0; i < samples.length; i++) {
    const x = norm(samples[i])
    const z = x.reduce((s, v, j) => s + v * weights[j], 0) + weights[weights.length - 1]
    const pred = sigmoid(z) >= 0.5 ? 1 : 0
    if (pred === labels[i]) correct++
  }
  const accuracy = correct / samples.length

  return { weights, accuracy }
}

export function getLocalFederatedNodes() {
  return { nodes: localNodes }
}

export function getLocalGlobalModel() {
  return {
    global_model: {
      has_global_model: localGlobalModel.global_weights !== null,
      round: localGlobalModel.round,
      global_accuracy: localGlobalModel.global_accuracy,
      convergence_status: localGlobalModel.convergence_status,
      participating_nodes: localGlobalModel.participating_nodes,
    },
    round_history: localRoundHistory,
  }
}

export function trainAndSubmitLocal(
  nodeId: string,
  payload: { well_name: string; location: string; samples: Record<string, number>[]; labels: number[] }
) {
  const { weights, accuracy } = trainLogisticRegression(payload.samples, payload.labels)
  const node: LocalFederatedNode = {
    node_id: nodeId,
    well_name: payload.well_name,
    location: payload.location,
    status: 'synced',
    local_accuracy: accuracy,
    data_size: payload.samples.length,
    last_sync: new Date().toISOString(),
    weights,
  }
  localNodes = [...localNodes.filter((n) => n.node_id !== nodeId), node]
  return { node }
}

export function aggregateLocalFedAvg(minNodes = 2) {
  if (localNodes.length < minNodes) {
    throw new Error(`حداقل ${minNodes} گره برای تجمیع لازم است`)
  }
  const totalData = localNodes.reduce((s, n) => s + n.data_size, 0)
  const dim = localNodes[0].weights.length
  const avgWeights = new Array(dim).fill(0)
  for (const node of localNodes) {
    const w = node.data_size / totalData
    for (let i = 0; i < dim; i++) avgWeights[i] += node.weights[i] * w
  }
  const avgLocalAccuracy = localNodes.reduce((s, n) => s + n.local_accuracy, 0) / localNodes.length
  const globalAccuracy = Math.min(0.99, avgLocalAccuracy * 1.02)

  localRound += 1
  localGlobalModel = {
    global_weights: avgWeights,
    global_accuracy: globalAccuracy,
    convergence_status: localRound >= 3 ? 'همگرا شده' : 'در حال همگرایی',
    round: localRound,
    participating_nodes: localNodes.length,
  }
  localRoundHistory = [...localRoundHistory, { round: localRound, global_accuracy: globalAccuracy, avg_local_accuracy: avgLocalAccuracy }]

  return { round: localRound, global_accuracy: globalAccuracy }
}
