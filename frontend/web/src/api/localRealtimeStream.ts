import { getDehloranAlerts } from '../data/dehloranAlerts'
import { getDehloranLiveState, SENSOR_VARIABLES } from '../data/dehloranField'
import type { RealtimeSnapshotPayload } from './realtimeStream'
import type { LiveTransport } from './offlineMode'

const TICK_MS = 4000

type Handlers = {
  onSnapshot: (payload: RealtimeSnapshotPayload) => void
  onTransportChange?: (transport: LiveTransport) => void
}

/** جریان زنده محلی از داده‌های میدان دهلران — بدون شبکه */
export function startLocalRealtimeStream(handlers: Handlers): () => void {
  let closed = false

  const emit = () => {
    if (closed) return
    const tick = Date.now()
    const wells = getDehloranLiveState(tick)
    const alerts = getDehloranAlerts(tick)

    const sensor_records = wells.flatMap((w) => {
      const values: Record<string, number | null> = {
        thp: w.thp,
        tht: w.tht,
        oil_rate: w.oilRate,
        gas_rate: w.gasRate,
        water_rate: w.waterRate,
        water_cut: w.waterCut,
        esp_current: w.pumpOnline ? Math.round((28 + w.equipmentRisk * 0.15) * 10) / 10 : 0,
        esp_vibration: w.pumpOnline ? Math.round((1.2 + w.equipmentRisk * 0.04) * 100) / 100 : 0,
        health_score: w.healthScore,
      }
      return SENSOR_VARIABLES.filter((s) => s.key in values).map((s) => ({
        well_name: w.id,
        tag: s.key,
        value: values[s.key as keyof typeof values],
        unit: s.unit,
        timestamp: new Date(tick).toISOString(),
        status: w.status,
      }))
    })

    const payload: RealtimeSnapshotPayload = {
      type: 'snapshot',
      timestamp: new Date(tick).toISOString(),
      data: {
        sensor_records,
        alerts: {
          count: alerts.filter((a) => a.status === 'open').length,
          alerts,
        },
      },
    }
    handlers.onSnapshot(payload)
  }

  handlers.onTransportChange?.('simulation')
  emit()
  const id = window.setInterval(emit, TICK_MS)

  return () => {
    closed = true
    window.clearInterval(id)
    handlers.onTransportChange?.('disconnected')
  }
}
