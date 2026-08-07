import { useState } from 'react'
import { FIELD } from '../data/dehloranField'
import './SystemArchitecture.css'

type SectionId =
  | 'sensors'
  | 'loggers'
  | 'interfaces'
  | 'protocols'
  | 'ai'
  | 'inputs'
  | 'outputs'
  | 'observability'
  | 'streaming'
  | 'storage'
  | 'services'
  | 'security'
  | 'infra'

type Item = { name: string; nameEn?: string; detail: string; tag?: string }

const SECTIONS: Array<{ id: SectionId; title: string; titleEn: string; items: Item[] }> = [
  {
    id: 'sensors',
    title: 'سنسورها و متغیرهای اندازه‌گیری',
    titleEn: 'Sensors & Measured Variables',
    items: [
      { name: 'فشار سرچاهی', nameEn: 'Wellhead Pressure', detail: 'فشار سرچاه — psi' },
      { name: 'دمای سرچاهی', nameEn: 'Wellhead Temperature', detail: 'دمای سرچاه — °C' },
      { name: 'فشار غلاف', nameEn: 'Casing Pressure', detail: 'فشار غلاف/annulus — psi' },
      { name: 'دبی نفت / گاز / آب', nameEn: 'Oil / Gas / Water Rate', detail: 'نرخ تولید — bbl/d · Mscf/d' },
      { name: 'درصد آب تولیدی', nameEn: 'Water Cut', detail: 'نسبت آب به سیال تولیدی — %' },
      { name: 'نسبت گاز به نفت', nameEn: 'Gas–Oil Ratio', detail: 'نسبت گاز به نفت — scf/bbl' },
      { name: 'جریان / لرزش / دمای پمپ درون‌چاهی الکتریکی', nameEn: 'Downhole Electric Pump Current / Vibration / Temp', detail: 'سلامت پمپ درون‌چاهی الکتریکی' },
      { name: 'فشار منیفولد / جداکننده / خط لوله', nameEn: 'Manifold / Separator / Pipeline P', detail: 'تأسیسات سطح' },
      { name: 'سطح مایع جداکننده', nameEn: 'Separator Level', detail: 'سطح مایع — %' },
      { name: 'کاتالوگ ۵۹ متغیره بک‌اند', nameEn: 'Backend Data Variables (59)', detail: 'فشار، دما، جریان، ترکیب، لرزش، الکتریکی، محیطی — data-variables-service' },
      { name: 'دبی‌سنج مجازی نفت', nameEn: 'Virtual Flow Meter', detail: 'برآورد دبی بدون فلومتر فیزیکی' },
    ],
  },
  {
    id: 'loggers',
    title: 'دیتا لاگرها و لبه',
    titleEn: 'Data Loggers & Edge',
    items: [
      { name: 'سرویس محاسبات لبه', nameEn: 'Edge Computing Service', detail: 'آنومالی، آستانه، روند و تجمیع محلی — :8009' },
      { name: 'بافر آفلاین', nameEn: 'Offline Buffer', detail: 'ذخیره موقت هنگام قطع شبکه (SQLite + DuckDB)' },
      { name: 'عملیات قطع‌شده', nameEn: 'Disconnected Operation', detail: 'ادامه کار لبه وقتی ابر در دسترس نیست' },
      { name: 'مانیتور اتصال', nameEn: 'Connection Monitor', detail: 'پایش سلامت لینک لبه ↔ ابر' },
      { name: 'ذخیره سری‌زمانی DuckDB', nameEn: 'DuckDB TS Storage', detail: 'بافر سریع سری‌زمانی در لبه' },
      { name: 'اعتبارسنجی و تطبیق داده', nameEn: 'Data Validation & Reconciliation', detail: 'اعتبارسنجی، پرتی، تطبیق جرم/انرژی، امتیاز کیفیت — :8011' },
      { name: 'سلامت سنسور', nameEn: 'Sensor Health', detail: 'وضعیت هر سنسور در مسیر ingestion' },
      { name: 'فشرده‌سازی سری‌زمانی', nameEn: 'Compression Manager', detail: 'فشرده‌سازی و نگهداری داده Timescale' },
    ],
  },
  {
    id: 'interfaces',
    title: 'رابط‌ها',
    titleEn: 'Interfaces',
    items: [
      { name: 'درگاه برنامه‌نویسی رست', nameEn: 'REST Proxy', detail: 'ورودی واحد سرویس‌ها با ژتون امنیتی و کنترل دسترسی' },
      { name: 'وب‌سوکت بلادرنگ', nameEn: 'Realtime WS', detail: 'جریان زنده برای داشبورد' },
      { name: 'رویداد سمت سرور بلادرنگ', nameEn: 'Server-Sent Events', detail: 'مسیر جایگزین جریان زنده' },
      { name: 'کلاینت پروتکل ارتباط باز صنعتی', nameEn: 'OPC-UA Client', detail: 'خواندن/نوشتن اسکادا و کنترل‌گر منطقی' },
      { name: 'کلاینت پروتکل مودباس', nameEn: 'Modbus TCP', detail: 'رجیسترهای کنترل‌گر منطقی' },
      { name: 'کلاینت پیام‌رسان بی‌سیم سبک', nameEn: 'MQTT Client', detail: 'سنسورهای بی‌سیم — پیش‌فرض غیرفعال' },
      { name: 'کلاینت شبکه حسگر کم‌مصرف', nameEn: 'LoRaWAN', detail: 'آپلینک سنسور کم‌مصرف — پیش‌فرض غیرفعال' },
      { name: 'اتصال سامانه برنامه‌ریزی منابع سازمان', nameEn: 'ERP', detail: 'دستورکار نگهداری (شبیه‌سازی)' },
      { name: 'درگاه شاخص کلیدی عملکرد', nameEn: 'Executive KPIs', detail: 'شاخص‌های اجرایی و میزان استفاده از قابلیت‌ها' },
      { name: 'اپلیکیشن موبایل میدانی', nameEn: 'Mobile App', detail: 'کلاینت میدانی' },
    ],
  },
  {
    id: 'protocols',
    title: 'پروتکل‌ها',
    titleEn: 'Protocols',
    items: [
      { name: 'پروتکل اچ‌تی‌تی‌پی / رست', detail: 'درگاه سرویس‌ها و رابط کاربری' },
      { name: 'وب‌سوکت', detail: 'استریم بلادرنگ داشبورد' },
      { name: 'رویداد سمت سرور', detail: 'استریم رویداد سمت سرور' },
      { name: 'پروتکل ارتباط باز صنعتی', detail: 'اتوماسیون صنعتی اسکادا / کنترل‌گر منطقی' },
      { name: 'پروتکل مودباس', detail: 'ارتباط رجیستری با کنترل‌گر منطقی' },
      { name: 'پیام‌رسان بی‌سیم سبک', detail: 'پیام‌رسانی سنسور بی‌سیم' },
      { name: 'شبکه حسگر کم‌مصرف', detail: 'شبکه حسگر کم‌مصرف میدان' },
      { name: 'صف پیام کافکا', detail: 'باس رویدادهای میدان' },
      { name: 'پروتکل ردیابی باز', detail: 'ارسال تریس به جمع‌کننده ردیابی' },
      { name: 'ژتون امنیتی', detail: 'احراز هویت درگاه' },
      { name: 'رمزنگاری متقابل سرویس‌ها', detail: 'اختیاری بین میکروسرویس‌ها' },
      { name: 'رمز یک‌بارمصرف زمانی', detail: 'احراز هویت دو مرحله‌ای کاربر' },
    ],
  },
  {
    id: 'ai',
    title: 'الگوریتم‌های هوش مصنوعی',
    titleEn: 'AI / ML Algorithms',
    items: [
      { name: 'جنگل ایزوله', nameEn: 'Isolation Forest', detail: 'تشخیص ناهنجاری — رجیستری مدل‌ها' },
      { name: 'جنگل تصادفی', nameEn: 'Random Forest', detail: 'پیش‌بینی خرابی تجهیزات' },
      { name: 'شبکه حافظه‌دار بلندکوتاه سری‌زمانی', nameEn: 'LSTM', detail: 'پیش‌بینی چندمرحله‌ای' },
      { name: 'شبکه حافظه‌دار پیشرفته', nameEn: 'Advanced LSTM', detail: 'پیش‌بینی پیشرفته به‌ازای هر چاه' },
      { name: 'مدل عمر مفید باقی‌مانده', nameEn: 'Remaining Useful Life', detail: 'عمر مفید باقی‌مانده تجهیزات' },
      { name: 'آنالیتیکس لبه', nameEn: 'Edge Heuristics', detail: 'آستانه، روند، تجمیع و ناهنجاری محلی' },
      { name: 'تشخیص دریفت مدل', nameEn: 'Model Drift', detail: 'پایش کیفیت مدل و مقایسه نسخه' },
      { name: 'منحنی زوال تولید', nameEn: 'Decline Curve', detail: 'پیش‌بینی افت دبی نفت چاه/میدان' },
      { name: 'پیش‌بینی درصد آب تولیدی', nameEn: 'Water-Cut Forecast', detail: 'رشد درصد آب تولیدی افق ۹۰روز/۱۲ماه' },
      { name: 'پردازش جریان نمونه', nameEn: 'Flink CEP', detail: 'تشخیص الگوی ناهنجاری در استریم — نمونه' },
    ],
  },
  {
    id: 'inputs',
    title: 'ورودی‌های داشبورد',
    titleEn: 'Dashboard Inputs',
    items: [
      { name: 'وضعیت زنده ۱۶ چاه دهلران', detail: 'نفت، گاز، آب، درصد آب تولیدی، سلامت، ریسک تجهیزات' },
      { name: 'استریم وب‌سوکت / رویداد سمت سرور', detail: 'به‌روزرسانی بلادرنگ از درگاه برنامه‌نویسی' },
      { name: 'هشدارها (درگاه هشدار)', detail: 'لیست و وضعیت آلارم‌های باز' },
      { name: 'داده اعتبارسنجی و تطبیق', detail: 'کیفیت، پرتی، تطبیق تولید / دبی‌سنج مجازی' },
      { name: 'داده دوقلوی دیجیتال سه‌بعدی', detail: 'مسیر چاه، فشار/دما عمقی، جلوگیری‌کننده از فوران، غلاف' },
      { name: 'داده واقعیت افزوده', detail: 'دستگاه، نشست، لنگر، پوشش بصری مدل اطلاعات تأسیسات' },
      { name: 'گزارش‌ساز / BI', detail: 'متادیتای گزارش و کوئری reporting-service' },
      { name: 'شاخص کلیدی عملکرد و تله‌متری استفاده', detail: 'ثبت استفاده از هر تب/قابلیت' },
      { name: 'اتصال اسکادا / کنترل‌گر منطقی', detail: 'کارت‌های پروتکل ارتباط باز صنعتی و مودباس' },
      { name: 'پیش‌بینی تولید', detail: 'سری منحنی افت تولید و درصد آب تولیدی به‌ازای هر چاه' },
    ],
  },
  {
    id: 'outputs',
    title: 'خروجی‌های داشبورد',
    titleEn: 'Dashboard Outputs',
    items: [
      { name: 'نقشه و شاخص کلیدی عملکرد میدان', detail: 'خلاصه تولید و سلامت چاه‌ها' },
      { name: 'نمودارهای منحنی افت تولید / درصد آب تولیدی', detail: 'Recharts — میدان و هر چاه' },
      { name: 'مدیریت هشدار', detail: 'مشاهده، تأیید، رفع آلارم' },
      { name: 'جدول و کارت چاه‌ها', detail: 'وضعیت هر DEH-01…16' },
      { name: 'گزارش اعتبارسنجی و تطبیق داده', detail: 'کیفیت داده و reconciliation' },
      { name: 'توصیه نگهداری پیش‌بینانه', detail: 'عمر مفید باقی‌مانده و برنامه نگهداری پیشگیرانه' },
      { name: 'نمای اسکادا / کنترل‌گر منطقی', detail: 'وضعیت پروتکل و اتصالات صنعتی' },
      { name: 'دوقلوی سه‌بعدی چاه', detail: 'Three.js / React Three Fiber' },
      { name: 'نمای واقعیت افزوده میدانی', detail: 'نمایشگر سربلند و پوشش بصری روی دارایی' },
      { name: 'گزارش‌ساز', detail: 'گزارش سفارشی عملیاتی' },
    ],
  },
  {
    id: 'observability',
    title: 'گرافانا، پرومتئوس و مشاهده‌پذیری',
    titleEn: 'Grafana · Prometheus · Observability',
    items: [
      { name: 'پرومتئوس', nameEn: ':9090', detail: 'جمع‌آوری متریک سرویس‌ها' },
      { name: 'گرافانا', nameEn: ':3001', detail: 'داشبورد پایش عملکرد سامانه' },
      { name: 'جمع‌کننده ردیابی باز', nameEn: 'OpenTelemetry', detail: 'دریافت تریس توزیع‌شده' },
      { name: 'تمپو گرافانا', nameEn: ':3200', detail: 'ذخیره و جستجوی ردیابی توزیع‌شده' },
      { name: 'قوانین آلارم پرومتئوس', detail: 'کیفیت داده · کیفیت مدل · شاخص‌های اجرایی' },
      { name: 'متریک و تریس مشترک', detail: 'ابزارسازی داخل هر میکروسرویس' },
      { name: 'ارسال لاگ', detail: 'پیکربندی موجود؛ مخزن لاگ اختیاری' },
    ],
  },
  {
    id: 'streaming',
    title: 'کافکا و استریم',
    titleEn: 'Kafka & Streaming',
    items: [
      { name: 'کافکا و هماهنگ‌کننده صف', detail: 'باس رویداد میدان در استقرار محلی' },
      { name: 'موضوع داده خام سنسور', detail: 'داده خام سنسور' },
      { name: 'موضوع داده پردازش‌شده', detail: 'داده پردازش‌شده' },
      { name: 'موضوع هشدارها', detail: 'رویداد هشدار' },
      { name: 'موضوع دستورات کنترلی', detail: 'دستورات کنترلی' },
      { name: 'موضوع دستورات بحرانی', detail: 'دستورات بحرانی / تأییدشده' },
      { name: 'پردازش جریان نمونه', detail: 'پاکسازی، غنی‌سازی و تشخیص الگو روی استریم' },
      { name: 'ردیس', detail: 'کش، نشست، محدودیت نرخ و انتشار کمکی' },
    ],
  },
  {
    id: 'storage',
    title: 'پایگاه‌داده و ذخیره‌سازی',
    titleEn: 'Databases & Storage',
    items: [
      { name: 'پایگاه‌داده رابطه‌ای', detail: 'کاربر، تگ، آلارم، دستور، گزارش' },
      { name: 'پایگاه سری‌زمانی', detail: 'جدول‌های زمانی سنسور، فشرده‌سازی، نگهداری' },
      { name: 'کلاستر چندگرهی سری‌زمانی', detail: 'مقیاس‌پذیری سری‌زمانی' },
      { name: 'ردیس', detail: 'کش و محدودیت نرخ' },
      { name: 'ذخیره لبه و آفلاین', detail: 'بافر لبه و آفلاین' },
      { name: 'رجیستری مدل‌های یادگیری ماشین', detail: 'ردیابی مدل‌های یادگیری ماشین' },
      { name: 'حجم مدل‌های آموزش‌دیده', detail: 'آرتیفکت مدل‌های آموزش‌دیده' },
    ],
  },
  {
    id: 'services',
    title: 'میکروسرویس‌ها',
    titleEn: 'Microservices',
    items: [
      { name: 'درگاه برنامه‌نویسی', detail: 'پروکسی، وب‌سوکت / رویداد سمت سرور، شاخص کلیدی عملکرد، امنیت' },
      { name: 'سرویس احراز هویت', detail: 'ژتون امنیتی، کاربر، احراز هویت دو مرحله‌ای' },
      { name: 'سرویس دریافت داده', detail: 'ورود سنسور و پروتکل‌های صنعتی' },
      { name: 'سرویس استنتاج یادگیری ماشین', detail: 'ناهنجاری، خرابی، پیش‌بینی، عمر مفید باقی‌مانده' },
      { name: 'سرویس هشدار', detail: 'قوانین، تحلیل علت ریشه، اعلان' },
      { name: 'سرویس گزارش‌گیری', detail: 'گزارش، هوش تجاری، نسب‌شناسی، گردش‌کار' },
      { name: 'سرویس فرمان و کنترل', detail: 'چرخه عمر دستور کنترلی' },
      { name: 'سرویس کاتالوگ تگ', detail: 'کاتالوگ تگ‌ها' },
      { name: 'سرویس دوقلوی دیجیتال', detail: 'شبیه‌سازی، مدل سه‌بعدی، چه-اگر، واقعیت افزوده' },
      { name: 'سرویس محاسبات لبه', detail: 'آنالیتیکس لبه' },
      { name: 'سرویس یکپارچه‌سازی منابع سازمان', detail: 'دستورکار نگهداری' },
      { name: 'سرویس اعتبارسنجی و تطبیق داده', detail: 'اعتبارسنجی و تطبیق' },
      { name: 'سرویس عملیات از راه دور', detail: 'ست‌پوینت، شیر، توقف اضطراری' },
      { name: 'سرویس متغیرهای داده', detail: 'کاتالوگ متغیرها' },
      { name: 'سرویس بهینه‌سازی ذخیره', detail: 'فشرده‌سازی و نگهداری' },
    ],
  },
  {
    id: 'security',
    title: 'امنیت',
    titleEn: 'Security',
    items: [
      { name: 'ژتون دسترسی و تازه‌سازی', detail: 'احراز هویت درگاه' },
      { name: 'کنترل دسترسی مبتنی بر نقش', detail: 'نقش‌ها: مدیر · اپراتور · مهندس · بازدیدکننده' },
      { name: 'احراز هویت دو عاملی', detail: 'رمز یک‌بارمصرف زمانی' },
      { name: 'محدودکننده نرخ', detail: 'محدودیت نرخ بر اساس نقش' },
      { name: 'تشخیص تهدید / مدیریت رویداد امنیتی', detail: 'امتیاز ریسک و رویداد امنیتی' },
      { name: 'اعتبارسنجی ورودی', detail: 'محافظت در برابر تزریق در درگاه' },
      { name: 'امنیت صنعتی', detail: 'اعتبارسنجی بسته مودباس و امضای پیام' },
      { name: 'گردش کار امن فرمان', detail: 'شبیه‌سازی ← تأیید دو نفره ← اجرا' },
      { name: 'رمزنگاری متقابل سرویس‌ها', detail: 'رمزنگاری متقابل بین سرویس‌ها' },
    ],
  },
  {
    id: 'infra',
    title: 'زیرساخت',
    titleEn: 'Infrastructure',
    items: [
      { name: 'استقرار کانتینری توسعه', detail: 'استک کامل محلی: پایگاه‌داده، کافکا، سرویس‌ها، گرافانا، پرومتئوس' },
      { name: 'مانیفست‌های ارکستراسیون', detail: 'استقرار پایگاه‌داده، ردیس، کافکا، سری‌زمانی، درگاه' },
      { name: 'پیکربندی گرافانا', detail: 'منبع داده و داشبورد پایش عملکرد از پیش تعریف‌شده' },
      { name: 'رابط وب واکنش‌گرا', detail: 'داشبورد وب هوشمندسازی میادین' },
      { name: 'کتابخانه‌های داده و نمودار', detail: 'داده، ارتباط شبکه، نمودار' },
      { name: 'موتور سه‌بعدی', detail: 'نمایش سه‌بعدی چاه' },
      { name: 'وب‌اپلیکیشن پیشرو', detail: 'قابلیت نصب و کار آفلاین نسبی' },
      { name: 'اسکریپت راه‌اندازی داشبورد', detail: 'راه‌اندازی سریع داشبورد محلی' },
    ],
  },
]

