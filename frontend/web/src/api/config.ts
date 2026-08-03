/** Shared API base URL — uses Vite proxy in dev when VITE_API_BASE_URL is unset. */
export function getApiBaseUrl(): string {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '')
  }
  if (typeof window !== 'undefined') {
    if (import.meta.env.DEV || window.location.port === '3000' || window.location.port === '4173') {
      return window.location.origin
    }
  }
  return 'http://localhost:18000'
}

export function toWebSocketBaseUrl(httpBaseUrl: string): string {
  const url = new URL(
    httpBaseUrl,
    typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000'
  )
  const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${url.host}`
}
