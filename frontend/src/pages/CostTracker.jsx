import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { DollarSign, ChevronDown, ChevronRight } from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

const MODEL_COLORS = {
  haiku:        '#6366f1',
  deepseek_v3:  '#22d3ee',
  deepseek_v4:  '#06b6d4',
  gpt_4o_mini:  '#10b981',
  gpt_4o:       '#f59e0b',
  minimax:      '#8b5cf6',
}

const MODEL_LABELS = {
  haiku:        'Haiku 4.5',
  deepseek_v3:  'DeepSeek V3.2',
  deepseek_v4:  'DeepSeek V4',
  gpt_4o_mini:  'GPT-4o Mini',
  gpt_4o:       'GPT-4o',
  minimax:      'MiniMax',
}

const RANGE_OPTIONS = [
  { label: '7d',  days: 7  },
  { label: '14d', days: 14 },
  { label: '30d', days: 30 },
]

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const total = payload.reduce((s, p) => s + (p.value || 0), 0)
  return (
    <div className="bg-retrix-surface border border-retrix-border rounded-lg px-3 py-2 text-xs shadow-lg">
      <p className="text-retrix-muted mb-1.5">{label}</p>
      {payload.map((p) => p.value > 0 && (
        <div key={p.dataKey} className="flex items-center gap-2 mb-0.5">
          <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: p.color }} />
          <span className="text-retrix-muted">{MODEL_LABELS[p.dataKey] || p.dataKey}</span>
          <span className="font-mono text-retrix-text ml-auto pl-3">${p.value.toFixed(4)}</span>
        </div>
      ))}
      <div className="border-t border-retrix-border mt-1.5 pt-1.5 flex justify-between">
        <span className="text-retrix-muted">Total</span>
        <span className="font-mono text-retrix-text">${total.toFixed(4)}</span>
      </div>
    </div>
  )
}

