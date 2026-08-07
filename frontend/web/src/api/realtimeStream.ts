import { getApiBaseUrl, toWebSocketBaseUrl } from './config'
import { startLocalRealtimeStream } from './localRealtimeStream'
import { shouldUseLocalLive, type LiveTransport } from './offlineMode'

export type RealtimeSnapshotPayload = {
  type: 'snapshot'
  timestamp: string
  data: {
    sensor_records: Array<any>
    alerts: {
      count?: number
      alerts?: Array<any>
    }
  }
}

type RealtimeStreamHandlers = {
  onSnapshot: (payload: RealtimeSnapshotPayload) => void
  onTransportChange?: (transport: LiveTransport) => void
}

const WS_RETRY_BASE_MS = 2000
const WS_RETRY_MAX_MS = 15000
const SSE_RETRY_BASE_MS = 3000
const SSE_RETRY_MAX_MS = 12000
const REMOTE_GIVE_UP_MS = 8000

export function startRealtimeStream(handlers: RealtimeStreamHandlers): () => void {
  // حالت آفلاین / بدون اینترنت: فقط شبیه‌سازی محلی زنده
  if (shouldUseLocalLive()) {
    return startLocalRealtimeStream(handlers)
  }

  const token = localStorage.getItem('access_token')
  if (!token) {
    // بدون توکن هم داشبورد زنده بماند
    return startLocalRealtimeStream(handlers)
  }

  const apiBase = getApiBaseUrl()
  let closed = false
  let usingLocal = false
  let stopLocal: (() => void) | null = null
  let socket: WebSocket | null = null
  let sse: EventSource | null = null
  let wsRetryTimeout: number | undefined
  let sseRetryTimeout: number | undefined
  let giveUpTimeout: number | undefined
  let wsRetryAttempt = 0
  let sseRetryAttempt = 0

  const cleanupRemote = () => {
    if (wsRetryTimeout) {
      window.clearTimeout(wsRetryTimeout)
      wsRetryTimeout = undefined
    }
    if (sseRetryTimeout) {
      window.clearTimeout(sseRetryTimeout)
      sseRetryTimeout = undefined
    }
    if (giveUpTimeout) {
      window.clearTimeout(giveUpTimeout)
      giveUpTimeout = undefined
    }
    if (socket) {
      socket.close()
      socket = null
    }
    if (sse) {
      sse.close()
      sse = null
    }
  }

  const fallBackToLocal = () => {
    if (closed || usingLocal) return
    usingLocal = true
    cleanupRemote()
    stopLocal = startLocalRealtimeStream(handlers)
  }

  const scheduleWsRetry = () => {
    if (closed || usingLocal) return
    const delay = Math.min(WS_RETRY_BASE_MS * 2 ** wsRetryAttempt, WS_RETRY_MAX_MS)
    wsRetryAttempt += 1
    wsRetryTimeout = window.setTimeout(connectWebSocket, delay)
  }

  const scheduleSseRetry = () => {
    if (closed || usingLocal || sse) return
    const delay = Math.min(SSE_RETRY_BASE_MS * 2 ** sseRetryAttempt, SSE_RETRY_MAX_MS)
    sseRetryAttempt += 1
    sseRetryTimeout = window.setTimeout(trySSEFallback, delay)
  }

  const trySSEFallback = () => {
    if (closed || usingLocal || sse) return

    const sseUrl = `${apiBase}/stream/realtime/sse?token=${encodeURIComponent(token)}`
    try {
      sse = new EventSource(sseUrl)
    } catch {
      fallBackToLocal()
      return
    }
    handlers.onTransportChange?.('sse')

    sse.addEventListener('snapshot', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as RealtimeSnapshotPayload
        handlers.onSnapshot(payload)
        sseRetryAttempt = 0
      } catch {
        /* ignore */
      }
    })

    sse.onerror = () => {
      if (sse) {
        sse.close()
        sse = null
      }
      if (!closed && !usingLocal) {
        handlers.onTransportChange?.('disconnected')
        scheduleSseRetry()
      }
    }
  }

  const connectWebSocket = () => {
    if (closed || usingLocal) return

    const wsBaseUrl = toWebSocketBaseUrl(apiBase)
    const wsUrl = `${wsBaseUrl}/stream/realtime/ws?token=${encodeURIComponent(token)}`
    try {
      socket = new WebSocket(wsUrl)
    } catch {
      fallBackToLocal()
      return
    }

    socket.onopen = () => {
      wsRetryAttempt = 0
      if (giveUpTimeout) {
        window.clearTimeout(giveUpTimeout)
        giveUpTimeout = undefined
      }
      handlers.onTransportChange?.('websocket')
      if (sse) {
        sse.close()
        sse = null
      }
    }

    socket.onmessage = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as RealtimeSnapshotPayload
        handlers.onSnapshot(payload)
      } catch {
        /* ignore */
      }
    }

    socket.onerror = () => {
      trySSEFallback()
    }

    socket.onclose = () => {
      socket = null
      if (closed || usingLocal) return
      trySSEFallback()
      scheduleWsRetry()
    }
  }

  // اگر ظرف چند ثانیه وصل نشد، به زنده محلی برو (بدون اینترنت)
  giveUpTimeout = window.setTimeout(() => {
    if (!closed && !usingLocal) fallBackToLocal()
  }, REMOTE_GIVE_UP_MS)

  connectWebSocket()

  return () => {
    closed = true
    cleanupRemote()
    stopLocal?.()
    stopLocal = null
    handlers.onTransportChange?.('disconnected')
  }
}
