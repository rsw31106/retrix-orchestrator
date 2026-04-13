import { Routes, Route, Navigate } from 'react-router-dom'
import { useWebSocket } from './hooks/useWebSocket'
import { isLoggedIn, clearToken } from './lib/auth'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import ProjectDetail from './pages/ProjectDetail'
import NewProject from './pages/NewProject'
import CostTracker from './pages/CostTracker'
import Settings from './pages/Settings'
import PMRules from './pages/PMRules'
import Accounts from './pages/Accounts'
import PMChat from './pages/PMChat'
import ActivityLog from './pages/ActivityLog'
import Login from './pages/Login'
import AlertBanner from './components/AlertBanner'
import { useState, useEffect } from 'react'

function ProtectedLayout({ children, connected, onLogout }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar connected={connected} onLogout={onLogout} />
      <main className="flex-1 overflow-y-auto">
        <div className="p-6">{children}</div>
      </main>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(isLoggedIn())
  const { connected, subscribe } = useWebSocket()
  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    if (!authed) return
    return subscribe('global-alerts', (msg) => {
      if (msg.type === 'alert') {
        setAlerts((prev) => [{ id: Date.now(), ...msg.data }, ...prev.slice(0, 9)])
      }
    })
  }, [subscribe, authed])

  const handleLogout = () => {
    clearToken()
    setAuthed(false)
  }

  const dismissAlert = (id) => setAlerts((prev) => prev.filter((a) => a.id !== id))

  if (!authed) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLogin={() => setAuthed(true)} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <ProtectedLayout connected={connected} onLogout={handleLogout}>
      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="sticky top-0 z-50 -mx-6 -mt-6 mb-4">
          {alerts.slice(0, 3).map((alert) => (
            <AlertBanner key={alert.id} alert={alert} onDismiss={() => dismissAlert(alert.id)} />
          ))}
        </div>
      )}

      <Routes>
        <Route path="/" element={<Dashboard subscribe={subscribe} />} />
        <Route path="/projects/:id" element={<ProjectDetail subscribe={subscribe} />} />
        <Route path="/new" element={<NewProject />} />
        <Route path="/costs" element={<CostTracker />} />
        <Route path="/activity" element={<ActivityLog subscribe={subscribe} />} />
        <Route path="/chat" element={<PMChat />} />
        <Route path="/accounts" element={<Accounts />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/pm-rules" element={<PMRules />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ProtectedLayout>
  )
}
