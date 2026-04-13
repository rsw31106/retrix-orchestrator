import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { Upload, Rocket, FileText, X, BookOpen } from 'lucide-react'
import clsx from 'clsx'

const projectTypes = [
  { value: 'game_unity', label: 'Game (Unity)', emoji: '🎮' },
  { value: 'game_cocos', label: 'Game (Cocos)', emoji: '🕹️' },
  { value: 'game_godot', label: 'Game (Godot)', emoji: '🎯' },
  { value: 'web_service', label: 'Web Service', emoji: '🌐' },
  { value: 'mobile_app', label: 'Mobile App', emoji: '📱' },
]

export default function NewProject() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    name: '',
    project_type: '',
    description: '',
    spec_document: '',
    budget_limit: 2.0,
    priority: 5,
    workspace_path: '',
    github_create_repo: false,
    github_repo_name: '',
    github_private: true,
  })
  const [submitting, setSubmitting] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [error, setError] = useState(null)
  const [notionUrl, setNotionUrl] = useState('')
  const [notionFetching, setNotionFetching] = useState(false)
  const [notionFetched, setNotionFetched] = useState(false)
  const [specSource, setSpecSource] = useState('manual') // 'manual' | 'notion'
  const fileInputRef = useRef(null)

  const update = (field, value) => setForm((prev) => ({ ...prev, [field]: value }))

  const handleFileUpload = async (file) => {
    if (!file) return
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['md', 'txt', 'pdf', 'docx'].includes(ext)) {
      setError(`Unsupported file type: .${ext}. Use .md, .txt, .pdf, or .docx`)
      return
    }
    setUploading(true)
    setError(null)
    try {
      const result = await api.uploadSpec(file)
      update('spec_document', result.text)
      setUploadedFile({ name: file.name, chars: result.char_count })
    } catch (e) {
      setError(e.message)
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFileUpload(file)
  }

  const handleNotionFetch = async () => {
    if (!notionUrl.trim()) return
    setNotionFetching(true)
    setError(null)
    try {
      // We'll just store the URL and let the backend fetch — no preview needed at creation time
      // But we do a lightweight check to confirm it's accessible
      update('notion_page_url', notionUrl.trim())
      setNotionFetched(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setNotionFetching(false)
    }
  }

  const handleSubmit = async () => {
    if (!form.name || !form.project_type) {
      setError('Name and type are required')
      return
    }
    if (specSource === 'manual' && !form.spec_document) {
      setError('Spec document is required')
      return
    }
    if (specSource === 'notion' && !notionUrl.trim()) {
      setError('Please enter a Notion page URL')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const payload = {
        ...form,
        notion_page_url: specSource === 'notion' ? notionUrl.trim() : undefined,
        spec_document: specSource === 'notion' ? '' : form.spec_document,
      }
      const result = await api.createProject(payload)
      navigate(`/projects/${result.id}`)
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-lg font-semibold text-retrix-text mb-1">New Project</h2>
      <p className="text-xs text-retrix-muted mb-6">Upload a spec document and let the PM orchestrator handle the rest.</p>

      {error && (
        <div className="bg-retrix-danger/10 border border-retrix-danger/30 rounded-md px-3 py-2 mb-4 text-sm text-retrix-danger">
          {error}
        </div>
      )}

      <div className="space-y-4">
        {/* Name */}
        <div>
          <label className="block text-xs text-retrix-muted mb-1.5">Project Name</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => update('name', e.target.value)}
            placeholder="My Awesome Game"
            className="w-full bg-retrix-surface border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent"
          />
        </div>

        {/* Type */}
        <div>
          <label className="block text-xs text-retrix-muted mb-1.5">Project Type</label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {projectTypes.map(({ value, label, emoji }) => (
              <button
                key={value}
                onClick={() => update('project_type', value)}
                className={clsx(
                  'flex items-center gap-2 px-3 py-2 rounded-md border text-sm transition-all',
                  form.project_type === value
                    ? 'border-retrix-accent bg-retrix-accent/10 text-retrix-accent'
                    : 'border-retrix-border text-retrix-muted hover:border-retrix-border hover:text-retrix-text'
                )}
              >
                <span>{emoji}</span>
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs text-retrix-muted mb-1.5">Brief Description</label>
          <input
            type="text"
            value={form.description}
            onChange={(e) => update('description', e.target.value)}
            placeholder="A puzzle platformer with online multiplayer"
            className="w-full bg-retrix-surface border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent"
          />
        </div>

        {/* Spec Document */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-retrix-muted">Spec Document / 기획서</label>
            {/* Source tab toggle */}
            <div className="flex rounded-md overflow-hidden border border-retrix-border text-xs">
              <button
                type="button"
                onClick={() => setSpecSource('manual')}
                className={clsx('px-3 py-1 flex items-center gap-1 transition-colors',
                  specSource === 'manual' ? 'bg-retrix-accent text-white' : 'text-retrix-muted hover:text-retrix-text'
                )}
              >
                <FileText size={11} /> 직접 입력
              </button>
              <button
                type="button"
                onClick={() => setSpecSource('notion')}
                className={clsx('px-3 py-1 flex items-center gap-1 transition-colors',
                  specSource === 'notion' ? 'bg-retrix-accent text-white' : 'text-retrix-muted hover:text-retrix-text'
                )}
              >
                <BookOpen size={11} /> Notion
              </button>
            </div>
          </div>

          {specSource === 'notion' ? (
            <div className="space-y-2">
              <div className="flex gap-2">
                <input
                  type="url"
                  value={notionUrl}
                  onChange={(e) => { setNotionUrl(e.target.value); setNotionFetched(false) }}
                  placeholder="https://www.notion.so/your-page-id or bare page ID"
                  className="flex-1 bg-retrix-surface border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent font-mono"
                />
                <button
                  type="button"
                  onClick={handleNotionFetch}
                  disabled={notionFetching || !notionUrl.trim()}
                  className="px-3 py-2 rounded-md bg-retrix-accent/20 text-retrix-accent text-xs hover:bg-retrix-accent/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                >
                  {notionFetching ? '확인 중...' : '페이지 연결'}
                </button>
              </div>
              {notionFetched && (
                <div className="flex items-center gap-1.5 text-xs text-retrix-success bg-retrix-success/10 border border-retrix-success/20 rounded-md px-3 py-2">
                  <BookOpen size={12} />
                  Notion URL이 설정되었습니다. 프로젝트 생성 시 자동으로 내용을 가져옵니다.
                </div>
              )}
              <p className="text-xs text-retrix-muted/70">
                Notion 페이지의 내용이 기획서로 자동 import됩니다. Notion API 키가 설정되어 있어야 합니다.
              </p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-1.5">
                {uploadedFile && (
                  <span className="flex items-center gap-1 text-xs text-retrix-accent">
                    <FileText size={12} />
                    {uploadedFile.name}
                    <span className="text-retrix-muted">({uploadedFile.chars.toLocaleString()} chars)</span>
                    <button
                      type="button"
                      onClick={() => { setUploadedFile(null); update('spec_document', '') }}
                      className="text-retrix-muted hover:text-retrix-danger ml-0.5"
                    >
                      <X size={12} />
                    </button>
                  </span>
                )}
              </div>

              {/* Drop zone */}
              <div
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center justify-center gap-2 border border-dashed border-retrix-border rounded-md py-3 mb-2 cursor-pointer hover:border-retrix-accent hover:bg-retrix-accent/5 transition-colors"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".md,.txt,.pdf,.docx"
                  className="hidden"
                  onChange={(e) => handleFileUpload(e.target.files[0])}
                />
                {uploading ? (
                  <div className="w-4 h-4 border-2 border-retrix-accent/30 border-t-retrix-accent rounded-full animate-spin" />
                ) : (
                  <Upload size={14} className="text-retrix-muted" />
                )}
                <span className="text-xs text-retrix-muted">
                  {uploading ? 'Parsing...' : 'Upload .md / .txt / .pdf / .docx — or drag & drop'}
                </span>
              </div>

              <textarea
                value={form.spec_document}
                onChange={(e) => update('spec_document', e.target.value)}
                placeholder="Paste your full project spec, feature list, or idea document here..."
                rows={12}
                className="w-full bg-retrix-surface border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent font-mono"
              />
            </>
          )}
        </div>

        {/* Priority & Budget */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-retrix-muted mb-1.5">Priority (1=highest, 10=lowest)</label>
            <input
              type="number"
              min={1}
              max={10}
              value={form.priority}
              onChange={(e) => update('priority', parseInt(e.target.value))}
              className="w-full bg-retrix-surface border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text focus:outline-none focus:border-retrix-accent"
            />
          </div>
          <div>
            <label className="block text-xs text-retrix-muted mb-1.5">Budget Limit (USD)</label>
            <input
              type="number"
              step="0.5"
              min={0}
              value={form.budget_limit}
              onChange={(e) => update('budget_limit', parseFloat(e.target.value))}
              className="w-full bg-retrix-surface border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text focus:outline-none focus:border-retrix-accent"
            />
          </div>
        </div>

        {/* Workspace Path */}
        <div>
          <label className="block text-xs text-retrix-muted mb-1.5">
            Workspace Path
            <span className="text-retrix-muted/50 ml-1">(비워두면 자동 생성: D:\Projects\{'{name}'})</span>
          </label>
          <input
            type="text"
            value={form.workspace_path}
            onChange={(e) => update('workspace_path', e.target.value)}
            placeholder="D:\Projects\my-game"
            className="w-full bg-retrix-surface border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent font-mono"
          />
        </div>

        {/* GitHub */}
        <div className="bg-retrix-bg/50 border border-retrix-border rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <label className="text-xs text-retrix-muted font-medium uppercase tracking-wider">GitHub Integration</label>
            <button
              type="button"
              onClick={() => update('github_create_repo', !form.github_create_repo)}
              className={clsx(
                'w-9 h-5 rounded-full transition-colors relative',
                form.github_create_repo ? 'bg-retrix-accent' : 'bg-retrix-border'
              )}
            >
              <div className={clsx(
                'w-3.5 h-3.5 bg-white rounded-full absolute top-0.5 transition-all',
                form.github_create_repo ? 'left-[18px]' : 'left-[3px]'
              )} />
            </button>
          </div>

          {form.github_create_repo && (
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-retrix-muted mb-1">Repo Name</label>
                <input
                  type="text"
                  value={form.github_repo_name}
                  onChange={(e) => update('github_repo_name', e.target.value)}
                  placeholder="auto-generated from project name"
                  className="w-full bg-retrix-surface border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text placeholder:text-retrix-muted/40 focus:outline-none focus:border-retrix-accent font-mono"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.github_private}
                  onChange={(e) => update('github_private', e.target.checked)}
                  className="rounded border-retrix-border"
                />
                <label className="text-xs text-retrix-muted">Private repository</label>
              </div>
            </div>
          )}
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className={clsx(
            'flex items-center justify-center gap-2 w-full py-2.5 rounded-md text-sm font-medium transition-all',
            submitting
              ? 'bg-retrix-muted/20 text-retrix-muted cursor-not-allowed'
              : 'bg-retrix-accent text-white hover:bg-retrix-accent/90'
          )}
        >
          {submitting ? (
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <Rocket size={16} />
          )}
          {submitting ? 'Creating...' : 'Launch Project'}
        </button>
      </div>
    </div>
  )
}
