import { useEffect, useState, useRef } from 'react'
import { api } from '../lib/api'
import { Bot, Wrench, Cpu, User, RefreshCw } from 'lucide-react'

const ACTOR_CONFIG = {
  pm:     { icon: Bot,     color: 'text-retrix-accent',   bg: 'bg-retrix-accent/15',   label: 'PM' },
  worker: { icon: Wrench,  color: 'text-retrix-success',  bg: 'bg-retrix-success/15',  label: 'Worker' },
  system: { icon: Cpu,     color: 'text-retrix-muted',    bg: 'bg-retrix-border',      label: 'System' },
  user:   { icon: User,    color: 'text-retrix-warning',  bg: 'bg-retrix-warning/15',  label: 'User' },
}

function getActorConfig(type) {
  return ACTOR_CONFIG[type] || ACTOR_CONFIG.system
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'Z')
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'Z')
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function LiveEntry({ entry }) {
  const cfg = getActorConfig(entry.actor_type)
  const Icon = cfg.icon
  return (
    <div className="flex gap-3 py-2.5 border-b border-retrix-border/40 last:border-0 items-start group">
      <div className={`w-7 h-7 rounded-full ${cfg.bg} flex items-center justify-center shrink-0 mt-0.5`}>
        <Icon size={13} className={cfg.color} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
          <span className={`text-xs font-semibold ${cfg.color}`}>{entry.actor_name}</span>
          <span className="text-xs text-retrix-muted">{entry.action}</span>
        </div>
        {entry.detail && typeof entry.detail === 'object' && Object.keys(entry.detail).length > 0 && (
          <p className="text-[11px] text-retrix-muted font-mono truncate">
            {Object.entries(entry.detail)
              .filter(([, v]) => typeof v === 'string' || typeof v === 'number')
              .slice(0, 2)
              .map(([k, v]) => `${k}: ${v}`)
              .join(' | ')}
          </p>
        )}
      </div>
      <div className="text-[10px] text-retrix-muted shrink-0 text-right leading-5 pt-0.5">
        <div>{formatTime(entry.created_at)}</div>
        <div className="text-retrix-border">{formatDate(entry.created_at)}</div>
      </div>
    </div>
  )
}

// Translate WS event to activity entry format
function wsEventToEntry(msg) {
  const now = new Date().toISOString()
  if (msg.type === 'project_update') {
    const d = msg.data || {}
    return {
      id: `ws-${Date.now()}`,
      actor_type: 'system',
      actor_name: 'Orchestrator',
      action: `Project ${d.project_id}: ${d.status || d.message || 'update'}`,
      detail: d,
      created_at: now,
    }
  }
  if (msg.type === 'task_update') {
    const d = msg.data || {}
    return {
      id: `ws-${Date.now()}`,
      actor_type: 'worker',
      actor_name: d.worker || 'Worker',
      action: `Task ${d.task_id}: ${d.status || 'update'}`,
      detail: d,
      created_at: now,
    }
  }
  if (msg.type === 'worker_update') {
    const d = msg.data || {}
    return {
      id: `ws-${Date.now()}`,
      actor_type: 'worker',
      actor_name: d.worker || 'Worker',
      action: d.status === 'working' ? `Working on task ${d.task_id}` : 'Idle',
      detail: d,
      created_at: now,
    }
  }
  if (msg.type === 'activity') {
    return { id: `ws-${Date.now()}`, ...msg.data }
  }
  return null
}

const ACTOR_FILTERS = [
  { value: '', label: 'All' },
  { value: 'pm', label: 'PM' },
  { value: 'worker', label: 'Workers' },
  { value: 'system', label: 'System' },
  { value: 'user', label: 'Users' },
]

export default function ActivityLog({ subscribe }) {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')
  const [liveEntries, setLiveEntries] = useState([])
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef(null)

  const load = async (actorType = filter) => {
    setLoading(true)
    try {
      const res = await api.getActivity({ limit: 200, actor_type: actorType || undefined })
      setLogs(res.logs)
      setTotal(res.total)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (!subscribe) return
    return subscribe('activity-log', (msg) => {
      const entry = wsEventToEntry(msg)
      if (!entry) return
      if (filter && entry.actor_type !== filter) return
      setLiveEntries(prev => [entry, ...prev].slice(0, 200))
    })
  }, [subscribe, filter])

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveEntries])

  const handleFilterChange = (val) => {
    setFilter(val)
    setLiveEntries([])
    load(val)
  }

  const allEntries = [...liveEntries, ...logs]

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-retrix-text mb-1">Activity Log</h2>
          <p className="text-xs text-retrix-muted">Real-time feed of PM, worker, and system events</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Live indicator */}
          <div className="flex items-center gap-1.5 text-xs text-retrix-success">
            <span className="w-1.5 h-1.5 rounded-full bg-retrix-success animate-pulse-live" />
            Live
          </div>
          <button
            onClick={() => load()}
            className="p-2 text-retrix-muted hover:text-retrix-text transition-colors"
            title="Refresh"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-1 mb-4">
        {ACTOR_FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => handleFilterChange(f.value)}
            className={`px-3 py-1 rounded-full text-xs transition-colors ${
              filter === f.value
                ? 'bg-retrix-accent text-white'
                : 'bg-retrix-surface border border-retrix-border text-retrix-muted hover:text-retrix-text'
            }`}
          >
            {f.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-retrix-muted self-center">{total} total</span>
      </div>

      {/* Live badge */}
      {liveEntries.length > 0 && (
        <div className="text-xs text-retrix-accent mb-2 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-retrix-accent animate-pulse-live" />
          {liveEntries.length} new live event{liveEntries.length > 1 ? 's' : ''}
        </div>
      )}

      {/* Log feed */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg px-4 py-2">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-5 h-5 border-2 border-retrix-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : allEntries.length === 0 ? (
          <p className="text-sm text-retrix-muted text-center py-8">No activity yet</p>
        ) : (
          allEntries.map((entry, i) => <LiveEntry key={entry.id || i} entry={entry} />)
        )}
        <div ref={bottomRef} />
      </div>

      {/* Auto-scroll toggle */}
      <div className="mt-3 flex items-center justify-end gap-2">
        <label className="flex items-center gap-2 text-xs text-retrix-muted cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={e => setAutoScroll(e.target.checked)}
            className="accent-retrix-accent"
          />
          Auto-scroll on live events
        </label>
      </div>
    </div>
  )
}
