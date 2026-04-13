import { useState, useEffect } from 'react'
import { Save, RotateCcw, Loader2, CheckCircle, AlertCircle, ShieldAlert } from 'lucide-react'
import { api } from '../lib/api'

const PLACEHOLDER = `## PM ABSOLUTE RULES
1. Never exceed the project budget
2. Always assign the cheapest adequate model
...`

export default function PMRules() {
  const [rules, setRules] = useState('')
  const [original, setOriginal] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null) // 'saved' | 'error'

  useEffect(() => {
    api.pmRules()
      .then((data) => {
        setRules(data.rules || '')
        setOriginal(data.rules || '')
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setStatus(null)
    try {
      await api.updatePMRules(rules)
      setOriginal(rules)
      setStatus('saved')
      setTimeout(() => setStatus(null), 3000)
    } catch (e) {
      setStatus('error')
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    setRules(original)
    setStatus(null)
  }

  const isDirty = rules !== original

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={20} className="animate-spin text-retrix-muted" />
      </div>
    )
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-retrix-text mb-1">PM Rules Editor</h2>
          <p className="text-xs text-retrix-muted">
            Edit the absolute rules that govern the PM Orchestrator. Changes take effect on the next task run.
          </p>
        </div>
        <div className="flex items-center gap-1.5 bg-retrix-warning/10 border border-retrix-warning/30 rounded-md px-3 py-1.5">
          <ShieldAlert size={12} className="text-retrix-warning" />
          <span className="text-[11px] text-retrix-warning font-medium">Admin only</span>
        </div>
      </div>

      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-medium text-retrix-muted uppercase tracking-wider">Rules (Markdown)</span>
          {isDirty && (
            <span className="text-[10px] text-retrix-warning font-mono">unsaved changes</span>
          )}
        </div>
        <textarea
          value={rules}
          onChange={(e) => setRules(e.target.value)}
          placeholder={PLACEHOLDER}
          spellCheck={false}
          className="w-full h-[480px] bg-retrix-bg border border-retrix-border rounded-md px-4 py-3 text-sm font-mono text-retrix-text focus:outline-none focus:border-retrix-accent resize-none leading-relaxed"
        />
      </div>

      <div className="flex items-center gap-3">
        {isDirty && (
          <button
            onClick={handleReset}
            className="flex items-center gap-2 px-4 py-2.5 text-sm text-retrix-muted border border-retrix-border rounded-md hover:text-retrix-text hover:border-retrix-muted transition-colors"
          >
            <RotateCcw size={14} />
            Discard
          </button>
        )}
        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          className="flex items-center gap-2 flex-1 justify-center py-2.5 bg-retrix-accent text-white text-sm rounded-md hover:bg-retrix-accent/90 transition-colors disabled:opacity-50"
        >
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          {saving ? 'Saving…' : 'Save Rules'}
        </button>
      </div>

      {status === 'saved' && (
        <div className="flex items-center gap-2 text-xs text-retrix-success mt-3">
          <CheckCircle size={13} />
          Rules saved — will apply to next orchestrator run
        </div>
      )}
      {status === 'error' && (
        <div className="flex items-center gap-2 text-xs text-retrix-danger mt-3">
          <AlertCircle size={13} />
          Failed to save rules (admin access required)
        </div>
      )}
    </div>
  )
}
