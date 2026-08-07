import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import apiClient from '../api/client'
import './RemoteOperations.css'

export default function RemoteOperations() {
  const [selectedOperation, setSelectedOperation] = useState<string>('')
  const queryClient = useQueryClient()

  // Setpoint adjustment form
  const [setpointForm, setSetpointForm] = useState({
    well_name: '',
    equipment_id: '',
    parameter_name: 'pressure',
    target_value: 0,
    ramp_rate: null as number | null,
  })

  // Equipment control form
  const [equipmentForm, setEquipmentForm] = useState({
    well_name: '',
    equipment_id: '',
    equipment_type: 'pump',
    operation: 'start',
  })

  // Valve control form
  const [valveForm, setValveForm] = useState({
    well_name: '',
    valve_id: '',
    operation: 'open',
    position: null as number | null,
  })

  // Emergency shutdown form
  const [esdForm, setEsdForm] = useState({
    well_name: '',
    equipment_id: '',
    shutdown_type: 'immediate',
    reason: '',
  })

  // Setpoint adjustment mutation
  const setpointMutation = useMutation({
    mutationFn: async (data: typeof setpointForm) => {
      const response = await apiClient.post('/api/remote-operations/setpoint/adjust', data)
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['operations'] })
      setSelectedOperation(data.operation_id)
      alert('Setpoint adjustment requested successfully')
    },
  })

  // Equipment control mutation
  const equipmentMutation = useMutation({
    mutationFn: async (data: typeof equipmentForm) => {
      const response = await apiClient.post('/api/remote-operations/equipment/control', data)
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['operations'] })
      setSelectedOperation(data.operation_id)
      alert('Equipment control command sent successfully')
    },
  })

  // Valve control mutation
  const valveMutation = useMutation({
    mutationFn: async (data: typeof valveForm) => {
      const response = await apiClient.post('/api/remote-operations/valve/control', data)
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['operations'] })
      setSelectedOperation(data.operation_id)
      alert('Valve control command sent successfully')
    },
  })

  // Emergency shutdown mutation
  const esdMutation = useMutation({
    mutationFn: async (data: typeof esdForm) => {
      const response = await apiClient.post('/api/remote-operations/emergency/shutdown', data)
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['operations'] })
      setSelectedOperation(data.operation_id)
      alert('EMERGENCY SHUTDOWN INITIATED!')
    },
  })

  // Fetch operation status
  const { data: operationStatus } = useQuery({
    queryKey: ['operation-status', selectedOperation],
    queryFn: async () => {
      if (!selectedOperation) return null
      const response = await apiClient.get(`/api/remote-operations/operation/${selectedOperation}/status`)
      return response.data
    },
    enabled: !!selectedOperation,
    refetchInterval: 5000,
  })

  const handleSetpointSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setpointMutation.mutate(setpointForm)
  }

  const handleEquipmentSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (window.confirm(`Are you sure you want to ${equipmentForm.operation} this equipment?`)) {
      equipmentMutation.mutate(equipmentForm)
    }
  }

  const handleValveSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    valveMutation.mutate(valveForm)
  }

  const handleESDSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (window.confirm('⚠️ EMERGENCY SHUTDOWN - This action cannot be undone. Are you absolutely sure?')) {
      esdMutation.mutate(esdForm)
    }
  }

  return (
    <div className="remote-operations">
      <h2>Remote Operations</h2>

      <div className="operations-grid">
        {/* Setpoint Adjustment */}
        <div className="operation-card">
          <h3>Setpoint Adjustment</h3>
          <form onSubmit={handleSetpointSubmit}>
            <div className="form-group">
              <label>Well Name</label>
              <input
                type="text"
                value={setpointForm.well_name}
                onChange={(e) => setSetpointForm({ ...setpointForm, well_name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Equipment ID</label>
              <input
                type="text"
                value={setpointForm.equipment_id}
                onChange={(e) => setSetpointForm({ ...setpointForm, equipment_id: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Parameter</label>
              <select
                value={setpointForm.parameter_name}
                onChange={(e) => setSetpointForm({ ...setpointForm, parameter_name: e.target.value })}
              >
                <option value="pressure">Pressure</option>
                <option value="temperature">Temperature</option>
                <option value="flow_rate">Flow Rate</option>
                <option value="pump_speed">Pump Speed</option>
              </select>
            </div>
            <div className="form-group">
              <label>Target Value</label>
              <input
                type="number"
                step="0.1"
                value={setpointForm.target_value}
                onChange={(e) => setSetpointForm({ ...setpointForm, target_value: parseFloat(e.target.value) })}
                required
              />
            </div>
            <div className="form-group">
              <label>Ramp Rate (optional)</label>
              <input
                type="number"
                step="0.1"
                value={setpointForm.ramp_rate || ''}
                onChange={(e) => setSetpointForm({ ...setpointForm, ramp_rate: e.target.value ? parseFloat(e.target.value) : null })}
              />
            </div>
            <button type="submit" disabled={setpointMutation.isPending}>
              {setpointMutation.isPending ? 'Sending...' : 'Adjust Setpoint'}
            </button>
          </form>
        </div>

        {/* Equipment Control */}
        <div className="operation-card">
          <h3>Equipment Control</h3>
          <form onSubmit={handleEquipmentSubmit}>
            <div className="form-group">
              <label>Well Name</label>
              <input
                type="text"
                value={equipmentForm.well_name}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, well_name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Equipment ID</label>
              <input
                type="text"
                value={equipmentForm.equipment_id}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, equipment_id: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Equipment Type</label>
              <select
                value={equipmentForm.equipment_type}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, equipment_type: e.target.value })}
              >
                <option value="pump">Pump</option>
                <option value="compressor">Compressor</option>
                <option value="motor">Motor</option>
                <option value="valve">Valve</option>
              </select>
            </div>
            <div className="form-group">
              <label>Operation</label>
              <select
                value={equipmentForm.operation}
                onChange={(e) => setEquipmentForm({ ...equipmentForm, operation: e.target.value })}
              >
                <option value="start">Start</option>
                <option value="stop">Stop</option>
                <option value="restart">Restart</option>
              </select>
            </div>
            <button type="submit" disabled={equipmentMutation.isPending}>
              {equipmentMutation.isPending ? 'Sending...' : 'Execute Command'}
            </button>
          </form>
        </div>

        {/* Valve Control */}
        <div className="operation-card">
          <h3>Valve Control</h3>
          <form onSubmit={handleValveSubmit}>
            <div className="form-group">
              <label>Well Name</label>
              <input
                type="text"
                value={valveForm.well_name}
                onChange={(e) => setValveForm({ ...valveForm, well_name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Valve ID</label>
              <input
                type="text"
                value={valveForm.valve_id}
                onChange={(e) => setValveForm({ ...valveForm, valve_id: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label>Operation</label>
              <select
                value={valveForm.operation}
                onChange={(e) => setValveForm({ ...valveForm, operation: e.target.value })}
              >
                <option value="open">Open</option>
                <option value="close">Close</option>
                <option value="set_position">Set Position</option>
              </select>
            </div>
            {valveForm.operation === 'set_position' && (
              <div className="form-group">
                <label>Position (0-100%)</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={valveForm.position || ''}
                  onChange={(e) => setValveForm({ ...valveForm, position: e.target.value ? parseFloat(e.target.value) : null })}
                  required
                />
              </div>
            )}
            <button type="submit" disabled={valveMutation.isPending}>
              {valveMutation.isPending ? 'Sending...' : 'Control Valve'}
            </button>
          </form>
        </div>

        {/* Emergency Shutdown */}
        <div className="operation-card emergency">
          <h3>⚠️ Emergency Shutdown</h3>
          <form onSubmit={handleESDSubmit}>
            <div className="form-group">
              <label>Well Name (optional - leave empty for site-wide)</label>
              <input
                type="text"
                value={esdForm.well_name}
                onChange={(e) => setEsdForm({ ...esdForm, well_name: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Equipment ID (optional)</label>
              <input
                type="text"
                value={esdForm.equipment_id}
                onChange={(e) => setEsdForm({ ...esdForm, equipment_id: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Shutdown Type</label>
              <select
                value={esdForm.shutdown_type}
                onChange={(e) => setEsdForm({ ...esdForm, shutdown_type: e.target.value })}
              >
                <option value="immediate">Immediate</option>
                <option value="controlled">Controlled</option>
                <option value="partial">Partial</option>
              </select>
            </div>
            <div className="form-group">
              <label>Reason *</label>
              <textarea
                value={esdForm.reason}
                onChange={(e) => setEsdForm({ ...esdForm, reason: e.target.value })}
                required
                rows={3}
              />
            </div>
            <button type="submit" className="emergency-button" disabled={esdMutation.isPending}>
              {esdMutation.isPending ? 'Initiating...' : '⚠️ INITIATE EMERGENCY SHUTDOWN'}
            </button>
          </form>
        </div>

        {/* Operation Status */}
        {selectedOperation && operationStatus && (
          <div className="operation-card">
            <h3>Operation Status</h3>
            <div className="status-info">
              <div>Operation ID: {selectedOperation}</div>
              <div>Status: <span className={`status-${operationStatus.status}`}>{operationStatus.status}</span></div>
              <div>Progress: {(operationStatus.progress * 100).toFixed(0)}%</div>
              {operationStatus.current_value !== null && (
                <div>Current Value: {operationStatus.current_value}</div>
              )}
              {operationStatus.target_value !== null && (
                <div>Target Value: {operationStatus.target_value}</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

