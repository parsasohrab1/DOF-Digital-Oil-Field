/** حالت اجرای زنده بدون اینترنت / بدون بک‌اند */

const STORAGE_KEY = 'sogf_offline_live'

/** صریحاً با VITE_OFFLINE_LIVE=true یا localStorage فعال می‌شود */
export function isOfflineLiveForced(): boolean {
  if (import.meta.env.VITE_OFFLINE_LIVE === 'true') return true
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function setOfflineLiveForced(on: boolean) {
  try {
    if (on) localStorage.setItem(STORAGE_KEY, '1')
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

/** مرورگر آفلاین است یا حالت آفلاین اجباری */
export function shouldUseLocalLive(): boolean {
  if (isOfflineLiveForced()) return true
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return true
  return false
}

export type LiveTransport = 'websocket' | 'sse' | 'simulation' | 'disconnected'

export function transportLabelFa(transport: LiveTransport | string): string {
  switch (transport) {
    case 'websocket':
      return 'زنده (وب‌سوکت)'
    case 'sse':
      return 'زنده (رویداد سمت سرور)'
    case 'simulation':
      return 'زنده (محلی — بدون اینترنت)'
    default:
      return 'زنده (محلی — بدون اینترنت)'
  }
}
