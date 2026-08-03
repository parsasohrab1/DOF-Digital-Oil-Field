import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuth } from '../hooks/useAuth'
import { alertAPI } from '../api/services'
import { transportLabelFa } from '../api/offlineMode'
import {
  buildAlertSmsText,
  getDehloranAlerts,
  getLocalSmsStatus,
  loadLocalSmsOutbox,
  pushLocalSms,
  saveLocalSmsRecipient,
  type DehloranAlert,
} from '../data/dehloranAlerts'
import './Alerts.css'

type Tab = 'all' | 'correlated' | 'sms'

const SMS_PHONE_KEY = 'sogf_sms_alert_phone'

function getMeta(alert: any): Record<string, any> {
  return alert.metadata_json || alert.metadata || {}
}

function normalizePhoneInput(raw: string) {
  return raw.replace(/[^\d+]/g, '').trim()
}

function severityFa(s: string) {
  if (s === 'critical') return 'بحرانی'
  if (s === 'warning') return 'هشدار'
  if (s === 'info') return 'اطلاع'
  return s
}

function statusFa(s: string) {
  if (s === 'open') return 'باز'
  if (s === 'acknowledged') return 'تأییدشده'
  if (s === 'resolved') return 'رفع‌شده'
  return s
}

function resolvePhone(phone: string) {
  const normalized = normalizePhoneInput(phone)
  if (normalized) return normalized
  return normalizePhoneInput(localStorage.getItem(SMS_PHONE_KEY) || '')
}

