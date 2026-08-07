import { ReactNode } from 'react'

/** Auth gate disabled — app is open without login. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  return <>{children}</>
}
