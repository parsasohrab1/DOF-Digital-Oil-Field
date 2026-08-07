import { FormEvent, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import './Login.css'

export default function Login() {
  const { isAuthenticated, login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'ورود ناموفق بود')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page" dir="rtl">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>هوشمندسازی میادین نفت و گاز</h1>
        <p className="login-subtitle">میدان دهلران · شرکت ملی نفت مناطق مرکزی</p>

        <label htmlFor="username">نام کاربری</label>
        <input
          id="username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />

        <label htmlFor="password">رمز عبور</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />

        {error && <p className="login-error">{error}</p>}

        <button type="submit" disabled={loading}>
          {loading ? 'در حال ورود…' : 'ورود'}
        </button>
      </form>
    </div>
  )
}
