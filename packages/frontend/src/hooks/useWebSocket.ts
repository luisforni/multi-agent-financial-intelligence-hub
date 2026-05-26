import { useEffect, useRef, useCallback, useState } from 'react'
import type { WsEvent } from '../types'

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ||
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`

export function useWebSocket(onEvent: (evt: WsEvent) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    const ws = new WebSocket(`${WS_URL}/ws`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)

    ws.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data as string) as WsEvent
        onEventRef.current(evt)
      } catch {
        // ignore malformed frames
      }
    }

    ws.onclose = () => {
      setConnected(false)
      setTimeout(connect, 3000)
    }

    ws.onerror = () => ws.close()
  }, [])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [connect])

  return connected
}
