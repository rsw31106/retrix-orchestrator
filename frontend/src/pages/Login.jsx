import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { setToken } from '../lib/auth'
import { Lock } from 'lucide-react'

export default function Login({ onLogin }) {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const data = await api.login(username, password)
      setToken(data.token)
      onLogin()
      navigate('/')
    } catch (err) {
      setError('Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-retrix-bg flex items-center justify-center">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="text-retrix-accent">RE</span>
            <span className="text-retrix-text">TRIX</span>
          </h1>
          <p className="text-[11px] text-retrix-muted mt-1 font-mono tracking-widest uppercase">
            AI Project Orchestrator
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="bg-retrix-surface border border-retrix-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-5">
            <Lock size={16} className="text-retrix-accent" />
            <span className="text-sm text-retrix-muted">Sign in to continue</span>
          </div>

          {error && (
            <div className="bg-retrix-danger/10 border border-retrix-danger/30 rounded-md px-3 py-2 mb-4 text-sm text-retrix-danger">
              {error}
            </div>
          )}

          <div className="space-y-3">
            <div>
              <label className="block text-xs text-retrix-muted mb-1">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                className="w-full bg-retrix-bg border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text focus:outline-none focus:border-retrix-accent"
              />
            </div>
            <div>
              <label className="block text-xs text-retrix-muted mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-retrix-bg border border-retrix-border rounded-md px-3 py-2 text-sm text-retrix-text focus:outline-none focus:border-retrix-accent"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-retrix-accent text-white text-sm rounded-md hover:bg-retrix-accent/90 transition-colors disabled:opacity-50"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
