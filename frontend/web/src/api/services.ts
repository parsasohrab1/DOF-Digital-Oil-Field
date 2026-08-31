import apiClient from './client'

// Auth API
export const authAPI = {
  login: async (username: string, password: string) => {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)
    
    const response = await apiClient.post('/api/auth/token', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return response.data
  },
  
  getCurrentUser: async () => {
    const response = await apiClient.get('/api/auth/users/me')
    return response.data
  },
  
  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }
}

// Data Ingestion API
export const dataIngestionAPI = {
  getSensorData: async (params?: { limit?: number; well_name?: string }) => {
    try {
      const response = await apiClient.get('/api/data-ingestion/sensor-data', { params })
      return response.data
    } catch (error: any) {
      // Handle network errors gracefully
      if (error.code === 'ERR_NETWORK' || error.code === 'ERR_EMPTY_RESPONSE' || error.message?.includes('Failed to fetch')) {
        // Service is not available, return empty result
        return { records: [] }
      }
      throw error
    }
  },
  
  getConnectors: async () => {
    const response = await apiClient.get('/api/data-ingestion/connectors')
    return response.data
  }
}

// Alert API
export const alertAPI = {
  getAlerts: async (params?: { well_name?: string; status?: string; severity?: string }) => {
    try {
      const response = await apiClient.get('/api/alert/alerts', { params })
      return response.data
    } catch (error: any) {
      // Handle network errors gracefully
      if (error.code === 'ERR_NETWORK' || error.code === 'ERR_EMPTY_RESPONSE' || error.message?.includes('Failed to fetch')) {
        // Service is not available, return empty result
        return { count: 0, alerts: [] }
      }
      throw error
    }
  },
  
  acknowledgeAlert: async (alertId: string, acknowledgedBy: string) => {
    const response = await apiClient.post(`/api/alert/alerts/${alertId}/acknowledge`, {
      acknowledged_by: acknowledgedBy
    })
    return response.data
  },
  
  resolveAlert: async (alertId: string) => {
    const response = await apiClient.post(`/api/alert/alerts/${alertId}/resolve`)
    return response.data
  },
  
  getAlertRules: async () => {
    const response = await apiClient.get('/api/alert/rules')
    return response.data
  },
  
  createWorkOrder: async (alertId: string, erpType: string = 'sap') => {
    const response = await apiClient.post(`/api/alert/alerts/${alertId}/create-work-order`, null, {
      params: { erp_type: erpType }
    })
    return response.data
  },

  getCorrelatedAlerts: async (status: string = 'open', limit: number = 100) => {
    const response = await apiClient.get('/api/alert/alerts/correlations', { params: { status, limit } })
    return response.data
  },

  runRCA: async (alertId: string, lookbackMinutes: number = 60) => {
    const response = await apiClient.post(`/api/alert/alerts/${alertId}/rca`, { lookback_minutes: lookbackMinutes })
    return response.data
  },

  getSmsStatus: async () => {
    const response = await apiClient.get('/api/alert/notifications/sms/status')
    return response.data
  },

  registerSmsPhone: async (payload: {
    phone: string
    label?: string
    enabled?: boolean
    severities?: string[]
  }) => {
    const response = await apiClient.post('/api/alert/notifications/sms/register', payload)
    return response.data
  },

  unregisterSmsPhone: async (phone: string) => {
    const response = await apiClient.post('/api/alert/notifications/sms/unregister', { phone })
    return response.data
  },

  sendTestSms: async (phone?: string, message?: string) => {
    const response = await apiClient.post('/api/alert/notifications/sms/test', {
      phone: phone || undefined,
      message: message || undefined,
    })
    return response.data
  },

  getSmsOutbox: async (limit = 20) => {
    const response = await apiClient.get('/api/alert/notifications/sms/outbox', { params: { limit } })
    return response.data
  },

  sendAlertSms: async (alertId: string) => {
    const response = await apiClient.post(`/api/alert/alerts/${alertId}/sms`)
    return response.data
  },
}

