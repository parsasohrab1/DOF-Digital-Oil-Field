import { useEffect, useState, ReactNode } from 'react'
import { authAPI } from '../api/services'
import { shouldUseLocalLive } from '../api/offlineMode'
import type { AuthUser } from './authContextTypes'
import { AuthContext } from './auth-context'

const GUEST_USER: AuthUser = {
  id: 0,
  username: 'guest',
  email: 'guest@sogf.local',
  role: 'system_admin',
  disabled: false,
  two_factor_enabled: false,
}

const OFFLINE_USER: AuthUser = {
  id: 1,
  username: 'offline_operator',
  email: 'offline@dehloran.local',
  role: 'system_admin',
  disabled: false,
  two_factor_enabled: false,
}

const DEV_USERNAME = 'admin'
const DEV_PASSWORD = 'Admin@123'

/** توکن ساختگی محلی فقط برای عبور از گیت‌های کلاینت — در سرور اعتبار ندارد */
function ensureOfflineToken() {
  if (!localStorage.getItem('access_token')) {
    localStorage.setItem('access_token', 'offline-live-token')
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(
    shouldUseLocalLive() ? OFFLINE_USER : GUEST_USER
  )
  const [isLoading] = useState(false)

  useEffect(() => {
    let cancelled = false

    const bootstrap = async () => {
      if (shouldUseLocalLive()) {
        ensureOfflineToken()
        if (!cancelled) setUser(OFFLINE_USER)
        return
      }

      const existing = localStorage.getItem('access_token')
      if (existing && existing !== 'offline-live-token') {
        try {
          const currentUser = await authAPI.getCurrentUser()
          if (!cancelled) setUser(currentUser)
          return
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
        }
      }

      try {
        const tokenResponse = await authAPI.login(DEV_USERNAME, DEV_PASSWORD)
        localStorage.setItem('access_token', tokenResponse.access_token)
        localStorage.setItem('refresh_token', tokenResponse.refresh_token)
        const currentUser = await authAPI.getCurrentUser()
        if (!cancelled) setUser(currentUser)
      } catch {
        ensureOfflineToken()
        if (!cancelled) setUser(OFFLINE_USER)
      }
    }

    bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const login = async (username: string, password: string) => {
    if (shouldUseLocalLive()) {
      ensureOfflineToken()
      setUser({ ...OFFLINE_USER, username })
      return
    }
    const tokenResponse = await authAPI.login(username, password)
    localStorage.setItem('access_token', tokenResponse.access_token)
    localStorage.setItem('refresh_token', tokenResponse.refresh_token)
    const currentUser = await authAPI.getCurrentUser()
    setUser(currentUser)
  }

  const logout = () => {
    try {
      authAPI.logout()
    } catch {
      /* offline */
    }
    if (shouldUseLocalLive()) {
      ensureOfflineToken()
      setUser(OFFLINE_USER)
      return
    }
    setUser(GUEST_USER)
  }

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: true, isLoading, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}
