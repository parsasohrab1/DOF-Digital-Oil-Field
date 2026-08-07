import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts'
import apiClient from '../api/client'
import {
  getDehloranMaintenanceSchedule,
  getDehloranRulPredictions,
  type DehloranRulPrediction,
} from '../data/dehloranRul'
import './Maintenance.css'

type RULPrediction = DehloranRulPrediction

interface MaintenanceSchedule {
  equipment_id: string
  equipment_type: string
  equipment_type_fa: string
  maintenance_type: string
  maintenance_type_fa: string
  scheduled_date: string
  estimated_duration: number
  priority: string
  status: string
  status_fa: string
}

interface PreventiveMaintenanceRecommendation {
  id: string
  category: 'pressure_maintenance' | 'production_optimization' | 'well_integrity' | 'equipment_health' | 'cost_reduction'
  title: string
  description: string
  well_name?: string
  equipment_id?: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  impact: string
  estimated_benefit: string
  action_required: string
  timeframe: string
  cost_estimate?: number
  roi?: number
}

const URGENCY_FA: Record<string, string> = {
  critical: 'بحرانی',
  high: 'بالا',
  medium: 'متوسط',
  low: 'پایین',
}

const PRIORITY_FA: Record<string, string> = {
  critical: 'بحرانی',
  high: 'بالا',
  medium: 'متوسط',
  low: 'پایین',
}

