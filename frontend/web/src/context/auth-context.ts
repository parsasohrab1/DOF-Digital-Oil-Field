import { createContext } from 'react'
import type { AuthContextValue } from './authContextTypes'

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)
