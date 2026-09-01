/** داده و منطق محلی پیش‌بینی سری‌زمانی LSTM (بدون نیاز به بک‌اند) */

import { DEHLORAN_WELLS } from './dehloranField'

export const LSTM_MODEL_TYPES: { id: string; labelFa: string }[] = [
  { id: 'stacked_lstm', labelFa: 'LSTM چندلایه' },
  { id: 'bidirectional', labelFa: 'LSTM دوطرفه' },
  { id: 'attention', labelFa: 'LSTM با توجه (Attention)' },
]

interface LocalLstmModel {
  well_name: string
  model_type: string
  sequence_length: number
  forecast_horizon: number
}

let localLstmModels: LocalLstmModel[] = [
  { well_name: DEHLORAN_WELLS[0].id, model_type: 'stacked_lstm', sequence_length: 60, forecast_horizon: 24 },
  { well_name: DEHLORAN_WELLS[2].id, model_type: 'bidirectional', sequence_length: 60, forecast_horizon: 24 },
]

export function getLocalLstmModels() {
  return { models: localLstmModels, count: localLstmModels.length }
}

export function trainLocalLstmModel(data: { well_name: string; model_type: string }) {
  const model: LocalLstmModel = {
    well_name: data.well_name,
    model_type: data.model_type,
    sequence_length: 60,
    forecast_horizon: 24,
  }
  localLstmModels = [model, ...localLstmModels.filter((m) => m.well_name !== data.well_name)]

  const train_mae = 1.2 + Math.random() * 0.8
  const val_mae = train_mae + Math.random() * 0.5
  return {
    training_status: 'completed',
    metrics: { train_mae, val_mae },
    epochs_trained: 50,
  }
}

/** یک سری زمانی نمایشی و واقع‌گرایانه (روند + نوسان + نویز) برای پرکردن سریع فرم‌ها تولید می‌کند */
export function generateDemoSeries(count: number, mean: number, amplitude: number): number[] {
  const points: number[] = []
  for (let i = 0; i < count; i++) {
    const seasonal = Math.sin(i / 8) * amplitude
    const drift = (i / count) * amplitude * 0.3
    const noise = (Math.random() - 0.5) * amplitude * 0.15
    points.push(Number((mean + seasonal + drift + noise).toFixed(1)))
  }
  return points
}

export interface LocalForecastResult {
  sensor_id: string
  predictions: number[]
  forecast_steps: number
  sequence_length: number
  confidence: number
  timestamp: string
  confidence_lower: number[]
  confidence_upper: number[]
  model_type: string
}

/** برون‌یابی روند + نویز میراشونده از انتهای سری زمانی ورودی؛ شبیه‌سازی محلی جایگزین استنتاج واقعی مدل LSTM */
export function forecastLocalTimeSeries(data: {
  sensor_id: string
  historical_data: number[]
  forecast_steps: number
}): LocalForecastResult {
  const { sensor_id, historical_data, forecast_steps } = data
  const tail = historical_data.slice(-20)
  const mean = tail.reduce((a, b) => a + b, 0) / tail.length
  const trend = (tail[tail.length - 1] - tail[0]) / tail.length
  const variance = tail.reduce((a, b) => a + (b - mean) ** 2, 0) / tail.length
  const std = Math.sqrt(variance) || Math.abs(mean) * 0.02 || 1

  const predictions: number[] = []
  const confidence_lower: number[] = []
  const confidence_upper: number[] = []
  let last = tail[tail.length - 1]
  for (let i = 0; i < forecast_steps; i++) {
    last = last + trend + (Math.random() - 0.5) * std * 0.3
    predictions.push(Number(last.toFixed(2)))
    const band = std * (0.5 + i * 0.03)
    confidence_lower.push(Number((last - band).toFixed(2)))
    confidence_upper.push(Number((last + band).toFixed(2)))
  }

  return {
    sensor_id,
    predictions,
    forecast_steps,
    sequence_length: 60,
    confidence: 0.87,
    timestamp: new Date().toISOString(),
    confidence_lower,
    confidence_upper,
    model_type: 'stacked_lstm (شبیه‌سازی محلی)',
  }
}