// Tag Catalog API
export const tagCatalogAPI = {
  getTags: async (params?: { well_name?: string; status?: string }) => {
    const response = await apiClient.get('/api/tag-catalog/tags', { params })
    return response.data
  },
  
  getTag: async (tagId: string) => {
    const response = await apiClient.get(`/api/tag-catalog/tags/${tagId}`)
    return response.data
  },
  
  createTag: async (tag: any) => {
    const response = await apiClient.post('/api/tag-catalog/tags', tag)
    return response.data
  },
  
  updateTag: async (tagId: string, tag: any) => {
    const response = await apiClient.put(`/api/tag-catalog/tags/${tagId}`, tag)
    return response.data
  }
}

// Command Control API
export const commandAPI = {
  getCommands: async (params?: { well_name?: string; status?: string }) => {
    const response = await apiClient.get('/api/command-control/commands', { params })
    return response.data
  },
  
  createCommand: async (command: any) => {
    const response = await apiClient.post('/api/command-control/commands', command)
    return response.data
  },
  
  approveCommand: async (commandId: string, approvedBy: string) => {
    const response = await apiClient.post(
      `/api/command-control/commands/${commandId}/approve`,
      { approved_by: approvedBy }
    )
    return response.data
  },
  
  executeCommand: async (commandId: string) => {
    const response = await apiClient.post(`/api/command-control/commands/${commandId}/execute`)
    return response.data
  }
}

// Reporting API
export const reportingAPI = {
  getReports: async (params?: { well_name?: string; limit?: number }) => {
    const response = await apiClient.get('/api/reporting/reports', { params })
    return response.data
  },
  
  generateReport: async (reportRequest: any) => {
    const response = await apiClient.post('/api/reporting/reports/generate', reportRequest)
    return response.data
  },
  
  getReport: async (reportId: string) => {
    const response = await apiClient.get(`/api/reporting/reports/${reportId}`)
    return response.data
  },
  runReportBuilder: async (request: {
    name: string
    well_name?: string
    lookback_hours?: number
    dimensions: string[]
    measures: string[]
    filters?: Record<string, any>
    limit?: number
  }) => {
    const response = await apiClient.post('/api/reporting/reports/builder', request)
    return response.data
  },
  getBIMetadata: async () => {
    const response = await apiClient.get('/api/reporting/bi/metadata')
    return response.data
  },
  getBIConnectors: async () => {
    const response = await apiClient.get('/api/reporting/bi/connectors')
    return response.data
  },
  createWorkflow: async (request: {
    name: string
    description?: string
    schedule_minutes?: number
    steps: Array<{ id: string; type: string; config: Record<string, any>; depends_on?: string[] }>
  }) => {
    const response = await apiClient.post('/api/reporting/workflows', request)
    return response.data
  },
  listWorkflows: async () => {
    const response = await apiClient.get('/api/reporting/workflows')
    return response.data
  },
  runWorkflow: async (workflowId: string, input?: Record<string, any>) => {
    const response = await apiClient.post(`/api/reporting/workflows/${workflowId}/run`, { input: input || {} })
    return response.data
  },
  getWorkflowRuns: async (workflowId: string, limit: number = 20) => {
    const response = await apiClient.get(`/api/reporting/workflows/${workflowId}/runs`, { params: { limit } })
    return response.data
  },
  getWorkflowStepTypes: async () => {
    const response = await apiClient.get('/api/reporting/workflows/visual-builder/step-types')
    return response.data
  },
  getWorkflowTemplates: async () => {
    const response = await apiClient.get('/api/reporting/workflows/templates')
    return response.data
  },
}

