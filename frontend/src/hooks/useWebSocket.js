import { useEffect, useRef, useState, useCallback } from 'react'
import { getToken } from '../lib/auth'

export function useWebSocket() {
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState(null)
  const listenersRef = useRef(new Map())
  const reconnectTimer = useRef(null)

  const connect = useCallback(() => {
    const token = getToken()
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${token}`)

    ws.onopen = () => {
      setConnected(true)
      console.log('[WS] Connected')
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        setLastEvent(msg)
        listenersRef.current.forEach((cb) => cb(msg))
      } catch (e) {
        console.error('[WS] Parse error:', e)
      }
    }

    ws.onclose = (ev) => {
      setConnected(false)
      if (ev.code === 4001) {
        console.log('[WS] Unauthorized')
        return
      }
      console.log('[WS] Disconnected, reconnecting in 3s...')
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => ws.close()
    wsRef.current = ws
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const subscribe = useCallback((id, callback) => {
    listenersRef.current.set(id, callback)
    return () => listenersRef.current.delete(id)
  }, [])

  return { connected, lastEvent, subscribe }
}
