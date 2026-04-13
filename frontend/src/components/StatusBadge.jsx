import clsx from 'clsx'

const statusStyles = {
  queued: 'bg-retrix-muted/20 text-retrix-muted',
  analyzing: 'bg-retrix-accent/20 text-retrix-accent',
  awaiting_approval: 'bg-yellow-500/20 text-yellow-400',
  planning: 'bg-retrix-accent2/20 text-retrix-accent2',
  in_progress: 'bg-blue-500/20 text-blue-400',
  paused: 'bg-retrix-warning/20 text-retrix-warning',
  completed: 'bg-retrix-success/20 text-retrix-success',
  failed: 'bg-retrix-danger/20 text-retrix-danger',
  held: 'bg-orange-500/20 text-orange-400',
  pending: 'bg-retrix-muted/20 text-retrix-muted',
  assigned: 'bg-indigo-500/20 text-indigo-400',
  review: 'bg-purple-500/20 text-purple-400',
}

export default function StatusBadge({ status }) {
  return (
    <span className={clsx(
      'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono uppercase tracking-wider',
      statusStyles[status] || statusStyles.queued
    )}>
      {status === 'in_progress' && <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse-live" />}
      {status?.replace('_', ' ')}
    </span>
  )
}
