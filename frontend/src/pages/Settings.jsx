import { useState, useEffect } from 'react'
import { Save, Cpu, Users, Loader2, CheckCircle, AlertCircle, Bell } from 'lucide-react'
import { api } from '../lib/api'

function Toggle({ checked, onChange }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`w-9 h-5 rounded-full transition-colors relative ${
        checked ? 'bg-retrix-success' : 'bg-retrix-border'
      }`}
    >
      <span
        className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
          checked ? 'translate-x-4' : 'translate-x-0.5'
        }`}
      />
    </button>
  )
}

export default function Settings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null) // 'saved' | 'error'

  const [dailyBudget, setDailyBudget] = useState('')
  const [projectBudget, setProjectBudget] = useState('')
  const [slackWebhook, setSlackWebhook] = useState('')
  const [models, setModels] = useState({})
  const [workers, setWorkers] = useState({})

  useEffect(() => {
    api.getSettings()
      .then((data) => {
        setDailyBudget(data.daily_budget ?? '')
        setProjectBudget(data.project_budget ?? '')
        setSlackWebhook(data.slack_webhook ?? '')
        // Index models/workers by key
        const mMap = {}
        ;(data.models || []).forEach((m) => { mMap[m.key] = m })
        setModels(mMap)
        const wMap = {}
        ;(data.workers || []).forEach((w) => { wMap[w.key] = w })
        setWorkers(wMap)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const toggleModel = (key) => {
    setModels((prev) => ({
      ...prev,
      [key]: { ...prev[key], enabled: !prev[key]?.enabled },
    }))
  }

  const toggleWorker = (key) => {
    setWorkers((prev) => ({
      ...prev,
      [key]: { ...prev[key], enabled: !prev[key]?.enabled },
    }))
  }

  const handleSave = async () => {
    setSaving(true)
    setStatus(null)
    try {
      const modelsPayload = {}
      Object.entries(models).forEach(([k, v]) => {
        modelsPayload[k] = { enabled: v.enabled }
      })
      const workersPayload = {}
      Object.entries(workers).forEach(([k, v]) => {
        workersPayload[k] = { enabled: v.enabled, priority: v.priority, fallback_worker: v.fallback_worker }
      })
      await api.updateSettings({
        daily_budget: dailyBudget === '' ? null : parseFloat(dailyBudget),
        project_budget: projectBudget === '' ? null : parseFloat(projectBudget),
        slack_webhook: slackWebhook || null,
        models: modelsPayload,
        workers: workersPayload,
      })
      setStatus('saved')
      setTimeout(() => setStatus(null), 3000)
    } catch (e) {
      setStatus('error')
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={20} className="animate-spin text-retrix-muted" />
      </div>
    )
  }

  const modelOrder = ['haiku', 'deepseek_v3', 'deepseek_v4', 'gpt_4o_mini', 'gpt_4o', 'minimax']
  const modelLabels = {
    haiku: 'Haiku 4.5',
    deepseek_v3: 'DeepSeek V3',
    deepseek_v4: 'DeepSeek V4',
    gpt_4o_mini: 'GPT-4o Mini',
    gpt_4o: 'GPT-4o',
    minimax: 'MiniMax',
  }
  const workerOrder = ['claude_code', 'cursor', 'codex', 'gemini_cli', 'antigravity']
  const workerLabels = {
    claude_code: 'Claude Code',
    cursor: 'Cursor',
    codex: 'Codex',
    gemini_cli: 'Gemini CLI',
    antigravity: 'Antigravity',
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-lg font-semibold text-retrix-text mb-1">Settings</h2>
      <p className="text-xs text-retrix-muted mb-6">Configure budgets, models, and workers</p>

      {/* Budget */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
        <h3 className="text-xs font-medium text-retrix-muted mb-4 uppercase tracking-wider">Budget Limits</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-retrix-muted mb-1.5">Daily Limit (USD)</label>
            <input
              type="number"
              step="0.5"
              min="0"
              placeholder="No limit"
              value={dailyBudget}
              onChange={(e) => setDailyBudget(e.target.value)}
              className="w-full bg-retrix-bg border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text focus:outline-none focus:border-retrix-accent"
            />
          </div>
          <div>
            <label className="block text-xs text-retrix-muted mb-1.5">Per-Project Limit (USD)</label>
            <input
              type="number"
              step="0.5"
              min="0"
              placeholder="No limit"
              value={projectBudget}
              onChange={(e) => setProjectBudget(e.target.value)}
              className="w-full bg-retrix-bg border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text focus:outline-none focus:border-retrix-accent"
            />
          </div>
        </div>
      </div>

      {/* Model Pool */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
        <div className="flex items-center gap-2 mb-4">
          <Cpu size={14} className="text-retrix-accent" />
          <h3 className="text-xs font-medium text-retrix-muted uppercase tracking-wider">Model Pool</h3>
        </div>
        <div className="space-y-1">
          {modelOrder.map((key) => {
            const m = models[key] || {}
            return (
              <div key={key} className="flex items-center justify-between py-2 border-b border-retrix-border/50 last:border-0">
                <div>
                  <span className={`text-sm ${m.enabled === false ? 'text-retrix-muted line-through' : 'text-retrix-text'}`}>
                    {modelLabels[key] || key}
                  </span>
                  {m.input_price !== undefined && (
                    <span className="text-[10px] font-mono text-retrix-muted ml-2">
                      {m.input_price === 0 ? 'flat rate' : `$${m.input_price}/$${m.output_price} per 1M`}
                    </span>
                  )}
                </div>
                <Toggle checked={m.enabled !== false} onChange={() => toggleModel(key)} />
              </div>
            )
          })}
        </div>
      </div>

      {/* Workers */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
        <div className="flex items-center gap-2 mb-4">
          <Users size={14} className="text-retrix-accent2" />
          <h3 className="text-xs font-medium text-retrix-muted uppercase tracking-wider">Worker Pool</h3>
        </div>
        <div className="space-y-1">
          {workerOrder.map((key) => {
            const w = workers[key] || {}
            return (
              <div key={key} className="flex items-center justify-between py-2 border-b border-retrix-border/50 last:border-0">
                <div>
                  <span className={`text-sm ${w.enabled === false ? 'text-retrix-muted line-through' : 'text-retrix-text'}`}>
                    {workerLabels[key] || key}
                  </span>
                  {w.fallback_worker && (
                    <span className="text-[10px] font-mono text-retrix-muted ml-2">
                      fallback → {w.fallback_worker}
                    </span>
                  )}
                </div>
                <Toggle checked={w.enabled !== false} onChange={() => toggleWorker(key)} />
              </div>
            )
          })}
        </div>
      </div>

      {/* Notifications */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
        <div className="flex items-center gap-2 mb-4">
          <Bell size={14} className="text-retrix-warning" />
          <h3 className="text-xs font-medium text-retrix-muted uppercase tracking-wider">Notifications</h3>
        </div>
        <div>
          <label className="block text-xs text-retrix-muted mb-1.5">Slack Webhook URL</label>
          <input
            type="url"
            placeholder="https://hooks.slack.com/services/..."
            value={slackWebhook}
            onChange={(e) => setSlackWebhook(e.target.value)}
            className="w-full bg-retrix-bg border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text focus:outline-none focus:border-retrix-accent font-mono"
          />
          <p className="text-[11px] text-retrix-muted mt-1.5">
            Notified on: project complete, project failed, 80% daily budget
          </p>
        </div>
      </div>

      {/* Status + Save */}
      {status === 'saved' && (
        <div className="flex items-center gap-2 text-xs text-retrix-success mb-3">
          <CheckCircle size={13} />
          Settings saved successfully
        </div>
      )}
      {status === 'error' && (
        <div className="flex items-center gap-2 text-xs text-retrix-danger mb-3">
          <AlertCircle size={13} />
          Failed to save settings
        </div>
      )}
      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center justify-center gap-2 w-full py-2.5 bg-retrix-accent text-white text-sm rounded-md hover:bg-retrix-accent/90 transition-colors disabled:opacity-60"
      >
        {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
        {saving ? 'Saving…' : 'Save Settings'}
      </button>
    </div>
  )
}
