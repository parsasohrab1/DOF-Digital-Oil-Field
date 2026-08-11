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
import MLModels from './pages/MLModels'
import LSTMForecast from './pages/LSTMForecast'
import FederatedLearning from './pages/FederatedLearning'
import Performance from './pages/Performance'
import SecurityCenter from './pages/SecurityCenter'
import RemoteOperations from './pages/RemoteOperations'
import Reports from './pages/Reports'
import WorkflowAutomation from './pages/WorkflowAutomation'
import StorageOptimization from './pages/StorageOptimization'
import EdgeComputing from './pages/EdgeComputing'
import DataVariables from './pages/DataVariables'
import BlockchainAudit from './pages/BlockchainAudit'
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
              <Route path="/ml-models" element={<MLModels />} />
              <Route path="/lstm-forecast" element={<LSTMForecast />} />
              <Route path="/federated-learning" element={<FederatedLearning />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/soc" element={<SecurityCenter />} />
              <Route path="/remote-operations" element={<RemoteOperations />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/workflow-automation" element={<WorkflowAutomation />} />
              <Route path="/storage-optimization" element={<StorageOptimization />} />
              <Route path="/edge-computing" element={<EdgeComputing />} />
              <Route path="/data-variables" element={<DataVariables />} />
              <Route path="/blockchain-audit" element={<BlockchainAudit />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Layout>
        </AuthProvider>
      </Router>
    </QueryClientProvider>
  )
}

export default App