// ML Inference API
export const mlAPI = {
  getModels: async () => {
    const response = await apiClient.get('/api/ml-inference/models')
    return response.data
  },
  
  runInference: async (inferenceRequest: any) => {
    const response = await apiClient.post('/api/ml-inference/infer', inferenceRequest)
    return response.data
  },
  
  forecastTimeSeries: async (request: { sensor_id: string; historical_data: number[]; forecast_steps: number }) => {
    const response = await apiClient.post('/api/ml-inference/forecast', request)
    return response
  },
  
  trainLSTMModel: async (request: any) => {
    const response = await apiClient.post('/api/ml-inference/lstm/train', request)
    return response
  },
  
  getLSTMModels: async () => {
    const response = await apiClient.get('/api/ml-inference/lstm/models')
    return response
  },

  getModelVersions: async (modelType: string, limit: number = 20) => {
    const response = await apiClient.get(`/api/ml-inference/models/${modelType}/versions`, { params: { limit } })
    return response.data
  },

  compareModelVersions: async (modelType: string, baselineVersion: string, candidateVersion: string) => {
    const response = await apiClient.post(`/api/ml-inference/models/${modelType}/compare`, {
      baseline_version: baselineVersion,
      candidate_version: candidateVersion,
    })
    return response.data
  },

  getABTestConfig: async (modelType: string) => {
    const response = await apiClient.get(`/api/ml-inference/models/${modelType}/ab-test`)
    return response.data
  },

  configureABTest: async (modelType: string, config: {
    baseline_version: string
    candidate_version: string
    candidate_weight: number
    seed?: number
  }) => {
    const response = await apiClient.post(`/api/ml-inference/models/${modelType}/ab-test`, config)
    return response.data
  },

  setDriftBaseline: async (modelType: string, features: Record<string, number>[]) => {
    // Backend expects a batch of historical samples (List[Dict[str, float]])
    // to compute a mean/stddev baseline -- a single reading isn't a distribution.
    const response = await apiClient.post(`/api/ml-inference/models/${modelType}/drift/baseline`, { features })
    return response.data
  },

  detectDrift: async (modelType: string, features: Record<string, number>[], threshold: number = 2.0) => {
    const response = await apiClient.post(`/api/ml-inference/models/${modelType}/drift/detect`, { features, threshold })
    return response.data
  },
}

// Federated Learning API
export const federatedAPI = {
  getNodes: async () => {
    const response = await apiClient.get('/api/ml-inference/federated/nodes')
    return response.data
  },

  getGlobalModel: async () => {
    const response = await apiClient.get('/api/ml-inference/federated/global-model')
    return response.data
  },

  trainAndSubmit: async (nodeId: string, payload: {
    well_name: string
    location: string
    samples: Record<string, number>[]
    labels: number[]
  }) => {
    const response = await apiClient.post(`/api/ml-inference/federated/nodes/${nodeId}/train-and-submit`, payload)
    return response.data
  },

  aggregate: async (minNodes: number = 2) => {
    const response = await apiClient.post('/api/ml-inference/federated/aggregate', { min_nodes: minNodes })
    return response.data
  },
}

// Storage Optimization API
export const storageAPI = {
  getStorageStats: async () => {
    const response = await apiClient.get('/api/storage-optimization/storage/stats')
    return response.data
  },
  getCompressionStatus: async (tableName: string) => {
    const response = await apiClient.get(`/api/storage-optimization/compression/status/${tableName}`)
    return response.data
  },
  enableCompression: async (request: any) => {
    const response = await apiClient.post('/api/storage-optimization/compression/enable', request)
    return response.data
  },
  compressNow: async (tableName: string, olderThanDays: number) => {
    const response = await apiClient.post('/api/storage-optimization/compression/compress-now', null, {
      params: { table_name: tableName, older_than_days: olderThanDays }
    })
    return response.data
  },
  getChunks: async (tableName: string, limit: number = 100) => {
    const response = await apiClient.get(`/api/storage-optimization/chunks/${tableName}`, {
      params: { limit }
    })
    return response.data
  },
  getClusterStatus: async () => {
    const response = await apiClient.get('/api/storage-optimization/cluster/status')
    return response.data
  }
}

