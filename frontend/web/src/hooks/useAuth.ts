import { useContext } from 'react'
import { AuthContext } from '../context/auth-context'
import type { AuthContextValue } from '../context/authContextTypes'

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
