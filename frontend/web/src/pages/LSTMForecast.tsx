import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, AreaChart } from 'recharts'
import { mlAPI } from '../api/services'
import { DEHLORAN_WELLS } from '../data/dehloranField'
import {
  LSTM_MODEL_TYPES,
  getLocalLstmModels,
  trainLocalLstmModel,
  forecastLocalTimeSeries,
  generateDemoSeries,
  type LocalForecastResult,
} from '../data/dehloranLstm'
import './LSTMForecast.css'

type ForecastResult = LocalForecastResult

export default function LSTMForecast() {
  const queryClient = useQueryClient()
  const [selectedSensor, setSelectedSensor] = useState<string>(`${DEHLORAN_WELLS[0].id}-فشار`)
  const [forecastSteps, setForecastSteps] = useState<number>(24)
  const [historicalData, setHistoricalData] = useState<string>('')
  const [trainingWell, setTrainingWell] = useState<string>(DEHLORAN_WELLS[0].id)
  const [trainingData, setTrainingData] = useState<string>('')
  const [modelType, setModelType] = useState<string>('stacked_lstm')

  const { data: modelsData } = useQuery({
    queryKey: ['lstm-models'],
    queryFn: async () => {
      try {
        const response = await mlAPI.getLSTMModels()
        return response.data
      } catch {
        return getLocalLstmModels()
      }
    },
    refetchInterval: 30000,
  })

  const forecastMutation = useMutation({
    mutationFn: async (data: { sensor_id: string; historical_data: number[]; forecast_steps: number }) => {
      try {
        const response = await mlAPI.forecastTimeSeries(data)
        return response.data as ForecastResult
      } catch {
        return forecastLocalTimeSeries(data)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forecast'] })
    },
  })

  const trainingMutation = useMutation({
    mutationFn: async (data: any) => {
      try {
        const response = await mlAPI.trainLSTMModel(data)
        return response.data
      } catch {
        return trainLocalLstmModel(data)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lstm-models'] })
      alert('آموزش مدل با موفقیت به پایان رسید!')
    },
  })

  const fillDemoForecastData = () => {
    setHistoricalData(generateDemoSeries(90, 320, 25).join(', '))
  }

  const fillDemoTrainingData = () => {
    setTrainingData(generateDemoSeries(220, 320, 25).join(', '))
  }

  const handleForecast = () => {
    if (!selectedSensor || !historicalData) {
      alert('لطفاً شناسهٔ حسگر و دادهٔ تاریخی را وارد کنید')
      return
    }

    try {
      const dataPoints = historicalData.split(',').map((v) => parseFloat(v.trim())).filter((v) => !isNaN(v))
      if (dataPoints.length < 60) {
        alert('دادهٔ تاریخی باید حداقل ۶۰ نقطه داشته باشد')
        return
      }

      forecastMutation.mutate({
        sensor_id: selectedSensor,
        historical_data: dataPoints,
        forecast_steps: forecastSteps,
      })
    } catch {
      alert('قالب دادهٔ تاریخی نامعتبر است. از اعداد جداشده با کاما استفاده کنید.')
    }
  }

  const handleTrain = () => {
    if (!trainingWell || !trainingData) {
      alert('لطفاً نام چاه و دادهٔ آموزشی را وارد کنید')
      return
    }

    try {
      const dataPoints = trainingData.split(',').map((v) => parseFloat(v.trim())).filter((v) => !isNaN(v))
      if (dataPoints.length < 200) {
        alert('دادهٔ آموزشی باید حداقل ۲۰۰ نقطه داشته باشد')
        return
      }

      trainingMutation.mutate({
        well_name: trainingWell,
        time_series_data: dataPoints,
        model_type: modelType,
        sequence_length: 60,
        forecast_horizon: 24,
        epochs: 50,
        batch_size: 32,
        validation_split: 0.2,
      })
    } catch {
      alert('قالب دادهٔ آموزشی نامعتبر است. از اعداد جداشده با کاما استفاده کنید.')
    }
  }

  const chartData: any[] = []
  if (forecastMutation.data) {
    const result = forecastMutation.data
    const historical = historicalData.split(',').map((v) => parseFloat(v.trim())).filter((v) => !isNaN(v))

    historical.slice(-60).forEach((value, idx) => {
      chartData.push({ time: `T-${60 - idx}`, value, type: 'historical' })
    })

    result.predictions.forEach((pred, idx) => {
      chartData.push({
        time: `T+${idx + 1}`,
        value: pred,
        type: 'forecast',
        lower: result.confidence_lower?.[idx],
        upper: result.confidence_upper?.[idx],
      })
    })
  }

  return (
    <div className="lstm-forecast-page" dir="rtl">
      <h2>پیش‌بینی سری‌زمانی LSTM</h2>

      <div className="lstm-grid">
        <div className="lstm-card">
          <h3>آموزش مدل LSTM</h3>
          <div className="form-group">
            <label>نام چاه</label>
            <select value={trainingWell} onChange={(e) => setTrainingWell(e.target.value)}>
              {DEHLORAN_WELLS.map((w) => (
                <option key={w.id} value={w.id}>{w.nameFa} ({w.id})</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>نوع مدل</label>
            <select value={modelType} onChange={(e) => setModelType(e.target.value)}>
              {LSTM_MODEL_TYPES.map((t) => (
                <option key={t.id} value={t.id}>{t.labelFa}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>
              دادهٔ آموزشی (جداشده با کاما، حداقل ۲۰۰ نقطه)
              <button type="button" className="btn-fill-demo" onClick={fillDemoTrainingData}>پر کردن با دادهٔ نمونه</button>
            </label>
            <textarea
              value={trainingData}
              onChange={(e) => setTrainingData(e.target.value)}
              rows={5}
              placeholder="مثلاً: ۱۰۰.۵, ۱۰۲.۳, ۹۸.۷, ..."
            />
          </div>
          <button onClick={handleTrain} disabled={trainingMutation.isPending} className="btn-train">
            {trainingMutation.isPending ? 'در حال آموزش...' : 'آموزش مدل'}
          </button>
          {trainingMutation.data && (
            <div className="training-results">
              <h4>نتایج آموزش</h4>
              <div>وضعیت: {trainingMutation.data.training_status === 'completed' ? 'کامل شد' : trainingMutation.data.training_status}</div>
              <div>خطای میانگین آموزش (MAE): {trainingMutation.data.metrics?.train_mae?.toFixed(4)}</div>
              <div>خطای میانگین اعتبارسنجی (MAE): {trainingMutation.data.metrics?.val_mae?.toFixed(4)}</div>
              <div>تعداد دوره‌ها (Epochs): {trainingMutation.data.epochs_trained}</div>
            </div>
          )}
        </div>

        <div className="lstm-card">
          <h3>تولید پیش‌بینی</h3>
          <div className="form-group">
            <label>شناسهٔ حسگر</label>
            <input
              type="text"
              value={selectedSensor}
              onChange={(e) => setSelectedSensor(e.target.value)}
              placeholder={`مثلاً ${DEHLORAN_WELLS[0].id}-فشار`}
            />
          </div>
          <div className="form-group">
            <label>تعداد گام‌های پیش‌بینی</label>
            <input
              type="number"
              value={forecastSteps}
              onChange={(e) => setForecastSteps(parseInt(e.target.value) || 24)}
              min={1}
              max={100}
            />
          </div>
          <div className="form-group">
            <label>
              دادهٔ تاریخی (جداشده با کاما، حداقل ۶۰ نقطه)
              <button type="button" className="btn-fill-demo" onClick={fillDemoForecastData}>پر کردن با دادهٔ نمونه</button>
            </label>
            <textarea
              value={historicalData}
              onChange={(e) => setHistoricalData(e.target.value)}
              rows={5}
              placeholder="مثلاً: ۱۰۰.۵, ۱۰۲.۳, ۹۸.۷, ..."
            />
          </div>
          <button onClick={handleForecast} disabled={forecastMutation.isPending} className="btn-forecast">
            {forecastMutation.isPending ? 'در حال پیش‌بینی...' : 'تولید پیش‌بینی'}
          </button>
        </div>

        <div className="lstm-card">
          <h3>مدل‌های آموزش‌دیده</h3>
          <div className="models-list">
            {modelsData?.models?.length === 0 ? (
              <p className="no-models">هیچ مدل آموزش‌دیده‌ای موجود نیست. ابتدا یک مدل آموزش دهید.</p>
            ) : (
              modelsData?.models?.map((model: any, idx: number) => (
                <div key={idx} className="model-item">
                  <div className="model-name">{model.well_name}</div>
                  <div className="model-type">{LSTM_MODEL_TYPES.find((t) => t.id === model.model_type)?.labelFa || model.model_type}</div>
                  <div className="model-info">
                    طول دنباله: {model.sequence_length} | افق پیش‌بینی: {model.forecast_horizon}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {forecastMutation.data && (
          <div className="lstm-card chart-card">
            <h3>نتایج پیش‌بینی</h3>
            <div className="forecast-info">
              <div>حسگر: {forecastMutation.data.sensor_id}</div>
              <div>تعداد گام‌های پیش‌بینی: {forecastMutation.data.forecast_steps}</div>
              <div>سطح اطمینان: {(forecastMutation.data.confidence * 100).toFixed(1)}%</div>
              {forecastMutation.data.model_type && <div>مدل: {forecastMutation.data.model_type}</div>}
            </div>
            <ResponsiveContainer width="100%" height={400}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="upper" stroke="none" fill="#8884d8" fillOpacity={0.1} name="سقف بازهٔ اطمینان" />
                <Area type="monotone" dataKey="lower" stroke="none" fill="#8884d8" fillOpacity={0.1} name="کف بازهٔ اطمینان" />
                <Line type="monotone" dataKey="value" stroke="#8884d8" strokeWidth={2} name="مقدار" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
            <div className="predictions-list">
              <h4>پیش‌بینی‌ها</h4>
              <div className="predictions-grid">
                {forecastMutation.data.predictions.map((pred, idx) => (
                  <div key={idx} className="prediction-item">
                    <div className="pred-step">گام {idx + 1}</div>
                    <div className="pred-value">{pred.toFixed(2)}</div>
                    {forecastMutation.data.confidence_lower && forecastMutation.data.confidence_upper && (
                      <div className="pred-range">
                        [{forecastMutation.data.confidence_lower[idx].toFixed(2)}, {forecastMutation.data.confidence_upper[idx].toFixed(2)}]
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