// Digital Twin API
export const digitalTwinAPI = {
  runSimulation: async (simulationRequest: any) => {
    const response = await apiClient.post('/api/digital-twin/simulate', simulationRequest)
    return response.data
  },
  
  getSimulations: async (params?: { well_name?: string }) => {
    const response = await apiClient.get('/api/digital-twin/simulations', { params })
    return response.data
  },
  runWhatIfScenario: async (request: {
    well_name: string
    base_conditions: { flow_rate: number; pressure: number; temperature: number }
    adjustments: { choke_pct?: number; pump_speed_pct?: number; injection_pct?: number }
    horizon_hours?: number
  }) => {
    const response = await apiClient.post('/api/digital-twin/what-if', request)
    return response.data
  },
  getAROverlay: async (wellName: string) => {
    const response = await apiClient.get(`/api/digital-twin/ar/overlay/${wellName}`)
    return response.data
  },
  getBimScene: async (wellName: string) => {
    const response = await apiClient.get(`/api/digital-twin/bim3d/scene/${wellName}`)
    return response.data
  },
}

// DVR API
export const dvrAPI = {
  validate: async (sensorId: string, value: number, timestamp: string) => {
    const response = await apiClient.post('/api/dvr/validate', {
      sensor_id: sensorId,
      value,
      timestamp
    })
    return response.data
  },
  getQualityScores: async () => {
    const response = await apiClient.get('/api/dvr/quality')
    return response.data
  },
  getQualityScore: async (sensorId: string) => {
    const response = await apiClient.get(`/api/dvr/quality/${sensorId}`)
    return response.data
  },
  detectOutliers: async (sensorId: string, method: string = 'zscore') => {
    const response = await apiClient.post('/api/dvr/outliers/detect', {
      sensor_id: sensorId,
      window_size: 100,
      method
    })
    return response.data
  },
  reconcile: async (sensorIds: string[], startTime: string, endTime: string) => {
    const response = await apiClient.post('/api/dvr/reconcile', {
      sensor_ids: sensorIds,
      start_time: startTime,
      end_time: endTime,
      reconciliation_method: 'statistical'
    })
    return response.data
  }
}

// Remote Operations API
export const remoteOpsAPI = {
  adjustSetpoint: async (request: any) => {
    const response = await apiClient.post('/api/remote-operations/setpoint/adjust', request)
    return response.data
  },
  controlEquipment: async (request: any) => {
    const response = await apiClient.post('/api/remote-operations/equipment/control', request)
    return response.data
  },
  controlValve: async (request: any) => {
    const response = await apiClient.post('/api/remote-operations/valve/control', request)
    return response.data
  },
  emergencyShutdown: async (request: any) => {
    const response = await apiClient.post('/api/remote-operations/emergency/shutdown', request)
    return response.data
  },
  getOperationStatus: async (operationId: string) => {
    const response = await apiClient.get(`/api/remote-operations/operation/${operationId}/status`)
    return response.data
  }
}

// Data Variables API
export const dataVariablesAPI = {
  getVariables: async () => {
    try {
      const response = await apiClient.get('/api/data-variables')
      return response.data
    } catch (error: any) {
      // Handle network errors gracefully
      if (error.code === 'ERR_NETWORK' || error.code === 'ERR_EMPTY_RESPONSE' || error.message?.includes('Failed to fetch') || error.isNetworkError) {
        // Service is not available, return empty array
        return []
      }
      throw error
    }
  },
  getVariableData: async (variableName: string, params?: any) => {
    try {
      const response = await apiClient.get(`/api/data-variables/${variableName}/data`, { params })
      return response.data
    } catch (error: any) {
      // Handle network errors gracefully
      if (error.code === 'ERR_NETWORK' || error.code === 'ERR_EMPTY_RESPONSE' || error.message?.includes('Failed to fetch') || error.isNetworkError) {
        // Service is not available, return empty data
        return { data: [], timestamps: [] }
      }
      throw error
    }
  },
  getVariablesByCategory: async (category: string) => {
    try {
      const response = await apiClient.get(`/api/data-variables/category/${category}`)
      return response.data
    } catch (error: any) {
      // Handle network errors gracefully
      if (error.code === 'ERR_NETWORK' || error.code === 'ERR_EMPTY_RESPONSE' || error.message?.includes('Failed to fetch') || error.isNetworkError) {
        // Service is not available, return empty array
        return []
      }
      throw error
    }
  }
}

