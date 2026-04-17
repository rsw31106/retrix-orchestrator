import { useState, useRef, useEffect } from 'react'
import { AlertTriangle, Check, X, ClipboardList, ChevronDown, ChevronUp, Send, Loader } from 'lucide-react'
import { api } from '../lib/api'

const MODEL_OPTIONS = [
  { value: 'haiku',       label: 'Claude Haiku 4.5' },
  { value: 'gpt_4o_mini', label: 'GPT-4o Mini' },
  { value: 'deepseek_v3', label: 'DeepSeek V3' },
  { value: 'deepseek_v4', label: 'DeepSeek V4' },
  { value: 'gpt_4o',      label: 'GPT-4o' },
]

function ModelSwitchCard({ conf, onRespond }) {
  const [selectedModel, setSelectedModel] = useState(conf.suggested_model)
  return (
    <div className="bg-retrix-surface border border-retrix-warning/60 rounded-lg p-4 shadow-lg">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle size={14} className="text-retrix-warning shrink-0" />
        <span className="text-xs font-medium text-retrix-warning uppercase tracking-wider">
          Model Switch Required
        </span>
      </div>
      <p className="text-sm text-retrix-text mb-1">
        <span className="font-mono text-retrix-warning">{conf.current_model}</span>
        {' '}failed during{' '}
        <span className="font-mono text-retrix-accent">{conf.stage}</span>
        {conf.task_id && <span className="text-retrix-muted"> (task #{conf.task_id})</span>}
      </p>
      <p className="text-xs text-retrix-muted font-mono break-all mb-3">{conf.reason}</p>
      <div className="flex items-center gap-2">
        <select
          value={selectedModel}
          onChange={e => setSelectedModel(e.target.value)}
          className="flex-1 bg-retrix-bg border border-retrix-border rounded px-2 py-1 text-xs text-retrix-text focus:outline-none focus:border-retrix-accent"
        >
          {MODEL_OPTIONS.map(m => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
        <button
          onClick={() => onRespond(conf.id, true, selectedModel)}
          className="flex items-center gap-1 px-3 py-1 bg-retrix-success/10 text-retrix-success text-xs rounded hover:bg-retrix-success/20"
        >
          <Check size={12} /> Approve
        </button>
        <button
          onClick={() => onRespond(conf.id, false)}
          className="flex items-center gap-1 px-3 py-1 bg-retrix-danger/10 text-retrix-danger text-xs rounded hover:bg-retrix-danger/20"
        >
          <X size={12} /> Deny
        </button>
      </div>
    </div>
  )
}

function AnalysisReviewCard({ conf, onRespond }) {
  const [expanded, setExpanded] = useState(true)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState(conf.feedback_history || [])
  const messagesEndRef = useRef(null)

  // Sync messages when conf updates (WebSocket analysis_updated)
  useEffect(() => {
    setMessages(conf.feedback_history || [])
    setLoading(false)
  }, [conf.feedback_history])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendFeedback = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    try {
      await api.analysisFeedback(conf.id, msg)
      // loading clears when analysis_updated arrives via WebSocket (useEffect above)
    } catch (e) {
      setLoading(false)
      setMessages(prev => [...prev, { role: 'pm', content: `Error: ${e.message}` }])
    }
  }

  const requirements = conf.key_requirements || []
  const risks = conf.risks || []
  const techStack = conf.tech_stack || []

  return (
    <div className="bg-retrix-surface border border-retrix-accent/60 rounded-lg shadow-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-retrix-border">
        <ClipboardList size={14} className="text-retrix-accent shrink-0" />
        <span className="text-xs font-medium text-retrix-accent uppercase tracking-wider flex-1">
          PM Analysis — Review &amp; Approve
        </span>
        <span className="text-[10px] text-retrix-muted font-mono">project #{conf.project_id}</span>
      </div>

      <div className="p-4 space-y-3">
        {/* Summary */}
        {conf.summary && (
          <p className="text-xs text-retrix-text leading-relaxed">{conf.summary}</p>
        )}

        {/* Meta row */}
        <div className="flex flex-wrap gap-2 text-xs font-mono">
          {conf.project_type && (
            <span className="px-2 py-0.5 bg-retrix-accent/10 text-retrix-accent rounded">
              {conf.project_type}
            </span>
          )}
          {conf.complexity && (
            <span className="px-2 py-0.5 bg-retrix-border text-retrix-muted rounded">
              complexity: {conf.complexity}
            </span>
          )}
          {conf.tasks_estimate && (
            <span className="px-2 py-0.5 bg-retrix-border text-retrix-muted rounded">
              ~{conf.tasks_estimate} tasks
            </span>
          )}
        </div>

        {/* Expandable details */}
        {(requirements.length > 0 || risks.length > 0 || techStack.length > 0) && (
          <>
            <button
              onClick={() => setExpanded(v => !v)}
              className="flex items-center gap-1 text-xs text-retrix-muted hover:text-retrix-text"
            >
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {expanded ? 'Hide details' : 'Show details'}
            </button>

            {expanded && (
              <div className="space-y-3 bg-retrix-bg rounded-md p-3">
                {requirements.length > 0 && (
                  <div>
                    <p className="text-[10px] text-retrix-muted uppercase tracking-wider mb-1.5">Requirements</p>
                    <ul className="space-y-1">
                      {requirements.map((r, i) => (
                        <li key={i} className="text-xs text-retrix-text flex gap-1.5">
                          <span className="text-retrix-accent shrink-0 mt-0.5">·</span>
                          <span>{typeof r === 'string' ? r : JSON.stringify(r)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {risks.length > 0 && (
                  <div>
                    <p className="text-[10px] text-retrix-muted uppercase tracking-wider mb-1.5">Risks</p>
                    <ul className="space-y-1">
                      {risks.map((r, i) => (
                        <li key={i} className="text-xs text-retrix-warning flex gap-1.5">
                          <span className="shrink-0">⚠</span>
                          <span>{typeof r === 'string' ? r : JSON.stringify(r)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {techStack.length > 0 && (
                  <div>
                    <p className="text-[10px] text-retrix-muted uppercase tracking-wider mb-1.5">Tech Stack</p>
                    <div className="flex flex-wrap gap-1">
                      {techStack.map((t, i) => (
                        <span key={i} className="text-[10px] font-mono px-1.5 py-0.5 bg-retrix-surface text-retrix-muted rounded border border-retrix-border">
                          {typeof t === 'string' ? t : JSON.stringify(t)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Feedback chat */}
        <div className="border border-retrix-border rounded-md overflow-hidden focus-within:border-retrix-accent/50 transition-colors">
          <div className="bg-retrix-bg px-3 py-1.5 border-b border-retrix-border">
            <p className="text-[10px] text-retrix-muted uppercase tracking-wider">Feedback to PM</p>
          </div>

          {/* Message history */}
          {messages.length > 0 && (
            <div className="max-h-40 overflow-y-auto p-2 space-y-2">
              {messages.map((m, i) => (
                <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] text-xs px-2.5 py-1.5 rounded-lg leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-retrix-accent/20 text-retrix-text'
                      : 'bg-retrix-border text-retrix-text'
                  }`}>
                    <span className="text-[10px] font-mono text-retrix-muted block mb-0.5">
                      {m.role === 'user' ? 'You' : 'PM'}
                    </span>
                    {m.content}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex gap-2 justify-start">
                  <div className="bg-retrix-border text-retrix-muted text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1.5">
                    <Loader size={10} className="animate-spin" />
                    PM is revising analysis…
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Input */}
          <div className="flex border-t border-retrix-border bg-retrix-bg">
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendFeedback()}
              placeholder="e.g. Add Redis caching, use TypeScript instead of JS…"
              disabled={loading}
              className="flex-1 bg-transparent px-3 py-2 text-xs text-retrix-text placeholder-retrix-muted/60 focus:outline-none disabled:opacity-50"
            />
            <button
              onClick={sendFeedback}
              disabled={!input.trim() || loading}
              className="px-3 py-2 text-retrix-accent hover:text-retrix-accent/70 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <Send size={13} />
            </button>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-retrix-border bg-retrix-bg">
        <button
          onClick={() => onRespond(conf.id, true, null)}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-retrix-accent text-white text-xs rounded hover:bg-retrix-accent/90 font-medium"
        >
          <Check size={12} /> Approve &amp; Start Tasks
        </button>
        <button
          onClick={() => onRespond(conf.id, false)}
          className="flex items-center gap-1 px-3 py-2 bg-retrix-danger/10 text-retrix-danger text-xs rounded hover:bg-retrix-danger/20"
        >
          <X size={12} /> Reject
        </button>
      </div>
    </div>
  )
}

export default function ConfirmationPanel({ confirmations, onRespond }) {
  if (confirmations.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 w-[480px] space-y-3 max-h-[90vh] overflow-y-auto">
      {confirmations.map((conf) =>
        conf.confirmation_type === 'analysis_review'
          ? <AnalysisReviewCard key={conf.id} conf={conf} onRespond={onRespond} />
          : <ModelSwitchCard key={conf.id} conf={conf} onRespond={onRespond} />
      )}
    </div>
  )
}