export default function CostTracker() {
  const [costs, setCosts]         = useState({})
  const [history, setHistory]     = useState([])
  const [projects, setProjects]   = useState([])
  const [projectCosts, setProjectCosts] = useState({})  // id -> {total, by_model}
  const [expandedProject, setExpandedProject] = useState(null)
  const [range, setRange]         = useState(14)
  const [loading, setLoading]     = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [c, p, h] = await Promise.all([
          api.costsToday(),
          api.listProjects(),
          api.costHistory(range),
        ])
        setCosts(c)
        setProjects(p)
        setHistory(h)
        // Fetch per-project cost breakdown
        const pcMap = {}
        await Promise.all(p.map(async (proj) => {
          try {
            pcMap[proj.id] = await api.projectCosts(proj.id)
          } catch {}
        }))
        setProjectCosts(pcMap)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [range])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-retrix-accent border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const total       = costs.total || 0
  const modelCosts  = Object.entries(costs).filter(([k]) => k !== 'total')
  const maxCost     = Math.max(...modelCosts.map(([, v]) => v), 0.001)

  // Models that appear in history
  const historyModels = [...new Set(
    history.flatMap(d => Object.keys(d).filter(k => k !== 'date' && k !== 'total'))
  )]

  // Format date label: "04/13"
  const chartData = history.map(d => ({
    ...d,
    date: d.date.slice(5), // "YYYY-MM-DD" -> "MM-DD"
  }))

  const hasHistory = history.some(d => (d.total || 0) > 0)

  return (
    <div>
      <h2 className="text-lg font-semibold text-retrix-text mb-1">Cost Tracker</h2>
      <p className="text-xs text-retrix-muted mb-6">API usage and spending history</p>

      {/* Today total */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-5 mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-retrix-warning/10">
            <DollarSign size={20} className="text-retrix-warning" />
          </div>
          <div>
            <p className="text-3xl font-bold text-retrix-text">${total.toFixed(4)}</p>
            <p className="text-xs text-retrix-muted">Total spend today</p>
          </div>
        </div>
      </div>

      {/* Daily trend chart */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-medium text-retrix-muted uppercase tracking-wider">Daily Trend</h3>
          <div className="flex gap-1">
            {RANGE_OPTIONS.map(({ label, days }) => (
              <button
                key={days}
                onClick={() => setRange(days)}
                className={`px-2 py-0.5 rounded text-xs transition-colors ${
                  range === days
                    ? 'bg-retrix-accent text-white'
                    : 'text-retrix-muted hover:text-retrix-text'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {!hasHistory ? (
          <p className="text-sm text-retrix-muted py-8 text-center">No cost data yet</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <defs>
                {historyModels.map(m => (
                  <linearGradient key={m} id={`grad-${m}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={MODEL_COLORS[m] || '#6366f1'} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={MODEL_COLORS[m] || '#6366f1'} stopOpacity={0}   />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#6b7280' }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#6b7280' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => v === 0 ? '$0' : `$${v.toFixed(3)}`}
                width={52}
              />
              <Tooltip content={<CustomTooltip />} />
              {historyModels.map(m => (
                <Area
                  key={m}
                  type="monotone"
                  dataKey={m}
                  stackId="1"
                  stroke={MODEL_COLORS[m] || '#6366f1'}
                  fill={`url(#grad-${m})`}
                  strokeWidth={1.5}
                  dot={false}
                  activeDot={{ r: 3 }}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Model breakdown */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-6">
        <h3 className="text-xs font-medium text-retrix-muted mb-4 uppercase tracking-wider">Today by Model</h3>
        {modelCosts.length === 0 ? (
          <p className="text-sm text-retrix-muted py-4 text-center">No API calls today yet</p>
        ) : (
          <div className="space-y-3">
            {modelCosts
              .sort(([, a], [, b]) => b - a)
              .map(([model, cost]) => (
                <div key={model}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-retrix-text">{MODEL_LABELS[model] || model}</span>
                    <span className="text-sm font-mono text-retrix-text">${cost.toFixed(4)}</span>
                  </div>
                  <div className="w-full h-2 bg-retrix-border rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${(cost / maxCost) * 100}%`,
                        backgroundColor: MODEL_COLORS[model] || '#6366f1',
                      }}
                    />
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Per project */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4">
        <h3 className="text-xs font-medium text-retrix-muted mb-4 uppercase tracking-wider">By Project</h3>
        {projects.length === 0 ? (
          <p className="text-sm text-retrix-muted py-4 text-center">No projects</p>
        ) : (
          <div className="space-y-1">
            {projects
              .sort((a, b) => (b.total_cost || 0) - (a.total_cost || 0))
              .map((p) => {
                const pc = projectCosts[p.id] || {}
                const byModel = Object.entries(pc.by_model || {}).sort(([, a], [, b]) => b - a)
                const isOpen = expandedProject === p.id
                return (
                  <div key={p.id} className="border-b border-retrix-border/50 last:border-0">
                    <button
                      onClick={() => setExpandedProject(isOpen ? null : p.id)}
                      className="w-full flex items-center justify-between py-2 hover:text-retrix-text text-left"
                    >
                      <div className="flex items-center gap-1.5 text-sm text-retrix-text">
                        {byModel.length > 0
                          ? (isOpen ? <ChevronDown size={12} className="text-retrix-muted" /> : <ChevronRight size={12} className="text-retrix-muted" />)
                          : <span className="w-3" />}
                        {p.name}
                      </div>
                      <span className="text-sm font-mono text-retrix-muted">${(p.total_cost || 0).toFixed(4)}</span>
                    </button>
                    {isOpen && byModel.length > 0 && (
                      <div className="pb-2 pl-5 space-y-1">
                        {byModel.map(([model, cost]) => (
                          <div key={model} className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-1.5 text-retrix-muted">
                              <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: MODEL_COLORS[model] || '#6366f1' }} />
                              {MODEL_LABELS[model] || model}
                            </span>
                            <span className="font-mono text-retrix-muted">${cost.toFixed(4)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
          </div>
        )}
      </div>
    </div>
  )
}
