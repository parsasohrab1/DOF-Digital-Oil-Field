import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Alerts from './pages/Alerts'
import Wells from './pages/Wells'
import DVR from './pages/DVR'
import ProductionForecast from './pages/ProductionForecast'
import Maintenance from './pages/Maintenance'
import SCADA from './pages/SCADA'
import Well3D from './pages/Well3D'
import ARIntegration from './pages/ARIntegration'
import ReportBuilder from './pages/ReportBuilder'
import SystemArchitecture from './pages/SystemArchitecture'
import './App.css'

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <AuthProvider>
          <Layout>
            <Routes>
              <Route path="/login" element={<Navigate to="/" replace />} />
              <Route path="/" element={<Dashboard />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/wells" element={<Wells />} />
              <Route path="/dvr" element={<DVR />} />
              <Route path="/production-forecast" element={<ProductionForecast />} />
              <Route path="/maintenance" element={<Maintenance />} />
              <Route path="/scada" element={<SCADA />} />
              <Route path="/well3d" element={<Well3D />} />
              <Route path="/ar-integration" element={<ARIntegration />} />
              <Route path="/report-builder" element={<ReportBuilder />} />
              <Route path="/system" element={<SystemArchitecture />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Layout>
        </AuthProvider>
      </Router>
    </QueryClientProvider>
  )
}

export default App
