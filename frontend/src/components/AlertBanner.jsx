import { X, AlertTriangle, AlertCircle, Info } from 'lucide-react'
import clsx from 'clsx'

const levelConfig = {
  critical: { icon: AlertCircle, bg: 'bg-retrix-danger/10', border: 'border-retrix-danger/30', text: 'text-retrix-danger' },
  error: { icon: AlertTriangle, bg: 'bg-retrix-danger/10', border: 'border-retrix-danger/30', text: 'text-retrix-danger' },
  warning: { icon: AlertTriangle, bg: 'bg-retrix-warning/10', border: 'border-retrix-warning/30', text: 'text-retrix-warning' },
  info: { icon: Info, bg: 'bg-retrix-accent/10', border: 'border-retrix-accent/30', text: 'text-retrix-accent' },
}

export default function AlertBanner({ alert, onDismiss }) {
  const config = levelConfig[alert.level] || levelConfig.info
  const Icon = config.icon

  return (
    <div className={clsx('flex items-center gap-3 px-4 py-2.5 border-b text-sm', config.bg, config.border)}>
      <Icon size={16} className={config.text} />
      <span className={clsx('flex-1', config.text)}>{alert.message}</span>
      <button onClick={onDismiss} className="text-retrix-muted hover:text-retrix-text">
        <X size={14} />
      </button>
    </div>
  )
}
