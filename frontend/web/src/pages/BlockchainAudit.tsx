import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts'
import './BlockchainAudit.css'

interface AuditLog {
  logId: string
  timestamp: string
  commandType: 'control' | 'maintenance' | 'safety' | 'configuration'
  command: string
  operator: string
  wellName: string
  status: 'approved' | 'pending' | 'rejected'
  blockHash: string
  previousHash: string
  transactionId: string
  verified: boolean
}

interface Block {
  blockNumber: number
  timestamp: string
  hash: string
  previousHash: string
  transactions: number
  verified: boolean
  miner: string
}

export default function BlockchainAudit() {
  const [selectedLog, setSelectedLog] = useState<string | null>(null)
  const [filterType, setFilterType] = useState<string>('all')

  // Mock data for audit logs
  const { data: auditLogs = [] } = useQuery({
    queryKey: ['blockchain-audit-logs', filterType],
    queryFn: async () => {
      await new Promise(resolve => setTimeout(resolve, 500))
      const allLogs: AuditLog[] = [
        {
          logId: 'LOG-001',
          timestamp: '2024-01-15 10:30:25',
          commandType: 'control',
          command: 'Open Master Valve',
          operator: 'John Smith',
          wellName: 'PROD-001',
          status: 'approved',
          blockHash: '0x7a3f9b2c...',
          previousHash: '0x5e8d1a4f...',
          transactionId: '0x9c2e5f8a...',
          verified: true
        },
        {
          logId: 'LOG-002',
          timestamp: '2024-01-15 10:28:15',
          commandType: 'safety',
          command: 'Emergency Shutdown',
          operator: 'Sarah Johnson',
          wellName: 'PROD-002',
          status: 'approved',
          blockHash: '0x8b4e1c7d...',
          previousHash: '0x7a3f9b2c...',
          transactionId: '0x3f7a9e2b...',
          verified: true
        },
        {
          logId: 'LOG-003',
          timestamp: '2024-01-15 10:25:42',
          commandType: 'maintenance',
          command: 'Schedule Pump Maintenance',
          operator: 'Mike Davis',
          wellName: 'DEV-001',
          status: 'pending',
          blockHash: '0x6d2a8f4e...',
          previousHash: '0x8b4e1c7d...',
          transactionId: '0x1a5c8d3f...',
          verified: false
        },
        {
          logId: 'LOG-004',
          timestamp: '2024-01-15 10:22:18',
          commandType: 'configuration',
          command: 'Update Pressure Threshold',
          operator: 'John Smith',
          wellName: 'PROD-001',
          status: 'approved',
          blockHash: '0x4f9a2e6c...',
          previousHash: '0x6d2a8f4e...',
          transactionId: '0x7b3e9f1a...',
          verified: true
        },
        {
          logId: 'LOG-005',
          timestamp: '2024-01-15 10:20:05',
          commandType: 'control',
          command: 'Adjust Choke Valve',
          operator: 'Sarah Johnson',
          wellName: 'OBS-001',
          status: 'rejected',
          blockHash: '0x3e8c5f2a...',
          previousHash: '0x4f9a2e6c...',
          transactionId: '0x2d7a4e9c...',
          verified: true
        }
      ]
      
      if (filterType === 'all') return allLogs
      return allLogs.filter(log => log.commandType === filterType)
    },
    refetchInterval: 10000
  })

  // Mock data for blockchain blocks
  const { data: blocks = [] } = useQuery({
    queryKey: ['blockchain-blocks'],
    queryFn: async () => {
      await new Promise(resolve => setTimeout(resolve, 500))
      return Array.from({ length: 10 }, (_, i) => ({
        blockNumber: 1000 + i,
        timestamp: new Date(Date.now() - i * 60000).toISOString(),
        hash: `0x${Math.random().toString(16).substr(2, 16)}...`,
        previousHash: i > 0 ? `0x${Math.random().toString(16).substr(2, 16)}...` : '0x0000...',
        transactions: Math.floor(Math.random() * 5) + 1,
        verified: true,
        miner: `Node-${Math.floor(Math.random() * 5) + 1}`
      })) as Block[]
    },
    refetchInterval: 10000
  })

  // Mock statistics
  const stats = {
    totalLogs: auditLogs.length,
    approved: auditLogs.filter(l => l.status === 'approved').length,
    pending: auditLogs.filter(l => l.status === 'pending').length,
    rejected: auditLogs.filter(l => l.status === 'rejected').length,
    verified: auditLogs.filter(l => l.verified).length,
    totalBlocks: blocks.length,
    totalTransactions: blocks.reduce((sum, b) => sum + b.transactions, 0)
  }

  // Mock activity chart data
  const activityData = Array.from({ length: 24 }, (_, i) => ({
    hour: i,
    commands: Math.floor(Math.random() * 10) + 1,
    verified: Math.floor(Math.random() * 8) + 1
  }))

  const selectedLogData = auditLogs.find(l => l.logId === selectedLog)

  return (
    <div className="blockchain-audit-page">
      <div className="page-header">
        <h1>Blockchain Audit Log</h1>
        <p>Immutable distributed ledger for command & control security</p>
      </div>

      <div className="audit-stats-grid">
        <div className="stat-card">
          <h3>Total Audit Logs</h3>
          <div className="stat-value">{stats.totalLogs}</div>
          <div className="stat-label">All Commands</div>
        </div>
        <div className="stat-card">
          <h3>Verified Logs</h3>
          <div className="stat-value">{stats.verified}</div>
          <div className="stat-label">{((stats.verified / stats.totalLogs) * 100 || 0).toFixed(1)}% verified</div>
        </div>
        <div className="stat-card">
          <h3>Blockchain Blocks</h3>
          <div className="stat-value">{stats.totalBlocks}</div>
          <div className="stat-label">{stats.totalTransactions} transactions</div>
        </div>
        <div className="stat-card">
          <h3>Security Status</h3>
          <div className="stat-value">100%</div>
          <div className="stat-label">No tampering detected</div>
        </div>
      </div>

      <div className="audit-content-grid">
        <div className="logs-section">
          <div className="section-header">
            <h2>Audit Logs</h2>
            <div className="filter-controls">
              <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
                <option value="all">All Types</option>
                <option value="control">Control</option>
                <option value="maintenance">Maintenance</option>
                <option value="safety">Safety</option>
                <option value="configuration">Configuration</option>
              </select>
            </div>
          </div>
          <div className="logs-list">
            {auditLogs.map(log => (
              <div
                key={log.logId}
                className={`log-card ${log.status} ${selectedLog === log.logId ? 'selected' : ''}`}
                onClick={() => setSelectedLog(log.logId)}
              >
                <div className="log-header">
                  <span className="log-id">{log.logId}</span>
                  <span className={`status-badge ${log.status}`}>{log.status}</span>
                  {log.verified && <span className="verified-badge">✓ Verified</span>}
                </div>
                <div className="log-info">
                  <p><strong>Command:</strong> {log.command}</p>
                  <p><strong>Type:</strong> {log.commandType}</p>
                  <p><strong>Operator:</strong> {log.operator}</p>
                  <p><strong>Well:</strong> {log.wellName}</p>
                  <p><strong>Time:</strong> {log.timestamp}</p>
                </div>
                <div className="log-hash">
                  <p><strong>Block Hash:</strong> <code>{log.blockHash}</code></p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="details-section">
          <h2>Log Details</h2>
          {selectedLogData ? (
            <div className="log-details">
              <div className="detail-group">
                <h3>Command Information</h3>
                <div className="detail-info">
                  <p><strong>Log ID:</strong> {selectedLogData.logId}</p>
                  <p><strong>Command:</strong> {selectedLogData.command}</p>
                  <p><strong>Type:</strong> {selectedLogData.commandType}</p>
                  <p><strong>Operator:</strong> {selectedLogData.operator}</p>
                  <p><strong>Well:</strong> {selectedLogData.wellName}</p>
                  <p><strong>Status:</strong> <span className={`status-badge ${selectedLogData.status}`}>{selectedLogData.status}</span></p>
                  <p><strong>Timestamp:</strong> {selectedLogData.timestamp}</p>
                </div>
              </div>

              <div className="detail-group">
                <h3>Blockchain Information</h3>
                <div className="detail-info">
                  <p><strong>Transaction ID:</strong> <code>{selectedLogData.transactionId}</code></p>
                  <p><strong>Block Hash:</strong> <code>{selectedLogData.blockHash}</code></p>
                  <p><strong>Previous Hash:</strong> <code>{selectedLogData.previousHash}</code></p>
                  <p><strong>Verified:</strong> {selectedLogData.verified ? '✓ Yes' : '✗ No'}</p>
                </div>
              </div>

              <div className="detail-group">
                <h3>Security Verification</h3>
                <div className="verification-status">
                  {selectedLogData.verified ? (
                    <div className="verified">
                      <span className="check-icon">✓</span>
                      <div>
                        <h4>Verified & Immutable</h4>
                        <p>This log entry has been verified and cannot be tampered with</p>
                      </div>
                    </div>
                  ) : (
                    <div className="pending">
                      <span className="pending-icon">⏳</span>
                      <div>
                        <h4>Pending Verification</h4>
                        <p>This log entry is awaiting blockchain verification</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="no-selection">
              <p>Select a log entry to view details</p>
            </div>
          )}
        </div>
      </div>

      <div className="blockchain-section">
        <h2>Blockchain Blocks</h2>
        <div className="blocks-list">
          {blocks.map(block => (
            <div key={block.blockNumber} className="block-card">
              <div className="block-header">
                <span className="block-number">Block #{block.blockNumber}</span>
                <span className={`block-status ${block.verified ? 'verified' : 'pending'}`}>
                  {block.verified ? '✓ Verified' : '⏳ Pending'}
                </span>
              </div>
              <div className="block-info">
                <p><strong>Hash:</strong> <code>{block.hash}</code></p>
                <p><strong>Previous Hash:</strong> <code>{block.previousHash}</code></p>
                <p><strong>Transactions:</strong> {block.transactions}</p>
                <p><strong>Miner:</strong> {block.miner}</p>
                <p><strong>Timestamp:</strong> {new Date(block.timestamp).toLocaleString()}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="activity-chart-section">
        <h2>Activity Over Time (24h)</h2>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={activityData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="commands" fill="#3498db" name="Commands" />
              <Bar dataKey="verified" fill="#27ae60" name="Verified" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

