import { getToken, clearToken } from './auth'

const API_BASE = '/api'

export async function fetchApi(path, options = {}) {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new Error('Session expired')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'API Error')
  }
  return res.json()
}

export const api = {
  // Auth
  login: (username, password) =>
    fetchApi('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  verify: () => fetchApi('/auth/verify'),

  // Dashboard
  summary: () => fetchApi('/dashboard/summary'),
  costsToday: () => fetchApi('/costs/today'),
  workerStatus: () => fetchApi('/workers/status'),

  // Projects
  listProjects: (archived = false) => fetchApi(`/projects?archived=${archived}`),
  getProject: (id) => fetchApi(`/projects/${id}`),
  createProject: (data) => fetchApi('/projects', { method: 'POST', body: JSON.stringify(data) }),
  pauseProject: (id) => fetchApi(`/projects/${id}/pause`, { method: 'POST' }),
  resumeProject: (id) => fetchApi(`/projects/${id}/resume`, { method: 'POST' }),
  deleteProject: (id) => fetchApi(`/projects/${id}`, { method: 'DELETE' }),
  archiveProject: (id) => fetchApi(`/projects/${id}/archive`, { method: 'POST' }),
  unarchiveProject: (id) => fetchApi(`/projects/${id}/unarchive`, { method: 'POST' }),

  // Tasks
  retryTask: (id, body = {}) => fetchApi(`/tasks/${id}/retry`, { method: 'POST', body: JSON.stringify(body) }),
  holdTask: (id) => fetchApi(`/tasks/${id}/hold`, { method: 'POST' }),
  updateTaskInstruction: (id, instruction) => fetchApi(`/tasks/${id}/instruction`, { method: 'PATCH', body: JSON.stringify({ instruction }) }),

  // Costs
  projectCosts: (id) => fetchApi(`/costs/by-project/${id}`),

  // Settings
  getSettings: () => fetchApi('/settings'),
  updateSettings: (data) => fetchApi('/settings', { method: 'PUT', body: JSON.stringify(data) }),

  // PM Rules
  pmRules: () => fetchApi('/pm/rules'),
  updatePMRules: (rules) => fetchApi('/pm/rules', { method: 'PUT', body: JSON.stringify({ rules }) }),

  // Cost history
  costHistory: (days = 30) => fetchApi(`/costs/history?days=${days}`),

  // User management
  listUsers: () => fetchApi('/users'),
  createUser: (data) => fetchApi('/users', { method: 'POST', body: JSON.stringify(data) }),
  deleteUser: (id) => fetchApi(`/users/${id}`, { method: 'DELETE' }),
  updateUserRole: (id, role) => fetchApi(`/users/${id}/role`, { method: 'PATCH', body: JSON.stringify({ role }) }),
  adminResetPassword: (id, newPassword) => fetchApi(`/users/${id}/change-password`, { method: 'POST', body: JSON.stringify({ new_password: newPassword }) }),

  // PM Chat
  pmChat: (messages, projectId = null) => fetchApi('/pm/chat', {
    method: 'POST',
    body: JSON.stringify({ messages, project_id: projectId }),
  }),

  // Confirmations (model switch + analysis review)
  listConfirmations: () => fetchApi('/confirmations'),
  respondConfirmation: (id, approved, model = null) =>
    fetchApi(`/confirmations/${id}/respond`, {
      method: 'POST',
      body: JSON.stringify({ approved, model }),
    }),
  analysisFeedback: (id, message) =>
    fetchApi(`/confirmations/${id}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  // Activity log
  getActivity: (params = {}) => {
    const q = new URLSearchParams()
    if (params.limit) q.set('limit', params.limit)
    if (params.offset) q.set('offset', params.offset)
    if (params.project_id) q.set('project_id', params.project_id)
    if (params.actor_type) q.set('actor_type', params.actor_type)
    return fetchApi(`/activity?${q}`)
  },

  // Notion integration
  notionConnect: (projectId, notionPageUrl) =>
    fetchApi(`/projects/${projectId}/notion/connect`, { method: 'POST', body: JSON.stringify({ notion_page_url: notionPageUrl }) }),
  notionSyncPreview: (projectId) => fetchApi(`/projects/${projectId}/notion/sync-preview`),
  notionSyncApply: (projectId, confirmed, changeSummary) =>
    fetchApi(`/projects/${projectId}/notion/sync-apply`, {
      method: 'POST',
      body: JSON.stringify({ confirmed, change_summary: changeSummary }),
    }),

  // File upload
  uploadSpec: (file) => {
    const token = getToken()
    const formData = new FormData()
    formData.append('file', file)
    return fetch(`${API_BASE}/upload/spec`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    }).then(async (res) => {
      if (res.status === 401) { clearToken(); window.location.href = '/login'; throw new Error('Session expired') }
      if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail || 'Upload failed') }
      return res.json()
    })
  },
}
