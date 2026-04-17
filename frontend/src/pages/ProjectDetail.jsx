import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import {
  ArrowLeft, Pause, Play, Trash2, RotateCcw, Hand,
  ChevronDown, ChevronRight, Clock, Cpu, AlertTriangle, Loader,
  RefreshCw, BookOpen, CheckCircle, XCircle, Link, MoreHorizontal,
  ShieldCheck, Save, Pencil, MessageSquare, Send, PlusCircle, ArchiveRestore, Archive,
} from 'lucide-react'
import clsx from 'clsx'

function TasksSection({ tasks, onRetry, onHold, onDelete, onArchive, onUnarchive, onUpdateInstruction, onStatusChange }) {
  const [showArchived, setShowArchived] = useState(false)

  const visible = tasks.filter(t => showArchived ? t.archived : !t.archived)
  const archivedCount = tasks.filter(t => t.archived).length

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-retrix-muted">
          Tasks ({visible.length}{archivedCount > 0 && !showArchived ? ` / ${archivedCount} archived` : ''})
        </h3>
        {archivedCount > 0 && (
          <button
            onClick={() => setShowArchived(v => !v)}
            className="flex items-center gap-1.5 text-[11px] text-retrix-muted hover:text-retrix-text transition-colors"
          >
            {showArchived
              ? <><XCircle size={11} /> Hide archived</>
              : <><Archive size={11} /> Show archived ({archivedCount})</>
            }
          </button>
        )}
      </div>
      <div className="space-y-2">
        {visible.map(task => (
          <TaskRow
            key={task.id}
            task={task}
            onRetry={onRetry}
            onHold={onHold}
            onDelete={onDelete}
            onArchive={onArchive}
            onUnarchive={onUnarchive}
            onUpdateInstruction={onUpdateInstruction}
            onStatusChange={onStatusChange}
          />
        ))}
        {visible.length === 0 && (
          <p className="text-xs text-retrix-muted text-center py-4">
            {showArchived ? '보관된 태스크가 없습니다.' : '진행 중인 태스크가 없습니다.'}
          </p>
        )}
      </div>
    </div>
  )
}


function AddFeaturesPanel({ projectId, onDone }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleSubmit = async () => {
    if (!text.trim() || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.addFeatures(projectId, text.trim())
      setResult(res)
      setText('')
      onDone?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-retrix-surface border border-retrix-border rounded-lg mb-4 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-retrix-bg/50 transition-colors"
      >
        <PlusCircle size={13} className="text-retrix-accent shrink-0" />
        <span className="text-xs font-medium text-retrix-accent flex-1 text-left">Add Features / New Tasks</span>
        {open ? <ChevronDown size={12} className="text-retrix-muted" /> : <ChevronRight size={12} className="text-retrix-muted" />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3 border-t border-retrix-border">
          <p className="text-[11px] text-retrix-muted pt-3">
            PM이 내용을 분석해 태스크를 생성하고 바로 작업을 시작합니다.
          </p>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && e.metaKey && handleSubmit()}
            placeholder={'예시:\n- 로그인 화면에 소셜 로그인 추가 (Google, Apple)\n- 결제 모듈 Stripe로 교체\n- 다크모드 지원'}
            rows={5}
            disabled={loading}
            className="w-full bg-retrix-bg border border-retrix-border rounded-md px-3 py-2 text-xs text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent font-mono resize-y disabled:opacity-50"
          />
          {error && <p className="text-xs text-retrix-danger">{error}</p>}
          {result && (
            <p className="text-xs text-retrix-success">
              ✓ {result.tasks_created}개 태스크 생성됨: {result.task_titles?.join(', ')}
            </p>
          )}
          <button
            onClick={handleSubmit}
            disabled={!text.trim() || loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-retrix-accent text-white text-xs rounded hover:bg-retrix-accent/90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? <Loader size={11} className="animate-spin" /> : <Send size={11} />}
            {loading ? 'PM이 태스크 분석 중…' : '태스크 생성 및 시작'}
          </button>
        </div>
      )}
    </div>
  )
}

const STATUS_OPTIONS = [
  { value: 'pending',     label: 'Pending',     color: 'text-retrix-muted' },
  { value: 'review',      label: 'Review',      color: 'text-retrix-accent2' },
  { value: 'completed',   label: 'Completed',   color: 'text-retrix-success' },
  { value: 'failed',      label: 'Failed',      color: 'text-retrix-danger' },
  { value: 'held',        label: 'Held',        color: 'text-retrix-warning' },
]

