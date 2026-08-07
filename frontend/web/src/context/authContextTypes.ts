export interface AuthUser {
  id: number
  username: string
  email: string
  role: string
  disabled: boolean
  two_factor_enabled: boolean
}

export interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}
