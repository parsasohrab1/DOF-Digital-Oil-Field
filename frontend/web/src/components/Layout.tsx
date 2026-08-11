import { ReactNode, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { kpiAPI } from '../api/services'
import { isOfflineLiveForced, shouldUseLocalLive } from '../api/offlineMode'
import './Layout.css'

interface LayoutProps {
  children: ReactNode
}

function featureFromPath(pathname: string): string {
  if (pathname === '/') return 'dashboard'
  const segment = pathname.replace(/^\//, '').split('/')[0]
  return segment || 'dashboard'
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const { user } = useAuth()
  const [offlineLive, setOfflineLive] = useState(() => shouldUseLocalLive())

  useEffect(() => {
    const sync = () => setOfflineLive(shouldUseLocalLive())
    window.addEventListener('online', sync)
    window.addEventListener('offline', sync)
    sync()
    return () => {
      window.removeEventListener('online', sync)
      window.removeEventListener('offline', sync)
    }
  }, [])

  useEffect(() => {
    if (shouldUseLocalLive()) return
    const feature = featureFromPath(location.pathname)
    kpiAPI.recordFeatureUsage(feature).catch(() => {
      /* non-blocking adoption metric */
    })
  }, [location.pathname])

  const link = (to: string, label: string) => (
    <Link to={to} className={location.pathname === to ? 'active' : ''}>
      {label}
    </Link>
  )

  return (
    <div className="layout" dir="rtl">
      <nav className="navbar">
        <div className="navbar-top">
          <div className="nav-brand">
            <h1>هوشمندسازی میادین</h1>
            <span>میدان دهلران · شرکت ملی نفت مناطق مرکزی</span>
          </div>
          {user && (
            <div className="nav-user">
              {(offlineLive || isOfflineLiveForced()) && (
                <span className="offline-live-badge" title="اجرای زنده بدون نیاز به اینترنت یا بک‌اند">
                  زنده آفلاین
                </span>
              )}
              <span>
                {user.username} ({roleFa(user.role)})
              </span>
            </div>
          )}
        </div>
        <div className="nav-links">
          {link('/', 'داشبورد')}
          {link('/wells', 'چاه‌ها')}
          {link('/alerts', 'هشدارها')}
          {link('/production-forecast', 'پیش‌بینی تولید')}
          {link('/dvr', 'اعتبارسنجی داده')}
          {link('/maintenance', 'نگهداری پیش‌بینانه')}
          {link('/scada', 'اسکادا و کنترل‌گر منطقی')}
          {link('/well3d', 'نمایش سه‌بعدی')}
          {link('/ar-integration', 'واقعیت افزوده')}
          {link('/report-builder', 'گزارش‌ساز')}
          {link('/reports', 'گزارش‌ها')}
          {link('/workflow-automation', 'اتوماسیون گردش‌کار')}
          {link('/ml-models', 'مدل‌های یادگیری ماشین')}
          {link('/lstm-forecast', 'پیش‌بینی سری‌زمانی LSTM')}
          {link('/federated-learning', 'یادگیری فدرال')}
          {link('/performance', 'عملکرد و KPI')}
          {link('/soc', 'مرکز امنیت')}
          {link('/remote-operations', 'عملیات از راه دور')}
          {link('/storage-optimization', 'بهینه‌سازی ذخیره‌سازی')}
          {link('/edge-computing', 'پردازش لبه (Edge)')}
          {link('/data-variables', 'متغیرهای داده')}
          {link('/blockchain-audit', 'ثبت بلاکچین')}
          {link('/system', 'سیستم')}
        </div>
      </nav>
      <main className="main-content">{children}</main>
    </div>
  )
}

function roleFa(role: string) {
  const map: Record<string, string> = {
    system_admin: 'مدیر سیستم',
    field_operator: 'اپراتور میدان',
    data_engineer: 'مهندس داده',
    viewer: 'بازدیدکننده',
    admin: 'مدیر',
    offline_operator: 'اپراتور آفلاین',
    guest: 'مهمان',
  }
  return map[role] || role
}
