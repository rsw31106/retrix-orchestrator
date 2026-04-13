import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import {
  ArrowLeft, Pause, Play, Trash2, RotateCcw, Hand,
  ChevronDown, ChevronRight, Clock, Cpu, AlertTriangle, Loader,
} from 'lucide-react'
import clsx from 'clsx'

const STAGE_LABELS = {
  analyzing:   { text: 'Analyzing spec document…',       active: true },
  planning:    { text: 'Decomposing into tasks…',         active: true },
  in_progress: { text: 'Generating instructions & dispatching workers…', active: true },
  paused:      { text: 'Paused',                          active: false },
  completed:   { text: 'All tasks completed',             active: false },
  failed:      { text: 'One or more tasks failed',        active: false },
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

function TaskRow({ task, onRetry, onHold, onUpdateInstruction }) {
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
    <div className="border border-retrix-border rounded-lg overflow-hidden">
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

        {task.retry_count > 0 && (
          <span className="text-[10px] font-mono text-retrix-warning flex items-center gap-1">
            <RotateCcw size={10} /> {task.retry_count}
          </span>
        )}

        <StatusBadge status={task.status} />

        {/* Actions */}
        {(task.status === 'failed' || task.status === 'held') && (
          <div className="flex gap-1 ml-2" onClick={(e) => e.stopPropagation()}>
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
          </div>
        )}
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
  const handleRetryTask = async (taskId) => {
    await api.retryTask(taskId)
    loadProject()
  }
  const handleHoldTask = async (taskId) => {
    await api.holdTask(taskId)
    loadProject()
  }
  const handleUpdateInstruction = async (taskId, instruction) => {
    await api.updateTaskInstruction(taskId, instruction)
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
          {project.status === 'in_progress' && (
            <button onClick={handlePause} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-retrix-warning/10 text-retrix-warning rounded-md hover:bg-retrix-warning/20">
              <Pause size={12} /> Pause
            </button>
          )}
          {project.status === 'paused' && (
            <button onClick={handleResume} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-retrix-success/10 text-retrix-success rounded-md hover:bg-retrix-success/20">
              <Play size={12} /> Resume
            </button>
          )}
          <button onClick={handleDelete} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-retrix-danger/10 text-retrix-danger rounded-md hover:bg-retrix-danger/20">
            <Trash2 size={12} /> Delete
          </button>
        </div>
      </div>

      {/* Orchestration stage banner */}
      <OrchestrationBanner status={project.status} />

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

      {/* Analysis Result */}
      {project.analysis_result && (
        <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-4">
          <h3 className="text-xs font-medium text-retrix-muted mb-2 uppercase tracking-wider">PM Analysis</h3>
          <pre className="text-xs text-retrix-text font-mono whitespace-pre-wrap overflow-x-auto">
            {JSON.stringify(project.analysis_result, null, 2)}
          </pre>
        </div>
      )}

      {/* Tasks */}
      <div className="mb-2">
        <h3 className="text-sm font-medium text-retrix-muted mb-3">Tasks ({project.tasks?.length || 0})</h3>
      </div>
      <div className="space-y-2">
        {(project.tasks || []).map((task) => (
          <TaskRow key={task.id} task={task} onRetry={handleRetryTask} onHold={handleHoldTask} onUpdateInstruction={handleUpdateInstruction} />
        ))}
      </div>
    </div>
  )
}