// Maintenance API
export const maintenanceAPI = {
  getRULPredictions: async () => {
    const response = await apiClient.get('/api/ml-inference/rul/predictions')
    return response.data
  },
  predictRUL: async (equipmentType: string, equipmentId: string, features: any) => {
    const response = await apiClient.post('/api/ml-inference/rul/predict', {
      equipment_type: equipmentType,
      equipment_id: equipmentId,
      features
    })
    return response.data
  },
  getMaintenanceSchedule: async () => {
    const response = await apiClient.get('/api/maintenance/schedule')
    return response.data
  },
  getSpareParts: async () => {
    const response = await apiClient.get('/api/maintenance/spare-parts')
    return response.data
  }
}

// SCADA API
export const scadaAPI = {
  getConnections: async () => {
    const response = await apiClient.get('/api/scada/connections')
    return response.data
  },
  connect: async (connectionId: string) => {
    const response = await apiClient.post(`/api/scada/connections/${connectionId}/connect`)
    return response.data
  },
  disconnect: async (connectionId: string) => {
    const response = await apiClient.post(`/api/scada/connections/${connectionId}/disconnect`)
    return response.data
  },
  getOPCUANodes: async () => {
    const response = await apiClient.get('/api/data-ingestion/opcua/nodes')
    return response.data
  }
}

// Well 3D API
export const well3DAPI = {
  getWellData: async (wellName: string) => {
    try {
      const response = await apiClient.get(`/api/digital-twin/well/${wellName}/3d`)
      return response.data
    } catch (error: any) {
      // Handle network errors gracefully
      if (error.code === 'ERR_NETWORK' || error.code === 'ERR_EMPTY_RESPONSE' || error.message?.includes('Failed to fetch') || error.isNetworkError) {
        // Service is not available, return null to use mock data
        return null
      }
      // For other errors, also return null
      return null
    }
  },
  getWells: async () => {
    try {
      const response = await apiClient.get('/api/digital-twin/wells')
      const data = response.data
      const list = Array.isArray(data) ? data : data?.wells
      if (Array.isArray(list) && list.length >= 8) return list
      // Fallback / enrich: میدان دهلران — ۱۶ حلقه
      return Array.from({ length: 16 }, (_, i) => `DEH-${String(i + 1).padStart(2, '0')}`)
    } catch (error: any) {
      if (error.code === 'ERR_NETWORK' || error.code === 'ERR_EMPTY_RESPONSE' || error.message?.includes('Failed to fetch') || error.isNetworkError) {
        return Array.from({ length: 16 }, (_, i) => `DEH-${String(i + 1).padStart(2, '0')}`)
      }
      return Array.from({ length: 16 }, (_, i) => `DEH-${String(i + 1).padStart(2, '0')}`)
    }
  }
}

// Security API (via API Gateway)
export const securityAPI = {
  getSiemEvents: async (limit: number = 50, severity?: string) => {
    const response = await apiClient.get('/security/siem/events', { params: { limit, severity } })
    return response.data
  },
  getThreatStatus: async () => {
    const response = await apiClient.get('/security/threat/status')
    return response.data
  },
}

export const kpiAPI = {
  getSummary: async () => {
    const response = await apiClient.get('/kpi/summary')
    return response.data
  },
  getCacheStats: async () => {
    const response = await apiClient.get('/kpi/cache-stats')
    return response.data
  },
  recordFeatureUsage: async (feature: string) => {
    const response = await apiClient.post('/kpi/feature-usage', { feature })
    return response.data
  },
}

export default {
  auth: authAPI,
  dataIngestion: dataIngestionAPI,
  alerts: alertAPI,
  tags: tagCatalogAPI,
  commands: commandAPI,
  reports: reportingAPI,
  ml: mlAPI,
  federated: federatedAPI,
  digitalTwin: digitalTwinAPI,
  dvr: dvrAPI,
  remoteOps: remoteOpsAPI,
  dataVariables: dataVariablesAPI,
  maintenance: maintenanceAPI,
  scada: scadaAPI,
  storage: storageAPI,
}

