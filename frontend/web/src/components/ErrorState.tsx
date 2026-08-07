import './ErrorState.css'

interface ErrorStateProps {
  message?: string
  onRetry?: () => void
}

export default function ErrorState({ message = 'بارگذاری داده از سرور ناموفق بود.', onRetry }: ErrorStateProps) {
  return (
    <div className="error-state" dir="rtl">
      <p>{message}</p>
      {onRetry && (
        <button onClick={onRetry}>تلاش مجدد</button>
      )}
    </div>
  )
}
