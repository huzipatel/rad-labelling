interface ProgressBarProps {
  value: number
  max?: number
  showLabel?: boolean
  variant?: 'default' | 'success'
}

export default function ProgressBar({ value, max = 100, showLabel = true, variant = 'default' }: ProgressBarProps) {
  const percentage = Math.min(Math.round((value / max) * 100), 100)

  return (
    <div>
      <div className={`progress-bar ${variant === 'success' ? 'progress-bar--success' : ''}`}>
        <div className="progress-bar__fill" style={{ width: `${percentage}%` }} />
      </div>
      {showLabel && (
        <span className="govuk-body-s govuk-!-margin-top-1">
          {percentage}% ({value}/{max})
        </span>
      )}
    </div>
  )
}

