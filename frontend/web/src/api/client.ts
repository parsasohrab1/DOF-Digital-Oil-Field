import axios, { AxiosInstance, AxiosError } from 'axios'
import { getApiBaseUrl } from './config'
import { shouldUseLocalLive } from './offlineMode'

const API_BASE_URL = getApiBaseUrl()

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  // در حالت آفلاین سریع شکست بخور تا fallback محلی فعال شود
  timeout: shouldUseLocalLive() ? 2500 : 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use(
  (config) => {
    if (shouldUseLocalLive()) {
      // درخواست‌های API در حالت آفلاین را زود قطع کن
      config.timeout = Math.min(config.timeout ?? 2500, 2500)
    }

    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }

    config.headers['X-Correlation-ID'] = generateCorrelationId()
    return config
  },
  (error) => Promise.reject(error)
)

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (
      error.code === 'ERR_NETWORK' ||
      error.code === 'ERR_EMPTY_RESPONSE' ||
      error.code === 'ECONNABORTED' ||
      error.message?.includes('Failed to fetch') ||
      error.message?.includes('timeout')
    ) {
      const networkError = {
        ...error,
        isNetworkError: true,
        message: 'Service unavailable',
        code: error.code || 'ERR_NETWORK',
      }
      return Promise.reject(networkError)
    }

    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken && !shouldUseLocalLive()) {
        try {
          const response = await axios.post(`${API_BASE_URL}/api/auth/refresh`, {
            refresh_token: refreshToken,
          })

          const { access_token, refresh_token: newRefreshToken } = response.data
          localStorage.setItem('access_token', access_token)
          localStorage.setItem('refresh_token', newRefreshToken)

          if (error.config) {
            error.config.headers.Authorization = `Bearer ${access_token}`
            return apiClient.request(error.config)
          }
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
        }
      }
    }

    return Promise.reject(error)
  }
)

function generateCorrelationId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

export default apiClient
