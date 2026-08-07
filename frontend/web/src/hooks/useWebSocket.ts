import { useEffect, useRef, useState, useCallback } from 'react'
import { startRealtimeStream, type RealtimeSnapshotPayload } from '../api/realtimeStream'
import type { LiveTransport } from '../api/offlineMode'

export type RealtimeTransport = LiveTransport

export function useWebSocket(options?: {
  enabled?: boolean
  onSnapshot?: (payload: RealtimeSnapshotPayload) => void
}) {
  const enabled = options?.enabled ?? true
  const [transport, setTransport] = useState<RealtimeTransport>('simulation')
  const [lastSnapshot, setLastSnapshot] = useState<RealtimeSnapshotPayload | null>(null)
  const onSnapshotRef = useRef(options?.onSnapshot)
  onSnapshotRef.current = options?.onSnapshot

  const handleSnapshot = useCallback((payload: RealtimeSnapshotPayload) => {
    setLastSnapshot(payload)
    onSnapshotRef.current?.(payload)
  }, [])

  useEffect(() => {
    if (!enabled) {
      setTransport('disconnected')
      return
    }

    const stop = startRealtimeStream({
      onTransportChange: setTransport,
      onSnapshot: handleSnapshot,
    })

    return stop
  }, [enabled, handleSnapshot])

  return { transport, lastSnapshot }
}
