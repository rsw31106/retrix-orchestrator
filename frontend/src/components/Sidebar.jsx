import { NavLink } from 'react-router-dom'
import { LayoutDashboard, FolderPlus, DollarSign, Settings, Wifi, WifiOff, LogOut, Users, MessageSquare, Activity, ShieldAlert } from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/new', icon: FolderPlus, label: 'New Project' },
  { to: '/costs', icon: DollarSign, label: 'Cost Tracker' },
  { to: '/activity', icon: Activity, label: 'Activity' },
  { to: '/chat', icon: MessageSquare, label: 'PM Chat' },
  { to: '/accounts', icon: Users, label: 'Accounts' },
  { to: '/settings', icon: Settings, label: 'Settings' },
  { to: '/pm-rules', icon: ShieldAlert, label: 'PM Rules' },
]

export default function Sidebar({ connected, onLogout }) {
  return (
    <aside className="w-56 h-screen bg-retrix-surface border-r border-retrix-border flex flex-col shrink-0">
      {/* Logo */}
      <div className="p-5 border-b border-retrix-border">
        <h1 className="text-xl font-bold tracking-tight">
          <span className="text-retrix-accent">RE</span>
          <span className="text-retrix-text">TRIX</span>
        </h1>
        <p className="text-[10px] text-retrix-muted mt-0.5 font-mono tracking-widest uppercase">
          AI Orchestrator
        </p>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-5 py-2.5 text-sm transition-all',
                isActive
                  ? 'text-retrix-accent bg-retrix-accent/10 border-r-2 border-retrix-accent'
                  : 'text-retrix-muted hover:text-retrix-text hover:bg-white/[0.02]'
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Connection status + Logout */}
      <div className="p-4 border-t border-retrix-border space-y-3">
        <div className="flex items-center gap-2 text-xs">
          {connected ? (
            <>
              <Wifi size={12} className="text-retrix-success" />
              <span className="text-retrix-success">Live</span>
              <span className="w-1.5 h-1.5 rounded-full bg-retrix-success animate-pulse-live" />
            </>
          ) : (
            <>
              <WifiOff size={12} className="text-retrix-danger" />
              <span className="text-retrix-danger">Disconnected</span>
            </>
          )}
        </div>
        <button
          onClick={onLogout}
          className="flex items-center gap-2 text-xs text-retrix-muted hover:text-retrix-danger transition-colors w-full"
        >
          <LogOut size={12} />
          Logout
        </button>
      </div>
    </aside>
  )
}
