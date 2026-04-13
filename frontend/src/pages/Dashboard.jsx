import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import { Activity, DollarSign, FolderOpen, CheckCircle, Cpu, Circle, Archive, ArchiveRestore } from 'lucide-react'

function StatCard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-md bg-${color}/10`}>
          <Icon size={18} className={`text-${color}`} />
        </div>
        <div>
          <p className="text-2xl font-semibold text-retrix-text">{value}</p>
          <p className="text-xs text-retrix-muted">{label}</p>
        </div>
      </div>
      {sub && <p className="text-[11px] text-retrix-muted mt-2 font-mono">{sub}</p>}
    </div>
  )
}

function WorkerStatusPanel({ workers }) {
  const entries = Object.entries(workers || {})
  if (entries.length === 0) return null
  return (
    <div className="bg-retrix-surface border border-retrix-border rounded-lg p-4 mb-6">
      <h3 className="text-xs font-medium text-retrix-muted uppercase tracking-wider mb-3 flex items-center gap-2">
        <Cpu size={12} /> Workers
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
        {entries.map(([name, info]) => {
          const working = info?.status === 'working'
          return (
            <div key={name} className="flex items-center gap-2 text-xs">
              <Circle
                size={7}
                className={working ? 'text-retrix-success fill-retrix-success' : 'text-retrix-border fill-retrix-border'}
              />
              <div className="min-w-0">
                <p className="font-mono text-retrix-text truncate">{name}</p>
                {working && info.task_title && (
                  <p className="text-retrix-muted truncate">{info.task_title}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ProjectCard({ project, onArchive }) {
  return (
    <div className="relative group bg-retrix-surface border border-retrix-border rounded-lg p-4 hover:border-retrix-accent/40 transition-all">
      <button
        onClick={(e) => { e.preventDefault(); onArchive(project.id, project.archived) }}
        title={project.archived ? 'Unarchive' : 'Archive'}
        className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded text-retrix-muted hover:text-retrix-text"
      >
        {project.archived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
      </button>
      <Link to={`/projects/${project.id}`} className="block">
        <div className="flex items-center justify-between mb-3 pr-5">
          <h3 className="font-medium text-retrix-text text-sm truncate">{project.name}</h3>
          <StatusBadge status={project.status} />
        </div>

        {/* Progress bar */}
        <div className="w-full h-1.5 bg-retrix-border rounded-full overflow-hidden mb-2">
          <div
            className="h-full bg-retrix-accent rounded-full transition-all duration-500"
            style={{ width: `${project.progress || 0}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-[11px] text-retrix-muted font-mono">
          <span>{project.project_type?.replace('_', ' ')}</span>
          <span>{Math.round(project.progress || 0)}% · {project.task_count} tasks</span>
        </div>
      </Link>
    </div>
  )
}

export default function Dashboard({ subscribe }) {
  const [summary, setSummary] = useState(null)
  const [projects, setProjects] = useState([])
  const [workers, setWorkers] = useState({})
  const [loading, setLoading] = useState(true)
  const [showArchived, setShowArchived] = useState(false)

  const loadData = useCallback(async () => {
    try {
      const [sum, projs] = await Promise.all([api.summary(), api.listProjects(showArchived)])
      setSummary(sum)
      setProjects(projs)
      setWorkers(sum?.workers || {})
    } catch (e) {
      console.error('Dashboard load error:', e)
    } finally {
      setLoading(false)
    }
  }, [showArchived])

  const handleArchive = useCallback(async (id, isArchived) => {
    try {
      if (isArchived) await api.unarchiveProject(id)
      else await api.archiveProject(id)
      loadData()
    } catch (e) {
      console.error('Archive error:', e)
    }
  }, [loadData])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 10000)
    return () => clearInterval(interval)
  }, [loadData])

  // Real-time project updates
  useEffect(() => {
    return subscribe('dashboard', (msg) => {
      if (msg.type === 'project_update') loadData()
    })
  }, [subscribe])

  // Real-time worker status (no full reload needed — patch in place)
  useEffect(() => {
    return subscribe('dashboard-workers', (msg) => {
      if (msg.type === 'worker_update') {
        const { worker, ...info } = msg.data
        setWorkers(prev => ({ ...prev, [worker]: info }))
      }
    })
  }, [subscribe])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-retrix-accent border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const stats = summary?.projects || {}
  const costsToday = summary?.costs_today || {}

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-retrix-text">Dashboard</h2>
          <p className="text-xs text-retrix-muted mt-0.5">Real-time project orchestration overview</p>
        </div>
        <Link
          to="/new"
          className="px-4 py-2 bg-retrix-accent text-white text-sm rounded-md hover:bg-retrix-accent/90 transition-colors"
        >
          + New Project
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <StatCard icon={FolderOpen} label="Total Projects" value={stats.total || 0} color="retrix-accent" />
        <StatCard icon={Activity} label="Active" value={stats.active || 0} color="blue-400" />
        <StatCard icon={CheckCircle} label="Completed" value={stats.completed || 0} color="retrix-success" />
        <StatCard
          icon={DollarSign}
          label="Cost Today"
          value={`$${(costsToday.total || 0).toFixed(2)}`}
          color="retrix-warning"
        />
      </div>

      {/* Worker Status */}
      <WorkerStatusPanel workers={workers} />

      {/* Project Grid */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-retrix-muted">
          {showArchived ? 'Archived Projects' : 'Projects'}
        </h3>
        <button
          onClick={() => setShowArchived(v => !v)}
          className="flex items-center gap-1.5 text-xs text-retrix-muted hover:text-retrix-text transition-colors"
        >
          {showArchived ? <ArchiveRestore size={12} /> : <Archive size={12} />}
          {showArchived ? 'Show Active' : 'Show Archived'}
        </button>
      </div>
      {projects.length === 0 ? (
        <div className="text-center py-16 text-retrix-muted">
          <FolderOpen size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">{showArchived ? 'No archived projects' : 'No projects yet'}</p>
          {!showArchived && (
            <Link to="/new" className="text-retrix-accent text-sm hover:underline">
              Create your first project
            </Link>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} onArchive={handleArchive} />
          ))}
        </div>
      )}
    </div>
  )
}