export default function SystemArchitecture() {
  const [active, setActive] = useState<SectionId>('sensors')
  const section = SECTIONS.find((s) => s.id === active) || SECTIONS[0]

  return (
    <div className="sys-page" dir="rtl">
      <header className="sys-hero">
        <div>
          <p className="sys-client">{FIELD.clientFa}</p>
          <h2>سیستم — معماری و اجزای هوشمندسازی میادین نفت و گاز</h2>
          <p className="sys-meta">
            {FIELD.nameFa} · فهرست سنسورها، لاگرها، رابط‌ها، پروتکل‌ها، هوش مصنوعی، ورودی/خروجی داشبورد،
            گرافانا، پرومتئوس، کافکا و کل پشته نرم‌افزار
          </p>
        </div>
        <div className="sys-count">
          <strong>{SECTIONS.reduce((n, s) => n + s.items.length, 0)}</strong>
          <span>جزء مستندشده</span>
        </div>
      </header>

      <div className="sys-layout">
        <nav className="sys-nav" aria-label="بخش‌های سیستم">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={active === s.id ? 'active' : ''}
              onClick={() => setActive(s.id)}
            >
              <span className="sys-nav-fa">{s.title}</span>
              <em>{s.items.length}</em>
            </button>
          ))}
        </nav>

        <section className="sys-panel">
          <div className="sys-panel-head">
            <h3>{section.title}</h3>
          </div>
          <ul className="sys-grid">
            {section.items.map((item) => (
              <li key={item.name}>
                <div className="sys-item-title">
                  <strong>{item.name}</strong>
                </div>
                <p>{item.detail}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
