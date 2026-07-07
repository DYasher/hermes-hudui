import { useEffect, useRef, useCallback, useState } from 'react'
import { mutate } from 'swr'

interface WebSocketMessage {
  type: 'data_changed' | 'cache_invalidate' | 'connected' | 'disconnected'
  data_types?: string[]
  data_type?: string
  keys?: string[]
  paths?: string[]
}

type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface UseWebSocketReturn {
  status: WebSocketStatus
  sendMessage: (data: string) => void
}

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`
const HEALTH_DEBOUNCE_MS = 750
const HEALTH_MIN_REFRESH_MS = 3000

export function useWebSocket(): UseWebSocketReturn {
  const [status, setStatus] = useState<WebSocketStatus>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const healthRefreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastHealthRefreshRef = useRef(0)

  const revalidateHealth = useCallback(() => {
    if (document.visibilityState === 'hidden') return

    const now = Date.now()
    const elapsed = now - lastHealthRefreshRef.current
    const delay = elapsed >= HEALTH_MIN_REFRESH_MS
      ? HEALTH_DEBOUNCE_MS
      : HEALTH_MIN_REFRESH_MS - elapsed

    if (healthRefreshTimeoutRef.current) {
      clearTimeout(healthRefreshTimeoutRef.current)
    }

    healthRefreshTimeoutRef.current = setTimeout(() => {
      lastHealthRefreshRef.current = Date.now()
      mutate(
        (key) => typeof key === 'string' && key.startsWith('/api/health'),
        undefined,
        {
          revalidate: true,
          rollbackOnError: true,
          populateCache: false,
        }
      )
    }, delay)
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setStatus('connecting')

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
      reconnectAttemptsRef.current = 0
    }

    ws.onmessage = (event) => {
      try {
        if (!event.data.startsWith('{')) {
          return
        }
        const data: WebSocketMessage = JSON.parse(event.data)

        if (data.type === 'data_changed') {
          const changedTypes = data.data_types || (data.data_type ? [data.data_type] : [])
          if (!changedTypes.length) return

          const typeToPath: Record<string, string> = {
            sessions: '/sessions',
            skills: '/skills',
            memory: '/state',
            user: '/state',
            patterns: '/patterns',
            profiles: '/profiles',
            cron: '/cron',
            projects: '/projects',
            corrections: '/corrections',
            state: '/state',
            timeline: '/timeline',
            snapshots: '/snapshots',
            gateway: '/gateway',
            plugins: '/plugins',
            'model-info': '/model-info',
          }

          const healthTypes = new Set(['health', 'config', 'gateway', 'plugins', 'model-info'])

          changedTypes.forEach((dataType) => {
            if (healthTypes.has(dataType)) {
              revalidateHealth()
            }

            const path = typeToPath[dataType]
            if (path) {
              mutate(
                (key) => typeof key === 'string' && key.startsWith(`/api${path}`),
                undefined,
                {
                  revalidate: true,
                  rollbackOnError: true,
                  populateCache: false,
                }
              )
            }
          })

          mutate(
            (key) => typeof key === 'string' && key.startsWith('/api/dashboard'),
            undefined,
            {
              revalidate: true,
              rollbackOnError: true,
              populateCache: false,
            }
          )
        }
      } catch (err) {
        console.warn('[WS] Failed to parse message:', err)
      }
    }

    ws.onclose = () => {
      setStatus('disconnected')
      wsRef.current = null

      const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)
      reconnectAttemptsRef.current++

      reconnectTimeoutRef.current = setTimeout(() => {
        connect()
      }, delay)
    }

    ws.onerror = () => {
      setStatus('error')
    }
  }, [revalidateHealth])

  const sendMessage = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    }
  }, [])

  useEffect(() => {
    connect()

    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping')
      }
    }, 30000)

    return () => {
      clearInterval(heartbeat)
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (healthRefreshTimeoutRef.current) {
        clearTimeout(healthRefreshTimeoutRef.current)
      }
      wsRef.current?.close()
    }
  }, [connect])

  return { status, sendMessage }
}
