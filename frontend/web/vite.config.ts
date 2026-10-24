import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Gateway port: 8000 matches docker-compose.dev.yml and the gateway Dockerfile.
// Override with VITE_API_PROXY_TARGET if the gateway runs elsewhere.
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/stream': {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      '/security': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/kpi': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})