export default function Maintenance() {
  const [selectedEquipment, setSelectedEquipment] = useState<string>('')

  const { data: rulPredictions, isLoading: rulLoading } = useQuery({
    queryKey: ['rul-predictions'],
    queryFn: async () => getDehloranRulPredictions() as RULPrediction[],
    refetchInterval: 15000,
  })

  const { data: maintenanceSchedule } = useQuery({
    queryKey: ['maintenance-schedule', rulPredictions?.length],
    queryFn: async () =>
      getDehloranMaintenanceSchedule(rulPredictions ?? getDehloranRulPredictions()) as MaintenanceSchedule[],
    enabled: !!rulPredictions?.length,
  })

  const { data: spareParts } = useQuery({
    queryKey: ['spare-parts'],
    queryFn: async () => {
      return [
        { part: 'یاتاقان', current_stock: 5, required: 8, cost: 500 },
        { part: 'آب‌بند', current_stock: 12, required: 15, cost: 200 },
        { part: 'واشر', current_stock: 20, required: 25, cost: 50 },
      ]
    },
  })

  const { data: preventiveRecommendations, isLoading: recLoading } = useQuery({
    queryKey: ['preventive-maintenance-recommendations'],
    queryFn: async () => {
      try {
        const response = await apiClient.get('/api/ml-inference/maintenance/recommendations')
        return response.data
      } catch {
        return [
          {
            id: 'PM-001',
            category: 'pressure_maintenance',
            title: 'جلوگیری از افت فشار در چاه DEH-01',
            description: 'فشار چاه در حال کاهش است. بازرسی شیر یک‌طرفه و سامانه کنترل فشار توصیه می‌شود.',
            well_name: 'DEH-01',
            priority: 'high',
            impact: 'جلوگیری از ۱۵٪ افت تولید',
            estimated_benefit: 'افزایش تولید به میزان ۲۰۰ bbl/day',
            action_required: 'بازرسی و تعمیر شیرهای یک‌طرفه، کالیبره گیج فشار، آزمون سامانه جلوگیری‌کننده از فوران',
            timeframe: 'فوری — ظرف ۴۸ ساعت',
            cost_estimate: 15000,
            roi: 350,
          },
          {
            id: 'PM-002',
            category: 'production_optimization',
            title: 'بهینه‌سازی تولید چاه DEH-02',
            description: 'چاه کمتر از ظرفیت تولید می‌کند. تنظیم شیر کنترل جریان و بهینه‌سازی دبی توصیه می‌شود.',
            well_name: 'DEH-02',
            priority: 'medium',
            impact: 'افزایش تولید به میزان ۱۰٪',
            estimated_benefit: 'افزایش تولید به میزان ۱۵۰ bbl/day',
            action_required: 'تحلیل نودال، تنظیم موقعیت شیر کنترل جریان، بهینه‌سازی لیفت مصنوعی',
            timeframe: 'ظرف ۱ هفته',
            cost_estimate: 8000,
            roi: 280,
          },
          {
            id: 'PM-003',
            category: 'well_integrity',
            title: 'بازرسی یکپارچگی غلاف چاه DEH-03',
            description: 'نشانه‌های خوردگی در casing مشاهده شده. بازرسی یکپارچگی و ارزیابی پیوند سیمان توصیه می‌شود.',
            well_name: 'DEH-03',
            priority: 'critical',
            impact: 'جلوگیری از نشتی و آلودگی',
            estimated_benefit: 'جلوگیری از هزینه تعمیر اضطراری ۵۰۰٬۰۰۰ دلار',
            action_required: 'بازرسی casing، لاگ پیوند سیمان، پایش خوردگی',
            timeframe: 'فوری — ظرف ۲۴ ساعت',
            cost_estimate: 25000,
            roi: 2000,
          },
          {
            id: 'PM-004',
            category: 'pressure_maintenance',
            title: 'تعمیرات پیشگیرانه سامانه گازلیفت',
            description: 'سامانه گازلیفت نیاز به سرویس دارد. کاهش بازدهی می‌تواند باعث افت فشار شود.',
            equipment_id: 'GASLIFT-DEH-04',
            well_name: 'DEH-04',
            priority: 'high',
            impact: 'جلوگیری از ۲۰٪ افت تولید',
            estimated_benefit: 'افزایش تولید به میزان ۳۰۰ bbl/day',
            action_required: 'سرویس کمپرسور، بازرسی خطوط گاز، آزمون شیرهای کنترل',
            timeframe: 'ظرف ۳ روز',
            cost_estimate: 12000,
            roi: 400,
          },
          {
            id: 'PM-005',
            category: 'production_optimization',
            title: 'بهینه‌سازی سامانه لیفت مصنوعی',
            description: 'پمپ درون‌چاهی الکتریکی نیاز به تنظیم دارد. بهینه‌سازی می‌تواند تولید را ۱۲٪ افزایش دهد.',
            equipment_id: 'ESP-DEH-05',
            well_name: 'DEH-05',
            priority: 'medium',
            impact: 'افزایش بازدهی پمپ',
            estimated_benefit: 'افزایش تولید ۱۸۰ bbl/day، کاهش مصرف برق ۸٪',
            action_required: 'تنظیم فرکانس، بررسی دمای موتور، بهینه‌سازی تنظیم پمپ',
            timeframe: 'ظرف ۱ هفته',
            cost_estimate: 6000,
            roi: 450,
          },
          {
            id: 'PM-006',
            category: 'equipment_health',
            title: 'تعمیرات پیشگیرانه جداکننده',
            description: 'جداکننده نیاز به تمیزکاری و بازرسی دارد. رسوبات می‌توانند بازدهی را کاهش دهند.',
            equipment_id: 'SEP-DEH-06',
            well_name: 'DEH-06',
            priority: 'medium',
            impact: 'بهبود کیفیت جداسازی',
            estimated_benefit: 'کاهش ۵٪ آب در نفت، بهبود کیفیت محصول',
            action_required: 'تمیزکاری داخلی، بازرسی صفحات، آزمون سامانه کنترل',
            timeframe: 'ظرف ۲ هفته',
            cost_estimate: 10000,
            roi: 180,
          },
          {
            id: 'PM-007',
            category: 'pressure_maintenance',
            title: 'جلوگیری از افت فشار در خط لوله',
            description: 'نشانه‌های افت فشار در خط اصلی مشاهده شده. بازرسی نشتی و ارزیابی رسوب ضروری است.',
            equipment_id: 'PIPELINE-DEH-07',
            well_name: 'DEH-07',
            priority: 'high',
            impact: 'جلوگیری از توقف تولید',
            estimated_benefit: 'جلوگیری از هزینه توقف تولید ۱٬۰۰۰٬۰۰۰ دلار',
            action_required: 'بازرسی خط لوله، پیگینگ، تشخیص نشتی، آزمون فشار',
            timeframe: 'فوری — ظرف ۷۲ ساعت',
            cost_estimate: 35000,
            roi: 2857,
          },
          {
            id: 'PM-008',
            category: 'production_optimization',
            title: 'بهینه‌سازی مدیریت شیر کنترل جریان',
            description: 'چندین چاه نیاز به تنظیم شیر کنترل جریان دارند. بهینه‌سازی می‌تواند تولید کل میدان را ۸٪ افزایش دهد.',
            well_name: 'DEH-01…DEH-16',
            priority: 'medium',
            impact: 'افزایش تولید کل میدان',
            estimated_benefit: 'افزایش تولید به میزان ۵۰۰ bbl/day در کل میدان',
            action_required: 'تحلیل پروفایل تولید، تنظیم شیر کنترل جریان هر چاه، پایش پیوسته',
            timeframe: 'ظرف ۲ هفته',
            cost_estimate: 15000,
            roi: 520,
          },
          {
            id: 'PM-009',
            category: 'well_integrity',
            title: 'بازرسی و نگهداری مجموعه جلوگیری‌کننده از فوران',
            description: 'جلوگیری‌کننده از فوران نیاز به آزمون و بازرسی دارد. اطمینان از عملکرد صحیح برای ایمنی ضروری است.',
            equipment_id: 'BOP-DEH-08',
            well_name: 'DEH-08',
            priority: 'critical',
            impact: 'ایمنی و جلوگیری از فوران',
            estimated_benefit: 'جلوگیری از حادثه‌ای با هزینه میلیون‌ها دلار',
            action_required: 'آزمون عملکرد جلوگیری‌کننده از فوران، آزمون فشار، بازرسی چشمی، مرور سوابق نگهداری',
            timeframe: 'فوری — ظرف ۲۴ ساعت',
            cost_estimate: 20000,
            roi: 10000,
          },
          {
            id: 'PM-010',
            category: 'cost_reduction',
            title: 'بهینه‌سازی مصرف انرژی',
            description: 'سامانه‌های برقی و کمپرسورها می‌توانند کارآمدتر عمل کنند. کاهش ۱۵٪ انرژی قابل دستیابی است.',
            equipment_id: 'POWER-DEH-09',
            well_name: 'DEH-09',
            priority: 'low',
            impact: 'کاهش هزینه‌های عملیاتی',
            estimated_benefit: 'کاهش هزینه برق به میزان ۲۵٬۰۰۰ دلار در ماه',
            action_required: 'بازبینی تعادل بار، بهینه‌سازی کارکرد کمپرسور، نصب درایو فرکانس متغیر',
            timeframe: 'ظرف ۱ ماه',
            cost_estimate: 50000,
            roi: 600,
          },
        ] as PreventiveMaintenanceRecommendation[]
      }
    },
    refetchInterval: 300000,
  })

  const urgencyColors: Record<string, string> = {
    critical: '#c62828',
    high: '#f9a825',
    medium: '#0288d1',
    low: '#2e7d32',
  }

  if (rulLoading) {
    return <div className="loading">در حال بارگذاری داده‌های نگهداری…</div>
  }

  const rulChartData = (rulPredictions ?? []).slice(0, 12).map((pred) => ({
    equipment: pred.equipment_id.replace('ESP-', ''),
    fullId: pred.equipment_id,
    rul_days: pred.rul_days,
    urgency: pred.urgency,
    confidence: (pred.confidence * 100).toFixed(0),
  }))

  const categoryLabels: Record<string, string> = {
    pressure_maintenance: 'نگهداری فشار',
    production_optimization: 'بهینه‌سازی تولید',
    well_integrity: 'یکپارچگی چاه',
    equipment_health: 'سلامت تجهیزات',
    cost_reduction: 'کاهش هزینه',
  }

  return (
    <div className="maintenance-page" dir="rtl">
      <h2>نگهداری پیش‌بینانه</h2>

      <div className="maintenance-grid">
        <div className="maintenance-card">
          <h3>پیش‌بینی عمر مفید باقی‌مانده</h3>
          <p className="section-description">۱۲ تجهیز با کمترین عمر مفید باقی‌مانده در میدان دهلران</p>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={rulChartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="equipment" tick={{ fill: '#555', fontSize: 11 }} />
              <YAxis tick={{ fill: '#555', fontSize: 11 }} unit=" روز" />
              <Tooltip
                contentStyle={{ background: '#ffffff', border: '1px solid #ccc', borderRadius: 8, color: '#111' }}
                labelStyle={{ color: '#111' }}
                formatter={(value: number) => [`${value} روز`, 'عمر مفید']}
              />
              <Legend wrapperStyle={{ color: '#333' }} />
              <Bar dataKey="rul_days" name="عمر مفید باقی‌مانده (روز)" radius={[4, 4, 0, 0]}>
                {rulChartData.map((row) => (
                  <Cell key={row.fullId} fill={urgencyColors[row.urgency] || '#5c6bc0'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="maintenance-card full-width">
          <h3>پیش‌بینی عمر مفید باقی‌مانده به‌ازای تجهیز</h3>
          <p className="section-description">
            پمپ‌های درون‌چاهی ۱۶ چاه دهلران به‌همراه تجهیزات تسهیلات مشترک — مرتب‌شده از بحرانی به پایدار
          </p>
          <div className="table-container">
            {!rulPredictions?.length ? (
              <p className="empty-state">داده‌ای برای نمایش وجود ندارد.</p>
            ) : (
              <table className="rul-table">
                <thead>
                  <tr>
                    <th>شناسه تجهیز</th>
                    <th>چاه / محل</th>
                    <th>نوع</th>
                    <th>عمر مفید (روز)</th>
                    <th>عمر مفید (ساعت)</th>
                    <th>اطمینان</th>
                    <th>فوریت</th>
                    <th>پنجره نگهداری</th>
                    <th>توصیه</th>
                  </tr>
                </thead>
                <tbody>
                  {rulPredictions.map((pred) => (
                    <tr key={pred.equipment_id} className={`urgency-row-${pred.urgency}`}>
                      <td className="mono">{pred.equipment_id}</td>
                      <td>{pred.well_name || 'تسهیلات میدان'}</td>
                      <td>{pred.equipment_type_fa || pred.equipment_type}</td>
                      <td>
                        <strong>{pred.rul_days.toFixed(0)}</strong>
                      </td>
                      <td>{pred.rul_hours.toLocaleString('fa-IR')}</td>
                      <td>{(pred.confidence * 100).toFixed(0)}٪</td>
                      <td>
                        <span
                          className="urgency-badge"
                          style={{ backgroundColor: urgencyColors[pred.urgency] }}
                        >
                          {URGENCY_FA[pred.urgency] || pred.urgency}
                        </span>
                      </td>
                      <td>{pred.maintenance_window_days} روز</td>
                      <td className="rec-cell">{pred.recommendation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="maintenance-card">
          <h3>برنامه نگهداری</h3>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>تجهیز</th>
                  <th>نوع</th>
                  <th>نوع نگهداری</th>
                  <th>تاریخ برنامه‌ریزی</th>
                  <th>مدت (ساعت)</th>
                  <th>اولویت</th>
                  <th>وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {maintenanceSchedule?.map((schedule, idx) => (
                  <tr key={idx}>
                    <td>{schedule.equipment_id}</td>
                    <td>{schedule.equipment_type_fa || schedule.equipment_type}</td>
                    <td>{schedule.maintenance_type_fa || schedule.maintenance_type}</td>
                    <td>{new Date(schedule.scheduled_date).toLocaleDateString('fa-IR')}</td>
                    <td>{schedule.estimated_duration}</td>
                    <td>
                      <span className={`priority-${schedule.priority}`}>
                        {PRIORITY_FA[schedule.priority] || schedule.priority}
                      </span>
                    </td>
                    <td>{schedule.status_fa || schedule.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="maintenance-card">
          <h3>بهینه‌سازی قطعات یدکی</h3>
          <div className="spare-parts">
            {spareParts?.map((part, idx) => (
              <div key={idx} className="spare-part-item">
                <div className="part-name">{part.part}</div>
                <div className="part-stock">
                  موجودی: {part.current_stock} / مورد نیاز: {part.required}
                </div>
                <div className="part-status">
                  {part.current_stock >= part.required ? (
                    <span className="status-ok">✓ کافی</span>
                  ) : (
                    <span className="status-low">⚠ موجودی کم</span>
                  )}
                </div>
                <div className="part-cost">هزینه: ${part.cost}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="maintenance-card">
          <h3>پیش‌بینی هزینه نگهداری</h3>
          <div className="cost-forecast">
            <div className="cost-item">
              <div className="cost-label">این ماه</div>
              <div className="cost-value">$45,000</div>
            </div>
            <div className="cost-item">
              <div className="cost-label">ماه آینده</div>
              <div className="cost-value">$52,000</div>
            </div>
            <div className="cost-item">
              <div className="cost-label">این فصل</div>
              <div className="cost-value">$150,000</div>
            </div>
          </div>
        </div>

        <div className="maintenance-card">
          <h3>توصیه‌های نگهداری پیش‌بینانه</h3>
          <div className="recommendations">
            {rulPredictions
              ?.filter((p) => p.urgency === 'high' || p.urgency === 'critical')
              .map((pred) => (
                <div key={pred.equipment_id} className="recommendation-item">
                  <div className="rec-equipment">{pred.equipment_id}</div>
                  <div className="rec-message">{pred.recommendation}</div>
                  <div className="rec-urgency">
                    فوریت:{' '}
                    <span style={{ color: urgencyColors[pred.urgency] }}>
                      {URGENCY_FA[pred.urgency] || pred.urgency}
                    </span>
                  </div>
                  <div className="rec-window">پنجره نگهداری: {pred.maintenance_window_days} روز</div>
                </div>
              ))}
          </div>
        </div>

        <div className="maintenance-card full-width">
          <h3>توصیه‌های نگهداری پیشگیرانه میدان نفت و گاز</h3>
          <p className="section-description">
            توصیه‌های هوشمند برای جلوگیری از افت فشار، بهینه‌سازی تولید و نگهداری پیشگیرانه تجهیزات
          </p>

          {recLoading ? (
            <div className="loading">در حال بارگذاری توصیه‌ها…</div>
          ) : (
            <div className="preventive-recommendations">
              <div className="recommendation-filters">
                <button className="filter-btn active" onClick={() => setSelectedEquipment('all')}>
                  همه
                </button>
                <button
                  className="filter-btn"
                  onClick={() => setSelectedEquipment('pressure_maintenance')}
                >
                  نگهداری فشار
                </button>
                <button
                  className="filter-btn"
                  onClick={() => setSelectedEquipment('production_optimization')}
                >
                  بهینه‌سازی تولید
                </button>
                <button className="filter-btn" onClick={() => setSelectedEquipment('well_integrity')}>
                  یکپارچگی چاه
                </button>
                <button
                  className="filter-btn"
                  onClick={() => setSelectedEquipment('equipment_health')}
                >
                  سلامت تجهیزات
                </button>
              </div>

              <div className="preventive-recommendations-list">
                {preventiveRecommendations
                  ?.filter(
                    (rec: PreventiveMaintenanceRecommendation) =>
                      selectedEquipment === '' ||
                      selectedEquipment === 'all' ||
                      rec.category === selectedEquipment
                  )
                  .sort(
                    (
                      a: PreventiveMaintenanceRecommendation,
                      b: PreventiveMaintenanceRecommendation
                    ) => {
                      const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
                      return priorityOrder[a.priority] - priorityOrder[b.priority]
                    }
                  )
                  .map((rec: PreventiveMaintenanceRecommendation) => (
                    <div
                      key={rec.id}
                      className={`preventive-rec-item priority-${rec.priority}`}
                    >
                      <div className="rec-header">
                        <div className="rec-title-section">
                          <h4>{rec.title}</h4>
                          <span className="rec-category">
                            {categoryLabels[rec.category] || rec.category}
                          </span>
                        </div>
                        <div
                          className="rec-priority-badge"
                          style={{ backgroundColor: urgencyColors[rec.priority] }}
                        >
                          {PRIORITY_FA[rec.priority] || rec.priority}
                        </div>
                      </div>

                      <div className="rec-body">
                        <p className="rec-description">{rec.description}</p>

                        <div className="rec-details-grid">
                          <div className="rec-detail-item">
                            <span className="detail-label">چاه/تجهیز:</span>
                            <span className="detail-value">
                              {rec.well_name || rec.equipment_id || 'عمومی'}
                            </span>
                          </div>
                          <div className="rec-detail-item">
                            <span className="detail-label">اثر:</span>
                            <span className="detail-value">{rec.impact}</span>
                          </div>
                          <div className="rec-detail-item">
                            <span className="detail-label">سود برآوردی:</span>
                            <span className="detail-value highlight">{rec.estimated_benefit}</span>
                          </div>
                          <div className="rec-detail-item">
                            <span className="detail-label">بازه زمانی:</span>
                            <span className="detail-value">{rec.timeframe}</span>
                          </div>
                          {rec.cost_estimate && (
                            <div className="rec-detail-item">
                              <span className="detail-label">هزینه برآوردی:</span>
                              <span className="detail-value">
                                ${rec.cost_estimate.toLocaleString()}
                              </span>
                            </div>
                          )}
                          {rec.roi && (
                            <div className="rec-detail-item">
                              <span className="detail-label">بازگشت سرمایه (ROI):</span>
                              <span className="detail-value highlight">{rec.roi}x</span>
                            </div>
                          )}
                        </div>

                        <div className="rec-actions">
                          <div className="action-required">
                            <strong>اقدامات لازم:</strong>
                            <p>{rec.action_required}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
              </div>

              {preventiveRecommendations && preventiveRecommendations.length === 0 && (
                <div className="no-recommendations">
                  <p>در حال حاضر توصیه‌ای موجود نیست.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