export default function Alerts() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('all')
  const [rcaResults, setRcaResults] = useState<Record<string, any>>({})
  const [phone, setPhone] = useState(() => localStorage.getItem(SMS_PHONE_KEY) || '')
  const [smsLabel, setSmsLabel] = useState('اپراتور میدان دهلران')
  const [smsMsg, setSmsMsg] = useState<string | null>(null)
  const [smsErr, setSmsErr] = useState<string | null>(null)

  const { transport } = useWebSocket({
    onSnapshot: (payload) => {
      if (payload.data.alerts) {
        queryClient.setQueryData(['alerts'], payload.data.alerts)
      }
    },
  })

  const { data: alertsResponse, isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: async () => {
      try {
        const data = await alertAPI.getAlerts()
        const list = data?.alerts || data || []
        if (Array.isArray(list) && list.length > 0) {
          return { count: list.length, alerts: list, source: 'api' as const }
        }
      } catch {
        /* fallback below */
      }
      const alerts = getDehloranAlerts()
      return { count: alerts.length, alerts, source: 'dehloran' as const }
    },
    refetchInterval: 15000,
    retry: false,
  })

  const { data: correlationsData, isLoading: correlationsLoading } = useQuery({
    queryKey: ['alert-correlations'],
    queryFn: async () => {
      try {
        return await alertAPI.getCorrelatedAlerts('open')
      } catch {
        const alerts = getDehloranAlerts().filter((a) => a.severity !== 'info')
        const byWell: Record<string, DehloranAlert[]> = {}
        for (const a of alerts) {
          ;(byWell[a.well_name] ||= []).push(a)
        }
        const groups = Object.entries(byWell)
          .filter(([, items]) => items.length >= 2)
          .map(([well, items]) => ({
            correlation_id: `CORR-${well}`,
            well_name: well,
            count: items.length,
            max_severity: items.some((i) => i.severity === 'critical') ? 'critical' : 'warning',
            suppressed_total: 0,
            alerts: items.map((i) => i.alert_id),
          }))
        return { groups }
      }
    },
    enabled: tab === 'correlated',
    refetchInterval: 15000,
  })

  const { data: smsStatus, refetch: refetchSms } = useQuery({
    queryKey: ['sms-status'],
    queryFn: async () => {
      try {
        return await alertAPI.getSmsStatus()
      } catch {
        return getLocalSmsStatus(phone)
      }
    },
    retry: false,
    refetchInterval: 30000,
  })

  const { data: smsOutbox, refetch: refetchOutbox } = useQuery({
    queryKey: ['sms-outbox'],
    queryFn: async () => {
      try {
        const data = await alertAPI.getSmsOutbox(12)
        if ((data?.messages || []).length > 0) return data
      } catch {
        /* local */
      }
      const messages = loadLocalSmsOutbox()
      return { messages, count: messages.length }
    },
    retry: false,
  })

  useEffect(() => {
    const registered = smsStatus?.recipients?.[0]?.phone_display || smsStatus?.recipients?.[0]?.phone
    if (registered && !phone) setPhone(registered)
  }, [smsStatus, phone])

  const acknowledgeMutation = useMutation({
    mutationFn: ({ alertId, username }: { alertId: string; username: string }) =>
      alertAPI.acknowledgeAlert(alertId, username),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  })

  const resolveMutation = useMutation({
    mutationFn: (alertId: string) => alertAPI.resolveAlert(alertId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alert-correlations'] })
    },
  })

  const createWorkOrderMutation = useMutation({
    mutationFn: ({ alertId, erpType }: { alertId: string; erpType?: string }) =>
      alertAPI.createWorkOrder(alertId, erpType || 'sap'),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      alert(`دستور کار ایجاد شد: ${data.work_order_id}`)
    },
    onError: (error: any) => {
      alert(`ایجاد دستور کار ناموفق: ${error.response?.data?.detail || error.message}`)
    },
  })

  const rcaMutation = useMutation({
    mutationFn: (alertId: string) => alertAPI.runRCA(alertId, 60),
    onSuccess: (data) => {
      setRcaResults((prev) => ({ ...prev, [data.alert_id]: data.rca }))
    },
  })

  const registerSmsMutation = useMutation({
    mutationFn: async () => {
      const p = resolvePhone(phone)
      if (!p) throw new Error('شماره موبایل را وارد کنید')
      try {
        return await alertAPI.registerSmsPhone({
          phone: p,
          label: smsLabel,
          enabled: true,
          severities: ['critical', 'warning'],
        })
      } catch {
        saveLocalSmsRecipient(p, smsLabel)
        return { message: 'شماره به‌صورت محلی ثبت شد (آماده ارسال پیامک هشدار)' }
      }
    },
    onSuccess: (data) => {
      localStorage.setItem(SMS_PHONE_KEY, resolvePhone(phone))
      setSmsErr(null)
      setSmsMsg(data.message || 'شماره ثبت شد')
      refetchSms()
    },
    onError: (error: any) => {
      setSmsMsg(null)
      setSmsErr(error.response?.data?.detail || error.message || 'خطا در ثبت شماره')
    },
  })

  const testSmsMutation = useMutation({
    mutationFn: async () => {
      const p = resolvePhone(phone)
      if (!p) throw new Error('ابتدا شماره موبایل را وارد/ثبت کنید')
      try {
        return await alertAPI.sendTestSms(p)
      } catch {
        const entry = pushLocalSms(
          p,
          `هوشمندسازی میادین — پیامک آزمایشی\nمیدان دهلران\nزمان: ${new Date().toLocaleString('fa-IR')}`,
          { type: 'test' }
        )
        return { entry, message: 'پیامک آزمایشی در صف محلی قرار گرفت' }
      }
    },
    onSuccess: (data) => {
      const st = data.entry?.result?.status || 'queued'
      setSmsErr(null)
      setSmsMsg(
        st === 'sent'
          ? 'پیامک آزمایشی ارسال شد'
          : `پیامک آزمایشی در صف قرار گرفت (${data.entry?.effective_provider || 'local-mock'})`
      )
      refetchOutbox()
      refetchSms()
    },
    onError: (error: any) => {
      setSmsMsg(null)
      setSmsErr(error.response?.data?.detail || error.message || 'ارسال آزمایشی ناموفق')
    },
  })

  const alertSmsMutation = useMutation({
    mutationFn: async (alertItem: any) => {
      const p = resolvePhone(phone)
      if (!p) throw new Error('ابتدا شماره موبایل را ثبت کنید')
      try {
        return await alertAPI.sendAlertSms(alertItem.alert_id)
      } catch {
        const text = buildAlertSmsText(alertItem)
        const entry = pushLocalSms(p, text, {
          type: 'alert',
          alert_id: alertItem.alert_id,
          severity: alertItem.severity,
        })
        return { entry, sent: 1, local: true }
      }
    },
    onSuccess: () => {
      setSmsErr(null)
      setSmsMsg('پیامک هشدار ارسال/صف‌بندی شد — متن در بخش «آخرین پیامک‌ها» قابل مشاهده است')
      refetchOutbox()
      setTab('sms')
    },
    onError: (error: any) => {
      setSmsMsg(null)
      setSmsErr(error.response?.data?.detail || error.message || 'ارسال پیامک هشدار ناموفق')
    },
  })

  const bulkCriticalSmsMutation = useMutation({
    mutationFn: async () => {
      const p = resolvePhone(phone)
      if (!p) throw new Error('ابتدا شماره موبایل را ثبت کنید')
      const criticals = (alertsResponse?.alerts || []).filter(
        (a: any) => a.severity === 'critical' && a.status === 'open'
      )
      if (criticals.length === 0) throw new Error('هشدار بحرانی بازی برای ارسال وجود ندارد')
      let sent = 0
      for (const a of criticals.slice(0, 8)) {
        try {
          await alertAPI.sendAlertSms(a.alert_id)
          sent += 1
        } catch {
          pushLocalSms(p, buildAlertSmsText(a), { type: 'alert', alert_id: a.alert_id })
          sent += 1
        }
      }
      return { sent, total: criticals.length }
    },
    onSuccess: (data) => {
      setSmsErr(null)
      setSmsMsg(`${data.sent} پیامک هشدار بحرانی در صف قرار گرفت`)
      refetchOutbox()
      setTab('sms')
    },
    onError: (error: any) => {
      setSmsMsg(null)
      setSmsErr(error.message || 'ارسال گروهی ناموفق')
    },
  })

  const handleAcknowledge = (alertId: string) => {
    if (!user) return
    acknowledgeMutation.mutate({ alertId, username: user.username })
  }

  const handleResolve = (alertId: string) => resolveMutation.mutate(alertId)

  const handleCreateWorkOrder = (alertId: string) => {
    if (window.confirm('برای این هشدار دستور کار ایجاد شود؟')) {
      createWorkOrderMutation.mutate({ alertId })
    }
  }

  const alerts = alertsResponse?.alerts || []
  const groups = correlationsData?.groups || []
  const criticalOpen = alerts.filter((a: any) => a.severity === 'critical' && a.status === 'open')
  const warningOpen = alerts.filter((a: any) => a.severity === 'warning' && a.status === 'open')

  if (isLoading) return <div className="loading">در حال بارگذاری هشدارها…</div>

  const smsPanel = (
    <section className="sms-panel">
      <div className="sms-panel-head">
        <div>
          <h3>ارسال پیامک هشدار</h3>
          <p>
            شماره موبایل اپراتور را ثبت کنید، سپس از لیست هشدارها دکمه «ارسال پیامک» را بزنید یا همه
            هشدارهای بحرانی را یکجا ارسال کنید.
          </p>
        </div>
        {smsStatus && (
          <div className="sms-provider-badge">
            <span>{smsStatus.provider}</span>
            <small>{smsStatus.detail}</small>
          </div>
        )}
      </div>

      <div className="sms-stats">
        <span className="sms-stat critical">{criticalOpen.length} بحرانی</span>
        <span className="sms-stat warning">{warningOpen.length} هشدار</span>
        <span className="sms-stat">{alerts.length} کل</span>
      </div>

      <div className="sms-form">
        <label>
          شماره موبایل
          <input
            type="tel"
            inputMode="tel"
            placeholder="09121234567"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            dir="ltr"
          />
        </label>
        <label>
          برچسب
          <input
            type="text"
            value={smsLabel}
            onChange={(e) => setSmsLabel(e.target.value)}
            placeholder="اپراتور میدان"
          />
        </label>
        <div className="sms-actions">
          <button
            type="button"
            className="sms-primary"
            disabled={!phone.trim() || registerSmsMutation.isPending}
            onClick={() => registerSmsMutation.mutate()}
          >
            {registerSmsMutation.isPending ? 'در حال ثبت…' : 'ثبت شماره'}
          </button>
          <button
            type="button"
            disabled={testSmsMutation.isPending}
            onClick={() => testSmsMutation.mutate()}
          >
            {testSmsMutation.isPending ? 'ارسال…' : 'پیامک آزمایشی'}
          </button>
          <button
            type="button"
            className="sms-bulk"
            disabled={bulkCriticalSmsMutation.isPending || criticalOpen.length === 0}
            onClick={() => bulkCriticalSmsMutation.mutate()}
          >
            {bulkCriticalSmsMutation.isPending
              ? 'در حال ارسال…'
              : `ارسال پیامک همه بحرانی‌ها (${criticalOpen.length})`}
          </button>
        </div>
      </div>

      {(smsMsg || smsErr) && (
        <p className={smsErr ? 'sms-feedback err' : 'sms-feedback ok'}>{smsErr || smsMsg}</p>
      )}

      {smsStatus?.recipients?.length > 0 && (
        <div className="sms-recipients">
          <strong>شماره‌های ثبت‌شده:</strong>
          <ul>
            {smsStatus.recipients.map((r: any) => (
              <li key={r.phone}>
                <span dir="ltr">{r.phone_display || r.phone}</span>
                <em>{r.label}</em>
                <small>{(r.severities || []).map((s: string) => severityFa(s)).join('، ')}</small>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(smsOutbox?.messages?.length || 0) > 0 && (
        <div className="sms-outbox">
          <strong>آخرین پیامک‌ها</strong>
          <ul>
            {smsOutbox.messages.slice(0, 8).map((m: any) => (
              <li key={m.id}>
                <span dir="ltr">{m.phone_display || m.phone}</span>
                <em>{m.result?.status || m.effective_provider}</em>
                <p>{m.message}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )

  return (
    <div className="alerts-page" dir="rtl">
      <div className="alerts-toolbar">
        <h2>هشدارها</h2>
        <div className="alerts-toolbar-right">
          <span className={`transport-badge ${transport}`}>
            {transportLabelFa(transport)}
          </span>
          <div className="tab-buttons">
            <button className={tab === 'all' ? 'active' : ''} onClick={() => setTab('all')}>
              همه هشدارها ({alerts.length})
            </button>
            <button
              className={tab === 'sms' ? 'active' : ''}
              onClick={() => setTab('sms')}
            >
              ارسال پیامک
            </button>
            <button
              className={tab === 'correlated' ? 'active' : ''}
              onClick={() => setTab('correlated')}
            >
              گروه‌های همبسته
            </button>
          </div>
        </div>
      </div>

      {(tab === 'sms' || tab === 'all') && smsPanel}

      {tab === 'sms' ? (
        <div className="sms-alert-pick">
          <h3>هشدارهای قابل ارسال با پیامک</h3>
          <p className="sms-pick-hint">
            روی هر هشدار «ارسال پیامک» را بزنید. اولویت با موارد بحرانی و هشدار است.
          </p>
          <div className="alerts-list">
            {alerts
              .filter((a: any) => a.severity === 'critical' || a.severity === 'warning')
              .map((alertItem: any) => (
                <div key={alertItem.alert_id} className={`alert-card ${alertItem.severity}`}>
                  <div className="alert-header">
                    <span className="alert-id">{alertItem.alert_id}</span>
                    <span className={`alert-severity ${alertItem.severity}`}>
                      {severityFa(alertItem.severity)}
                    </span>
                  </div>
                  <div className="alert-body">
                    <p>
                      <strong>چاه / محل:</strong> {alertItem.well_name}
                    </p>
                    <p>
                      <strong>پیام:</strong> {alertItem.message}
                    </p>
                    <p className="sms-preview">
                      <strong>پیش‌نمایش پیامک:</strong>
                      <span>{buildAlertSmsText(alertItem)}</span>
                    </p>
                    <div className="alert-actions">
                      <button
                        className="sms-btn sms-primary"
                        onClick={() => alertSmsMutation.mutate(alertItem)}
                        disabled={alertSmsMutation.isPending}
                      >
                        {alertSmsMutation.isPending ? 'ارسال…' : 'ارسال پیامک این هشدار'}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
          </div>
        </div>
      ) : tab === 'correlated' ? (
        <div className="correlation-groups">
          {correlationsLoading ? (
            <p>در حال بارگذاری همبستگی‌ها…</p>
          ) : groups.length === 0 ? (
            <div className="no-alerts">
              <p>گروه هشدار همبسته‌ای یافت نشد.</p>
            </div>
          ) : (
            groups.map((group: any) => (
              <div key={group.correlation_id} className={`alert-card ${group.max_severity}`}>
                <div className="alert-header">
                  <span className="alert-id">{group.correlation_id}</span>
                  <span className={`alert-severity ${group.max_severity}`}>
                    {severityFa(group.max_severity)}
                  </span>
                </div>
                <div className="alert-body">
                  <p>
                    <strong>چاه:</strong> {group.well_name}
                  </p>
                  <p>
                    <strong>تعداد هشدار در گروه:</strong> {group.count}
                  </p>
                  <p>
                    <strong>سرکوب‌شده (خستگی هشدار):</strong> {group.suppressed_total}
                  </p>
                  <p>
                    <strong>شناسه هشدارها:</strong> {group.alerts.join(', ')}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        <>
          {alerts.length === 0 && (
            <div className="no-alerts">
              <p>هشداری یافت نشد. همه سامانه‌ها در وضعیت عادی هستند.</p>
            </div>
          )}
          <div className="alerts-list">
            {alerts.map((alertItem: any) => {
              const meta = getMeta(alertItem)
              const rca = rcaResults[alertItem.alert_id] || meta.rca
              const suppressed = meta.suppressed_count || 0

              return (
                <div key={alertItem.alert_id} className={`alert-card ${alertItem.severity}`}>
                  <div className="alert-header">
                    <span className="alert-id">{alertItem.alert_id}</span>
                    <span className={`alert-severity ${alertItem.severity}`}>
                      {severityFa(alertItem.severity)}
                    </span>
                  </div>
                  <div className="alert-body">
                    <p>
                      <strong>چاه:</strong> {alertItem.well_name}
                    </p>
                    <p>
                      <strong>پیام:</strong> {alertItem.message}
                    </p>
                    <p>
                      <strong>وضعیت:</strong> {statusFa(alertItem.status)}
                    </p>
                    <p>
                      <strong>زمان:</strong> {new Date(alertItem.timestamp).toLocaleString('fa-IR')}
                    </p>
                    {meta.correlation_id && (
                      <p>
                        <strong>همبستگی:</strong> {meta.correlation_id}
                      </p>
                    )}
                    {suppressed > 0 && (
                      <p className="fatigue-badge">
                        <strong>سرکوب خستگی هشدار:</strong> {suppressed} مورد تکراری
                      </p>
                    )}
                    {alertItem.erp_work_order_id && (
                      <div className="work-order-info">
                        <p>
                          <strong>دستور کار:</strong> {alertItem.erp_work_order_id}
                        </p>
                      </div>
                    )}
                    {rca && (
                      <div className="rca-box">
                        <strong>تحلیل ریشه علت (RCA)</strong>
                        <p>قانون غالب: {rca.dominant_rule || rca.primary_rule || '—'}</p>
                        <p>
                          سنسور غالب: {rca.dominant_sensor || rca.primary_sensor || '—'}
                        </p>
                        {rca.confidence !== undefined && (
                          <p>اطمینان: {(rca.confidence * 100).toFixed(0)}%</p>
                        )}
                      </div>
                    )}
                    <div className="alert-actions">
                      <button
                        onClick={() => rcaMutation.mutate(alertItem.alert_id)}
                        disabled={rcaMutation.isPending}
                      >
                        {rcaMutation.isPending ? 'در حال اجرای RCA…' : 'اجرای RCA'}
                      </button>
                      <button
                        className="sms-btn sms-primary"
                        onClick={() => alertSmsMutation.mutate(alertItem)}
                        disabled={alertSmsMutation.isPending}
                      >
                        {alertSmsMutation.isPending ? 'ارسال…' : 'ارسال پیامک'}
                      </button>
                      {alertItem.status === 'open' && (
                        <>
                          <button
                            onClick={() => handleAcknowledge(alertItem.alert_id)}
                            disabled={acknowledgeMutation.isPending}
                          >
                            تأیید
                          </button>
                          <button
                            onClick={() => handleResolve(alertItem.alert_id)}
                            disabled={resolveMutation.isPending}
                          >
                            رفع
                          </button>
                          {!alertItem.erp_work_order_id && (
                            <button
                              onClick={() => handleCreateWorkOrder(alertItem.alert_id)}
                              disabled={createWorkOrderMutation.isPending}
                              className="work-order-btn"
                            >
                              ایجاد دستور کار
                            </button>
                          )}
                        </>
                      )}
                      {alertItem.status === 'acknowledged' && (
                        <>
                          <button
                            onClick={() => handleResolve(alertItem.alert_id)}
                            disabled={resolveMutation.isPending}
                          >
                            رفع
                          </button>
                          {!alertItem.erp_work_order_id && (
                            <button
                              onClick={() => handleCreateWorkOrder(alertItem.alert_id)}
                              disabled={createWorkOrderMutation.isPending}
                              className="work-order-btn"
                            >
                              ایجاد دستور کار
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