function TaskStatusMenu({ taskId, currentStatus, onStatusChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setOpen(!open)}
        className="p-1 rounded text-retrix-muted hover:text-retrix-text hover:bg-white/[0.05] transition-colors"
        title="Change status"
      >
        <MoreHorizontal size={14} />
      </button>
      {open && (
        <div className="absolute right-0 top-6 z-50 bg-retrix-surface border border-retrix-border rounded-lg shadow-lg py-1 min-w-[130px]">
          <p className="text-[10px] text-retrix-muted px-3 py-1 border-b border-retrix-border mb-1">Set status</p>
          {STATUS_OPTIONS.filter(o => o.value !== currentStatus).map(opt => (
            <button
              key={opt.value}
              onClick={async () => { setOpen(false); await onStatusChange(taskId, opt.value) }}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-white/[0.05] ${opt.color}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const STAGE_LABELS = {
  analyzing:          { text: 'Analyzing spec document…',                       active: true },
  awaiting_approval:  { text: 'Analysis complete — waiting for your approval…', active: true },
  planning:           { text: 'Decomposing into tasks…',                         active: true },
  in_progress:        { text: 'Generating instructions & dispatching workers…',  active: true },
  paused:             { text: 'Paused',                                           active: false },
  completed:          { text: 'All tasks completed',                              active: false },
  failed:             { text: 'One or more tasks failed',                         active: false },
}

function OrchestrationBanner({ status }) {
  const info = STAGE_LABELS[status]
  if (!info) return null
  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-md text-xs mb-4 ${
      info.active
        ? 'bg-retrix-accent/10 text-retrix-accent border border-retrix-accent/20'
        : status === 'completed'
          ? 'bg-retrix-success/10 text-retrix-success border border-retrix-success/20'
          : 'bg-retrix-danger/10 text-retrix-danger border border-retrix-danger/20'
    }`}>
      {info.active && <Loader size={12} className="animate-spin shrink-0" />}
      <span>{info.text}</span>
    </div>
  )
}

function useElapsedTime(startedAt) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!startedAt) return
    const start = new Date(startedAt + (startedAt.endsWith('Z') ? '' : 'Z')).getTime()
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startedAt])
  if (elapsed < 60) return `${elapsed}s`
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
  return `${Math.floor(elapsed / 3600)}h ${Math.floor((elapsed % 3600) / 60)}m`
}

function ProcessStatusBadge({ taskId, startedAt }) {
  const [procStatus, setProcStatus] = useState(null) // null=loading, {alive,pid}
  const elapsed = useElapsedTime(startedAt)

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        const s = await api.taskProcessStatus(taskId)
        if (!cancelled) setProcStatus(s)
      } catch {
        if (!cancelled) setProcStatus({ alive: false, pid: null })
      }
    }
    check()
    const id = setInterval(check, 15000)
    return () => { cancelled = true; clearInterval(id) }
  }, [taskId])

  const dot = procStatus === null
    ? 'bg-retrix-muted animate-pulse'
    : procStatus.alive
      ? 'bg-retrix-success'
      : 'bg-retrix-danger'

  const label = procStatus === null
    ? 'checking…'
    : procStatus.alive
      ? `PID ${procStatus.pid}`
      : 'no process'

  return (
    <span
      className="flex items-center gap-1.5 text-[10px] font-mono text-retrix-muted"
      title={procStatus?.alive ? `Subprocess PID ${procStatus.pid} is running` : 'No active subprocess found — may have crashed or not started yet'}
    >
      <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} />
      <span className="text-retrix-text/70">{elapsed}</span>
      <span className="text-retrix-muted/60">{label}</span>
    </span>
  )
}

function TaskRow({ task, onRetry, onHold, onDelete, onArchive, onUnarchive, onUpdateInstruction, onStatusChange }) {
  const [expanded, setExpanded] = useState(false)
  const [editingInstruction, setEditingInstruction] = useState(false)
  const [instructionDraft, setInstructionDraft] = useState(task.instruction || '')
  const [saving, setSaving] = useState(false)
  const hasFallback = task.fallback_history && task.fallback_history.length > 0

  const saveInstruction = async () => {
    setSaving(true)
    try {
      await onUpdateInstruction(task.id, instructionDraft)
      setEditingInstruction(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border border-retrix-border rounded-lg">
      <div
        className="flex items-center gap-3 p-3 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown size={14} className="text-retrix-muted" /> : <ChevronRight size={14} className="text-retrix-muted" />}

        <span className="flex-1 text-sm text-retrix-text truncate">{task.title}</span>

        {task.assigned_worker && (
          <span className="text-[10px] font-mono text-retrix-accent2 bg-retrix-accent2/10 px-1.5 py-0.5 rounded">
            {task.assigned_worker}
          </span>
        )}

        {task.status === 'in_progress' && (
          <ProcessStatusBadge taskId={task.id} startedAt={task.started_at} />
        )}

        {task.scheduled_retry_at && (
          <span className="text-[10px] font-mono text-retrix-accent2 flex items-center gap-1" title={`Rate limited — auto retry at ${new Date(task.scheduled_retry_at + 'Z').toLocaleString()}`}>
            <Clock size={10} /> {new Date(task.scheduled_retry_at + 'Z').toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}
          </span>
        )}
        {task.retry_count > 0 && (
          <span className="text-[10px] font-mono text-retrix-warning flex items-center gap-1">
            <RotateCcw size={10} /> {task.retry_count}
          </span>
        )}

        <StatusBadge status={task.status} />

        {/* Actions */}
        <div className="flex gap-1 ml-2" onClick={(e) => e.stopPropagation()}>
          {task.status === 'completed' && !task.archived && (
            <button
              onClick={() => onArchive(task.id)}
              className="p-1 rounded text-retrix-muted hover:bg-white/[0.05]"
              title="Archive task"
            >
              <Archive size={14} />
            </button>
          )}
          {task.archived && (
            <button
              onClick={() => onUnarchive(task.id)}
              className="p-1 rounded text-retrix-accent2 hover:bg-retrix-accent2/10"
              title="Unarchive task"
            >
              <ArchiveRestore size={14} />
            </button>
          )}
          {task.status === 'held' && (
            <button
              onClick={() => onDelete(task.id)}
              className="p-1 rounded text-retrix-danger hover:bg-retrix-danger/10"
              title="Delete task"
            >
              <Trash2 size={14} />
            </button>
          )}
          {(task.status === 'failed' || task.status === 'held') && (
            <>
              <button
                onClick={() => onRetry(task.id)}
                className="p-1 rounded text-retrix-accent hover:bg-retrix-accent/10"
                title="Retry"
              >
                <RotateCcw size={14} />
              </button>
              {task.status !== 'held' && (
                <button
                  onClick={() => onHold(task.id)}
                  className="p-1 rounded text-retrix-warning hover:bg-retrix-warning/10"
                  title="Hold"
                >
                  <Hand size={14} />
                </button>
              )}
            </>
          )}
          <TaskStatusMenu taskId={task.id} currentStatus={task.status} onStatusChange={onStatusChange} />
        </div>
      </div>

      {expanded && (
        <div className="border-t border-retrix-border p-3 bg-retrix-bg/50 text-xs space-y-2">
          {task.assigned_model && (
            <div className="flex gap-2">
              <Cpu size={12} className="text-retrix-muted mt-0.5" />
              <span className="text-retrix-muted">Model: <span className="text-retrix-text">{task.assigned_model}</span></span>
            </div>
          )}

          {(task.instruction || task.status === 'held') && (
            <div className="mt-2">
              <div className="flex items-center justify-between mb-1">
                <p className="text-retrix-muted font-medium">Instruction:</p>
                {task.status === 'held' && !editingInstruction && (
                  <button
                    onClick={() => { setInstructionDraft(task.instruction || ''); setEditingInstruction(true) }}
                    className="text-retrix-accent hover:underline"
                  >
                    Edit
                  </button>
                )}
              </div>
              {editingInstruction ? (
                <div className="space-y-2">
                  <textarea
                    value={instructionDraft}
                    onChange={e => setInstructionDraft(e.target.value)}
                    className="w-full bg-retrix-bg border border-retrix-accent/40 rounded p-2 font-mono text-retrix-text text-xs resize-y focus:outline-none focus:border-retrix-accent"
                    rows={6}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={saveInstruction}
                      disabled={saving}
                      className="px-3 py-1 bg-retrix-accent text-white rounded text-xs disabled:opacity-50"
                    >
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      onClick={async () => {
                        setSaving(true)
                        try {
                          await onUpdateInstruction(task.id, instructionDraft)
                          setEditingInstruction(false)
                          await onRetry(task.id)
                        } finally {
                          setSaving(false)
                        }
                      }}
                      disabled={saving}
                      className="px-3 py-1 bg-retrix-success/10 text-retrix-success rounded text-xs disabled:opacity-50"
                    >
                      Save & Retry
                    </button>
                    <button
                      onClick={() => setEditingInstruction(false)}
                      className="px-3 py-1 text-retrix-muted rounded text-xs hover:text-retrix-text"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <pre className="bg-retrix-bg border border-retrix-border rounded p-2 font-mono text-retrix-text whitespace-pre-wrap break-words max-h-40 overflow-y-auto">{task.instruction}</pre>
              )}
            </div>
          )}

          {task.result && (
            <div className="mt-2">
              <p className="text-retrix-muted mb-1 font-medium">Result:</p>
              <pre className="bg-retrix-bg border border-retrix-border rounded p-2 font-mono text-retrix-text whitespace-pre-wrap break-words max-h-40 overflow-y-auto">{task.result}</pre>
            </div>
          )}

          {task.error_message && (
            <div className="flex gap-2">
              <AlertTriangle size={12} className="text-retrix-danger mt-0.5" />
              <span className="text-retrix-danger font-mono">{task.error_message}</span>
            </div>
          )}

          {hasFallback && (
            <div className="mt-2">
              <p className="text-retrix-muted mb-1 font-medium">Fallback History:</p>
              <div className="space-y-1">
                {task.fallback_history.map((fb, i) => (
                  <div key={i} className="flex items-center gap-2 text-retrix-muted font-mono pl-3">
                    <span className="text-retrix-warning">#{fb.attempt}</span>
                    <span>{fb.action}</span>
                    {fb.from_worker && <span>from {fb.from_worker}</span>}
                    {fb.to_worker && <span>→ {fb.to_worker}</span>}
                    <span className="text-retrix-muted/50">{fb.reason}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function NotionSyncPanel({ projectId, notionPageUrl, notionLastSynced, onSynced }) {
  const [syncing, setSyncing] = useState(false)
  const [preview, setPreview] = useState(null) // null | { changed, pm_analysis, new_hash } | { changed: false }
  const [applying, setApplying] = useState(false)
  const [connectUrl, setConnectUrl] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [showConnect, setShowConnect] = useState(false)
  const [error, setError] = useState(null)

  const handleConnect = async () => {
    if (!connectUrl.trim()) return
    setConnecting(true)
    setError(null)
    try {
      await api.notionConnect(projectId, connectUrl.trim())
      setShowConnect(false)
      setConnectUrl('')
      onSynced()
    } catch (e) {
      setError(e.message)
    } finally {
      setConnecting(false)
    }
  }

  const handleSyncPreview = async () => {
    setSyncing(true)
    setPreview(null)
    setError(null)
    try {
      const result = await api.notionSyncPreview(projectId)
      setPreview(result)
    } catch (e) {
      setError(e.message)
    } finally {
      setSyncing(false)
    }
  }

  const handleApply = async () => {
    if (!preview?.pm_analysis) return
    setApplying(true)
    setError(null)
    try {
      const result = await api.notionSyncApply(projectId, true, preview.pm_analysis)
      setPreview(null)
      onSynced()
      alert(`Sync applied! ${result.tasks_created} new task(s) created.`)
    } catch (e) {
      setError(e.message)
    } finally {
      setApplying(false)
    }
  }

  const handleCancel = async () => {
    await api.notionSyncApply(projectId, false, '')
    setPreview(null)
  }

  return (
    <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <BookOpen size={14} className="text-retrix-accent" />
          <h3 className="text-xs font-medium text-retrix-muted uppercase tracking-wider">Notion Integration</h3>
        </div>
        {notionPageUrl ? (
          <button
            onClick={handleSyncPreview}
            disabled={syncing}
            className="flex items-center gap-1.5 px-3 py-1 text-xs bg-retrix-accent/10 text-retrix-accent rounded-md hover:bg-retrix-accent/20 disabled:opacity-50"
          >
            <RefreshCw size={11} className={syncing ? 'animate-spin' : ''} />
            {syncing ? '확인 중...' : 'Sync'}
          </button>
        ) : (
          <button
            onClick={() => setShowConnect(!showConnect)}
            className="flex items-center gap-1.5 px-3 py-1 text-xs bg-retrix-border/50 text-retrix-muted rounded-md hover:bg-retrix-border hover:text-retrix-text"
          >
            <Link size={11} /> Notion 연결
          </button>
        )}
      </div>

      {notionPageUrl ? (
        <div className="text-xs text-retrix-muted font-mono truncate">
          <span className="text-retrix-muted/60">Page: </span>
          <a href={notionPageUrl} target="_blank" rel="noopener noreferrer" className="text-retrix-accent hover:underline">{notionPageUrl}</a>
          {notionLastSynced && <span className="ml-2 text-retrix-muted/50">Last synced: {new Date(notionLastSynced).toLocaleString()}</span>}
        </div>
      ) : showConnect ? (
        <div className="space-y-2 mt-2">
          <div className="flex gap-2">
            <input
              type="url"
              value={connectUrl}
              onChange={(e) => setConnectUrl(e.target.value)}
              placeholder="https://www.notion.so/..."
              className="flex-1 bg-retrix-bg border border-retrix-border rounded-md px-3 py-1.5 text-xs text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent font-mono"
            />
            <button
              onClick={handleConnect}
              disabled={connecting || !connectUrl.trim()}
              className="px-3 py-1.5 bg-retrix-accent text-white text-xs rounded-md disabled:opacity-50 hover:bg-retrix-accent/90"
            >
              {connecting ? '연결 중...' : '연결'}
            </button>
          </div>
          <p className="text-xs text-retrix-muted/60">Notion 페이지를 연결하면 spec이 자동으로 import됩니다.</p>
        </div>
      ) : (
        <p className="text-xs text-retrix-muted/60">연결된 Notion 페이지가 없습니다.</p>
      )}

      {error && (
        <div className="mt-2 text-xs text-retrix-danger bg-retrix-danger/10 rounded-md px-3 py-2">{error}</div>
      )}

      {preview && (
        <div className="mt-3 border-t border-retrix-border pt-3">
          {!preview.changed ? (
            <div className="flex items-center gap-2 text-xs text-retrix-success">
              <CheckCircle size={12} />
              변경사항 없음 — 페이지 내용이 마지막 sync 이후 바뀌지 않았습니다.
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs font-medium text-retrix-warning flex items-center gap-1.5">
                <AlertTriangle size={12} /> 변경사항이 감지되었습니다. PM 분석 결과:
              </p>
              <pre className="bg-retrix-bg border border-retrix-border rounded-md p-3 text-xs text-retrix-text font-mono whitespace-pre-wrap max-h-60 overflow-y-auto">
                {preview.pm_analysis}
              </pre>
              <div className="flex gap-2">
                <button
                  onClick={handleApply}
                  disabled={applying}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-retrix-accent text-white text-xs rounded-md hover:bg-retrix-accent/90 disabled:opacity-50"
                >
                  <CheckCircle size={12} />
                  {applying ? '적용 중...' : '확인 — 적용하기'}
                </button>
                <button
                  onClick={handleCancel}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-retrix-border text-retrix-muted text-xs rounded-md hover:bg-retrix-border/70"
                >
                  <XCircle size={12} /> 취소
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PreDecomposePanel({ projectId, initialNotes, onDecomposeStarted }) {
  const [notes, setNotes] = useState(initialNotes || '')
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)
  const chatEndRef = useRef(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  const sendChat = async () => {
    const msg = chatInput.trim()
    if (!msg || chatLoading) return
    const newMessages = [...chatMessages, { role: 'user', content: msg }]
    setChatMessages(newMessages)
    setChatInput('')
    setChatLoading(true)
    try {
      const res = await api.pmChat(newMessages, parseInt(projectId))
      setChatMessages([...newMessages, { role: 'assistant', content: res.reply }])
    } catch (e) {
      setError(e.message)
    } finally {
      setChatLoading(false)
    }
  }

  const handleStart = async () => {
    setStarting(true)
    setError(null)
    try {
      // Build notes from manual textarea + chat summary
      let finalNotes = notes.trim()
      if (chatMessages.length > 0) {
        const chatSummary = chatMessages
          .map((m) => `${m.role === 'user' ? 'User' : 'PM'}: ${m.content}`)
          .join('\n')
        finalNotes = finalNotes
          ? `${finalNotes}\n\n---\n\n## PM 대화 내용\n${chatSummary}`
          : `## PM 대화 내용\n${chatSummary}`
      }
      await api.startDecompose(projectId, finalNotes)
      onDecomposeStarted()
    } catch (e) {
      setError(e.message)
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="bg-retrix-accent/5 border border-retrix-accent/30 rounded-lg p-4 mb-4">
      <div className="flex items-center gap-2 mb-3">
        <MessageSquare size={14} className="text-retrix-accent" />
        <h3 className="text-xs font-medium text-retrix-accent uppercase tracking-wider">분석 완료 — PM 대화 후 태스크 설계</h3>
      </div>
      <p className="text-[11px] text-retrix-muted/80 mb-4">
        Spec 분석이 완료되었습니다. PM과 대화하여 요구사항, 우선순위, 기술 방향 등을 정리하세요.
        대화 내용은 태스크 분해 시 반영됩니다.
      </p>

      {/* PM Chat */}
      <div className="mb-3">
        <div className="bg-retrix-bg border border-retrix-border rounded-md mb-2 max-h-64 overflow-y-auto p-3 space-y-2">
          {chatMessages.length === 0 ? (
            <p className="text-[11px] text-retrix-muted/50 text-center py-4">PM과 대화를 시작하세요</p>
          ) : (
            chatMessages.map((m, i) => (
              <div key={i} className={`text-xs ${m.role === 'user' ? 'text-retrix-text' : 'text-retrix-accent'}`}>
                <span className="font-semibold">{m.role === 'user' ? 'You' : 'PM'}: </span>
                <span className="whitespace-pre-wrap">{m.content}</span>
              </div>
            ))
          )}
          {chatLoading && (
            <div className="flex items-center gap-2 text-xs text-retrix-muted">
              <Loader size={10} className="animate-spin" /> PM 응답 중...
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendChat()}
            placeholder="PM에게 질문하거나 요구사항을 논의하세요..."
            className="flex-1 bg-retrix-bg border border-retrix-border rounded-md px-3 py-1.5 text-xs text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent"
          />
          <button
            onClick={sendChat}
            disabled={!chatInput.trim() || chatLoading}
            className="px-3 py-1.5 bg-retrix-accent/20 text-retrix-accent text-xs rounded-md hover:bg-retrix-accent/30 disabled:opacity-40"
          >
            <Send size={12} />
          </button>
        </div>
      </div>

      {/* Manual notes */}
      <div className="mb-3">
        <label className="block text-[11px] text-retrix-muted mb-1">추가 메모 (선택) — 태스크 설계 시 반영됩니다</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={'예시:\n- 1단계에서는 로그인/회원가입만 구현\n- 결제 모듈은 이번 버전에서 제외\n- 모바일 우선 반응형 디자인 필수'}
          rows={4}
          className="w-full bg-retrix-bg border border-retrix-border rounded-md px-3 py-2 text-xs font-mono text-retrix-text placeholder:text-retrix-muted/30 focus:outline-none focus:border-retrix-accent resize-y"
        />
      </div>

      {error && (
        <div className="mb-3 text-xs text-retrix-danger bg-retrix-danger/10 rounded-md px-3 py-2">{error}</div>
      )}

      <button
        onClick={handleStart}
        disabled={starting}
        className="flex items-center gap-2 px-4 py-2 bg-retrix-accent text-white text-xs rounded-md hover:bg-retrix-accent/90 disabled:opacity-50 transition-colors"
      >
        {starting ? <Loader size={12} className="animate-spin" /> : <Play size={12} />}
        {starting ? '태스크 분해 중...' : '태스크 분해 시작'}
      </button>
    </div>
  )
}


function ProjectRulesPanel({ projectId, initialRules }) {
  const [open, setOpen] = useState(false)
  const [rules, setRules] = useState(initialRules || '')
  const [original, setOriginal] = useState(initialRules || '')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null) // 'saved' | 'error'

  // Sync when parent reloads project data
  useEffect(() => {
    setRules(initialRules || '')
    setOriginal(initialRules || '')
  }, [initialRules])

  const isDirty = rules !== original

  const handleSave = async () => {
    setSaving(true)
    setStatus(null)
    try {
      await api.updateProjectRules(projectId, rules)
      setOriginal(rules)
      setStatus('saved')
      setTimeout(() => setStatus(null), 3000)
    } catch (e) {
      setStatus('error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
      <button
        className="flex items-center justify-between w-full"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-2">
          <ShieldCheck size={14} className="text-retrix-accent" />
          <h3 className="text-xs font-medium text-retrix-muted uppercase tracking-wider">Project Rules</h3>
          {original.trim() && (
            <span className="text-[10px] bg-retrix-accent/20 text-retrix-accent px-1.5 py-0.5 rounded font-mono">active</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isDirty && <span className="text-[10px] text-retrix-warning font-mono">unsaved</span>}
          {open ? <ChevronDown size={13} className="text-retrix-muted" /> : <ChevronRight size={13} className="text-retrix-muted" />}
        </div>
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-[11px] text-retrix-muted/70">
            이 프로젝트에만 적용되는 PM 규칙. 글로벌 규칙 뒤에 추가되며 충돌 시 우선 적용됩니다.
          </p>
          <textarea
            value={rules}
            onChange={(e) => setRules(e.target.value)}
            placeholder={'예시:\n- 이 프로젝트는 Unity 2022.3 LTS를 사용한다.\n- 모든 스크립트는 네임스페이스 Saju.Core 안에 있어야 한다.\n- C# 코드는 반드시 async/await 패턴을 따라야 한다.'}
            spellCheck={false}
            rows={8}
            className="w-full bg-retrix-bg border border-retrix-border rounded-md px-3 py-2.5 text-xs font-mono text-retrix-text focus:outline-none focus:border-retrix-accent resize-y leading-relaxed placeholder:text-retrix-muted/30"
          />
          <div className="flex items-center gap-2">
            {isDirty && (
              <button
                onClick={() => { setRules(original); setStatus(null) }}
                className="px-3 py-1.5 text-xs text-retrix-muted border border-retrix-border rounded-md hover:text-retrix-text hover:border-retrix-muted transition-colors"
              >
                Discard
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={saving || !isDirty}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-retrix-accent text-white text-xs rounded-md hover:bg-retrix-accent/90 disabled:opacity-50 transition-colors"
            >
              {saving ? <Loader size={12} className="animate-spin" /> : <Save size={12} />}
              {saving ? 'Saving…' : 'Save Rules'}
            </button>
            {status === 'saved' && (
              <span className="flex items-center gap-1 text-xs text-retrix-success">
                <CheckCircle size={12} /> Saved
              </span>
            )}
            {status === 'error' && (
              <span className="flex items-center gap-1 text-xs text-retrix-danger">
                <AlertTriangle size={12} /> Failed to save
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ProjectDetail({ subscribe }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadProject = async () => {
    try {
      const data = await api.getProject(id)
      setProject(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProject()
    // Polling fallback for when WebSocket misses updates
    const interval = setInterval(loadProject, 8000)
    return () => clearInterval(interval)
  }, [id])

  useEffect(() => {
    return subscribe(`project-${id}`, (msg) => {
      if (msg.data?.project_id === parseInt(id)) {
        loadProject()
      }
    })
  }, [id, subscribe])

  // Real-time task updates
  useEffect(() => {
    return subscribe(`project-tasks-${id}`, (msg) => {
      if (msg.type === 'task_update' && msg.data?.project_id === parseInt(id)) {
        loadProject()
      }
    })
  }, [id, subscribe])

  const handlePause = async () => {
    await api.pauseProject(id)
    loadProject()
  }
  const handleResume = async () => {
    await api.resumeProject(id)
    loadProject()
  }
  const handleDelete = async () => {
    if (confirm('Delete this project and all tasks?')) {
      await api.deleteProject(id)
      navigate('/')
    }
  }
  const handleUnarchive = async () => {
    await api.unarchiveProject(id)
    loadProject()
  }
  const handleReassignWorkers = async () => {
    if (!confirm('PENDING/ASSIGNED 태스크의 워커를 PM이 재선택합니다. REVIEW/COMPLETED 태스크는 건드리지 않습니다. 진행하시겠습니까?')) return
    await api.pauseProject(id).catch(() => {})
    await api.reassignWorkers(id)
    loadProject()
  }
  const handleRetryTask = async (taskId) => {
    await api.retryTask(taskId)
    loadProject()
  }
  const handleHoldTask = async (taskId) => {
    await api.holdTask(taskId)
    loadProject()
  }
  const handleDeleteTask = async (taskId) => {
    if (!confirm('이 태스크를 삭제하시겠습니까?')) return
    try {
      await api.deleteTask(taskId)
    } catch (e) {
      alert(`삭제 실패: ${e.message}`)
    } finally {
      loadProject()
    }
  }
  const handleArchiveTask = async (taskId) => {
    await api.archiveTask(taskId)
    loadProject()
  }
  const handleUnarchiveTask = async (taskId) => {
    await api.unarchiveTask(taskId)
    loadProject()
  }
  const handleUpdateInstruction = async (taskId, instruction) => {
    await api.updateTaskInstruction(taskId, instruction)
    loadProject()
  }
  const handleStatusChange = async (taskId, status) => {
    await api.updateTaskStatus(taskId, status)
    loadProject()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-retrix-accent border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!project) {
    return <p className="text-retrix-muted">Project not found</p>
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/')} className="text-retrix-muted hover:text-retrix-text">
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-retrix-text">{project.name}</h2>
            <StatusBadge status={project.status} />
          </div>
          <p className="text-xs text-retrix-muted mt-0.5 font-mono">
            {project.project_type?.replace('_', ' ')} · Priority {project.priority}
          </p>
        </div>

        {/* Controls */}
        <div className="flex gap-2">
          {project.archived && (
            <button onClick={handleUnarchive} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-retrix-muted/10 text-retrix-muted rounded-md hover:bg-retrix-muted/20">
              <ArchiveRestore size={12} /> Unarchive
            </button>
          )}
          {!project.archived && project.status === 'in_progress' && (
            <button onClick={handlePause} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-retrix-warning/10 text-retrix-warning rounded-md hover:bg-retrix-warning/20">
              <Pause size={12} /> Pause
            </button>
          )}
          {!project.archived && (project.status === 'paused' || project.status === 'analyzing') && (
            <button onClick={handleResume} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-retrix-success/10 text-retrix-success rounded-md hover:bg-retrix-success/20">
              <Play size={12} /> Resume
            </button>
          )}
          {!project.archived && project.tasks?.some(t => t.status === 'pending' || t.status === 'assigned') && (
            <button onClick={handleReassignWorkers} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-retrix-muted/10 text-retrix-muted rounded-md hover:bg-retrix-muted/20" title="PENDING/ASSIGNED 태스크 워커 재선택">
              <RefreshCw size={12} /> Reassign Workers
            </button>
          )}
          <button onClick={handleDelete} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-retrix-danger/10 text-retrix-danger rounded-md hover:bg-retrix-danger/20">
            <Trash2 size={12} /> Delete
          </button>
        </div>
      </div>

      {/* Archived banner */}
      {project.archived && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-md text-xs mb-4 bg-retrix-muted/10 text-retrix-muted border border-retrix-border">
          <ArchiveRestore size={12} className="shrink-0" />
          <span>이 프로젝트는 보관된 상태입니다. Unarchive 버튼으로 되돌릴 수 있습니다.</span>
        </div>
      )}

      {/* Orchestration stage banner */}
      {!project.archived && <OrchestrationBanner status={project.status} />}

      {/* Progress */}
      <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-retrix-muted">Progress</span>
          <span className="text-sm font-mono text-retrix-text">{Math.round(project.progress || 0)}%</span>
        </div>
        <div className="w-full h-2 bg-retrix-border rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-retrix-accent to-retrix-accent2 rounded-full transition-all duration-700"
            style={{ width: `${project.progress || 0}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-2 text-[11px] text-retrix-muted font-mono">
          <span>Cost: ${(project.total_cost || 0).toFixed(4)}</span>
          <span>Budget: ${project.budget_limit?.toFixed(2) || '∞'}</span>
        </div>
      </div>

      {/* Completion Report */}
      {project.completion_report && (
        <div className="bg-retrix-surface border border-retrix-success/30 rounded-lg p-4 mb-4">
          <h3 className="text-xs font-semibold text-retrix-success mb-3 uppercase tracking-wider flex items-center gap-1.5">
            <CheckCircle size={13} /> PM 완료 보고서
          </h3>

          {project.completion_report.summary && (
            <p className="text-sm text-retrix-text mb-4">{project.completion_report.summary}</p>
          )}

          {project.completion_report.completed?.length > 0 && (
            <div className="mb-4">
              <p className="text-[11px] font-medium text-retrix-muted uppercase tracking-wider mb-2">완료된 작업</p>
              <ul className="space-y-1">
                {project.completion_report.completed.map((item, i) => (
                  <li key={i} className="flex gap-2 text-xs">
                    <CheckCircle size={11} className="text-retrix-success mt-0.5 shrink-0" />
                    <span><span className="text-retrix-text font-medium">{item.task}</span>
                    {item.what_was_done && <span className="text-retrix-muted"> — {item.what_was_done}</span>}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {project.completion_report.ai_next_steps?.length > 0 && (
              <div className="bg-retrix-accent/5 border border-retrix-accent/20 rounded-md p-3">
                <p className="text-[11px] font-medium text-retrix-accent uppercase tracking-wider mb-2 flex items-center gap-1">
                  <Cpu size={11} /> AI가 할 수 있는 다음 작업
                </p>
                <ul className="space-y-1">
                  {project.completion_report.ai_next_steps.map((step, i) => (
                    <li key={i} className="text-xs text-retrix-muted flex gap-1.5">
                      <span className="text-retrix-accent shrink-0">→</span>{step}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {project.completion_report.user_next_steps?.length > 0 && (
              <div className="bg-retrix-accent2/5 border border-retrix-accent2/20 rounded-md p-3">
                <p className="text-[11px] font-medium text-retrix-accent2 uppercase tracking-wider mb-2 flex items-center gap-1">
                  <ShieldCheck size={11} /> 사용자가 해야 할 작업
                </p>
                <ul className="space-y-1">
                  {project.completion_report.user_next_steps.map((step, i) => (
                    <li key={i} className="text-xs text-retrix-muted flex gap-1.5">
                      <span className="text-retrix-accent2 shrink-0">→</span>{step}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {project.completion_report.risks?.length > 0 && (
            <div className="mt-3 bg-retrix-warning/5 border border-retrix-warning/20 rounded-md p-3">
              <p className="text-[11px] font-medium text-retrix-warning uppercase tracking-wider mb-2 flex items-center gap-1">
                <AlertTriangle size={11} /> 주의사항
              </p>
              <ul className="space-y-1">
                {project.completion_report.risks.map((risk, i) => (
                  <li key={i} className="text-xs text-retrix-muted flex gap-1.5">
                    <span className="text-retrix-warning shrink-0">!</span>{risk}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Notion Integration */}
      <NotionSyncPanel
        projectId={id}
        notionPageUrl={project.notion_page_url}
        notionLastSynced={project.notion_last_synced_at}
        onSynced={loadProject}
      />

      {/* Pre-decompose PM discussion panel */}
      {project.pause_after_analysis &&
        project.status === 'paused' &&
        project.analysis_result &&
        (project.tasks?.length || 0) === 0 && (
          <PreDecomposePanel
            projectId={id}
            initialNotes={project.pm_context_notes || ''}
            onDecomposeStarted={loadProject}
          />
        )}

      {/* Per-project PM Rules */}
      <ProjectRulesPanel
        projectId={id}
        initialRules={project.custom_rules || ''}
      />

      {/* Analysis Result */}
      {project.analysis_result && (
        <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
          <h3 className="text-xs font-medium text-retrix-muted mb-2 uppercase tracking-wider">PM Analysis</h3>
          <pre className="text-xs text-retrix-text font-mono whitespace-pre-wrap overflow-x-auto">
            {JSON.stringify(project.analysis_result, null, 2)}
          </pre>
        </div>
      )}

      {/* Add Features */}
      <AddFeaturesPanel projectId={id} onDone={loadProject} />

      {/* Tasks */}
      <TasksSection
        tasks={project.tasks || []}
        onRetry={handleRetryTask}
        onHold={handleHoldTask}
        onDelete={handleDeleteTask}
        onArchive={handleArchiveTask}
        onUnarchive={handleUnarchiveTask}
        onUpdateInstruction={handleUpdateInstruction}
        onStatusChange={handleStatusChange}
      />
    </div>
  )
}
