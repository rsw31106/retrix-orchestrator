import { useState, useRef, useEffect, useCallback } from 'react'
import { api } from '../lib/api'
import { Send, Bot, User, Loader, Trash2 } from 'lucide-react'

const STORAGE_KEY = (id) => `retrix:chat:${id || 'global'}`

const WELCOME_MSG = {
  role: 'assistant',
  content: "Hi! I'm Retrix PM. I have full visibility into your projects, tasks, costs, and worker status. Ask me anything — project status, what's blocking a task, cost analysis, or anything else.",
}

function makeWelcome() {
  return [WELCOME_MSG]
}

function loadHistory(projectId) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY(projectId))
    if (raw) return JSON.parse(raw)
  } catch {}
  return makeWelcome()
}

function saveHistory(projectId, messages) {
  try {
    // Keep max 50 messages per session to avoid localStorage bloat
    localStorage.setItem(STORAGE_KEY(projectId), JSON.stringify(messages.slice(-50)))
  } catch {}
}

function ChatBubble({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex gap-3 mb-4 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${
        isUser ? 'bg-retrix-accent/20' : 'bg-retrix-success/20'
      }`}>
        {isUser
          ? <User size={14} className="text-retrix-accent" />
          : <Bot size={14} className="text-retrix-success" />
        }
      </div>
      <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
        isUser
          ? 'bg-retrix-accent text-white rounded-tr-sm'
          : 'bg-retrix-surface border border-retrix-border text-retrix-text rounded-tl-sm'
      }`}>
        {msg.content}
      </div>
    </div>
  )
}

export default function PMChat() {
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState('')
  const [messages, setMessages] = useState(() => loadHistory(''))
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    api.listProjects().then(setProjects).catch(() => {})
  }, [])

  // Switch history when project changes
  useEffect(() => {
    setMessages(loadHistory(projectId))
  }, [projectId])

  // Persist history on every update
  useEffect(() => {
    saveHistory(projectId, messages)
  }, [messages, projectId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg = { role: 'user', content: text }
    // Exclude the welcome message from API history
    const apiHistory = [...messages.filter(m => m !== WELCOME_MSG), userMsg]
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await api.pmChat(apiHistory, projectId ? parseInt(projectId) : null)
      setMessages(prev => [...prev, { role: 'assistant', content: res.reply }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message}` }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }, [input, loading, messages, projectId])

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const clearChat = () => {
    const fresh = makeWelcome()
    setMessages(fresh)
    saveHistory(projectId, fresh)
  }

  const selectedProject = projects.find(p => String(p.id) === String(projectId))

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] -mt-6 -mx-6">
      {/* Header */}
      <div className="px-6 pt-6 pb-4 border-b border-retrix-border bg-retrix-bg flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-lg font-semibold text-retrix-text">PM Chat</h2>
          <p className="text-xs text-retrix-muted">
            {selectedProject
              ? <>Context: <span className="text-retrix-accent">{selectedProject.name}</span></>
              : 'Global context — all projects'
            }
          </p>
        </div>
        <div className="flex items-center gap-3">
          {projects.length > 0 && (
            <select
              value={projectId}
              onChange={e => setProjectId(e.target.value)}
              className="bg-retrix-surface border border-retrix-border rounded-lg px-3 py-1.5 text-xs text-retrix-text focus:outline-none focus:border-retrix-accent"
            >
              <option value="">All projects</option>
              {projects.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          )}
          <button
            onClick={clearChat}
            className="p-2 text-retrix-muted hover:text-retrix-danger transition-colors"
            title={`Clear ${selectedProject ? selectedProject.name : 'global'} chat`}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.map((msg, i) => <ChatBubble key={i} msg={msg} />)}
        {loading && (
          <div className="flex gap-3 mb-4">
            <div className="w-7 h-7 rounded-full bg-retrix-success/20 flex items-center justify-center shrink-0">
              <Bot size={14} className="text-retrix-success" />
            </div>
            <div className="bg-retrix-surface border border-retrix-border rounded-2xl rounded-tl-sm px-4 py-3">
              <Loader size={14} className="text-retrix-muted animate-spin" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 pb-6 pt-3 border-t border-retrix-border bg-retrix-bg shrink-0">
        <div className="flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask PM anything... (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="flex-1 bg-retrix-surface border border-retrix-border rounded-xl px-4 py-3 text-sm text-retrix-text placeholder-retrix-muted focus:outline-none focus:border-retrix-accent resize-none"
            style={{ minHeight: '44px', maxHeight: '120px' }}
            onInput={e => {
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || loading}
            className="p-3 bg-retrix-accent text-white rounded-xl hover:bg-retrix-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            <Send size={16} />
          </button>
        </div>
        <p className="text-[10px] text-retrix-muted mt-2">Powered by Claude Haiku 4.5 &mdash; responses cost API credits</p>
      </div>
    </div>
  )
}
