import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Users, Plus, Trash2, Key, Shield, Eye, X, Check } from 'lucide-react'

const ROLE_BADGE = {
  admin: 'bg-retrix-accent/20 text-retrix-accent',
  viewer: 'bg-retrix-border text-retrix-muted',
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-retrix-surface border border-retrix-border rounded-xl w-full max-w-md p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-semibold text-retrix-text">{title}</h3>
          <button onClick={onClose} className="text-retrix-muted hover:text-retrix-text">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div className="mb-4">
      <label className="text-xs text-retrix-muted block mb-1.5">{label}</label>
      {children}
    </div>
  )
}

const inputCls = 'w-full bg-retrix-bg border border-retrix-border rounded-lg px-3 py-2 text-sm text-retrix-text focus:outline-none focus:border-retrix-accent'

export default function Accounts() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Create user modal
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ username: '', password: '', email: '', role: 'viewer' })
  const [creating, setCreating] = useState(false)

  // Reset password modal
  const [resetTarget, setResetTarget] = useState(null)
  const [newPassword, setNewPassword] = useState('')
  const [resetting, setResetting] = useState(false)

  const load = async () => {
    try {
      const data = await api.listUsers()
      setUsers(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    setCreating(true)
    try {
      await api.createUser(createForm)
      setShowCreate(false)
      setCreateForm({ username: '', password: '', email: '', role: 'viewer' })
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (u) => {
    if (!confirm(`Delete user "${u.username}"?`)) return
    try {
      await api.deleteUser(u.id)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const handleRoleToggle = async (u) => {
    const newRole = u.role === 'admin' ? 'viewer' : 'admin'
    try {
      await api.updateUserRole(u.id, newRole)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const handleResetPassword = async (e) => {
    e.preventDefault()
    setResetting(true)
    try {
      await api.adminResetPassword(resetTarget.id, newPassword)
      setResetTarget(null)
      setNewPassword('')
    } catch (e) {
      setError(e.message)
    } finally {
      setResetting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-retrix-accent border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-retrix-text mb-1">Accounts</h2>
          <p className="text-xs text-retrix-muted">Manage users and access levels</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-3 py-2 bg-retrix-accent text-white rounded-lg text-sm hover:bg-retrix-accent/90 transition-colors"
        >
          <Plus size={14} />
          New User
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-retrix-danger/10 border border-retrix-danger/30 rounded-lg text-sm text-retrix-danger flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}><X size={14} /></button>
        </div>
      )}

      <div className="bg-retrix-surface border border-retrix-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-retrix-border">
              <th className="text-left px-4 py-3 text-xs font-medium text-retrix-muted uppercase tracking-wider">User</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-retrix-muted uppercase tracking-wider">Email</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-retrix-muted uppercase tracking-wider">Role</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-retrix-muted uppercase tracking-wider">Created</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-retrix-border/50 last:border-0 hover:bg-white/[0.02]">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-retrix-accent/20 flex items-center justify-center text-xs font-semibold text-retrix-accent uppercase">
                      {u.username[0]}
                    </div>
                    <span className="text-retrix-text font-medium">{u.username}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-retrix-muted">{u.email || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ROLE_BADGE[u.role]}`}>
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3 text-retrix-muted text-xs">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1 justify-end">
                    <button
                      onClick={() => handleRoleToggle(u)}
                      title={u.role === 'admin' ? 'Demote to viewer' : 'Promote to admin'}
                      className="p-1.5 text-retrix-muted hover:text-retrix-accent transition-colors"
                    >
                      {u.role === 'admin' ? <Eye size={14} /> : <Shield size={14} />}
                    </button>
                    <button
                      onClick={() => { setResetTarget(u); setNewPassword('') }}
                      title="Reset password"
                      className="p-1.5 text-retrix-muted hover:text-retrix-warning transition-colors"
                    >
                      <Key size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(u)}
                      title="Delete user"
                      className="p-1.5 text-retrix-muted hover:text-retrix-danger transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && (
          <p className="text-sm text-retrix-muted text-center py-8">No users found</p>
        )}
      </div>

      {/* Create user modal */}
      {showCreate && (
        <Modal title="Create New User" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleCreate}>
            <Field label="Username">
              <input
                className={inputCls}
                value={createForm.username}
                onChange={e => setCreateForm(f => ({ ...f, username: e.target.value }))}
                required autoFocus
              />
            </Field>
            <Field label="Password">
              <input
                type="password"
                className={inputCls}
                value={createForm.password}
                onChange={e => setCreateForm(f => ({ ...f, password: e.target.value }))}
                required
              />
            </Field>
            <Field label="Email (optional)">
              <input
                type="email"
                className={inputCls}
                value={createForm.email}
                onChange={e => setCreateForm(f => ({ ...f, email: e.target.value }))}
              />
            </Field>
            <Field label="Role">
              <select
                className={inputCls}
                value={createForm.role}
                onChange={e => setCreateForm(f => ({ ...f, role: e.target.value }))}
              >
                <option value="viewer">Viewer</option>
                <option value="admin">Admin</option>
              </select>
            </Field>
            <div className="flex gap-2 justify-end mt-6">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-retrix-muted hover:text-retrix-text transition-colors">
                Cancel
              </button>
              <button type="submit" disabled={creating} className="flex items-center gap-2 px-4 py-2 bg-retrix-accent text-white rounded-lg text-sm hover:bg-retrix-accent/90 disabled:opacity-50">
                <Check size={14} />
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Reset password modal */}
      {resetTarget && (
        <Modal title={`Reset password — ${resetTarget.username}`} onClose={() => setResetTarget(null)}>
          <form onSubmit={handleResetPassword}>
            <Field label="New Password">
              <input
                type="password"
                className={inputCls}
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                required autoFocus
              />
            </Field>
            <div className="flex gap-2 justify-end mt-6">
              <button type="button" onClick={() => setResetTarget(null)} className="px-4 py-2 text-sm text-retrix-muted hover:text-retrix-text transition-colors">
                Cancel
              </button>
              <button type="submit" disabled={resetting} className="flex items-center gap-2 px-4 py-2 bg-retrix-warning/90 text-white rounded-lg text-sm hover:bg-retrix-warning disabled:opacity-50">
                <Key size={14} />
                {resetting ? 'Saving...' : 'Reset'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
