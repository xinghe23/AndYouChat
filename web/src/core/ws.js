/**
 * WebSocket 客户端：心跳保活 + 指数退避重连 + 鉴权失败回调。
 * 与业务无关，只负责把 frame 交给上层。
 */
import { parseJson } from './format'

const HEARTBEAT_MS = 25000
const SILENCE_LIMIT_MS = 60000
const MAX_BACKOFF_MS = 15000

export function createSocket({ url, onOpen, onFrame, onStatus, onAuthFail }) {
  let ws = null
  let retry = 0
  let closedByUser = false
  let heartbeat = null
  let reconnectTimer = null
  let lastFrameAt = Date.now()

  function clearTimers() {
    if (heartbeat) {
      clearInterval(heartbeat)
      heartbeat = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function scheduleReconnect() {
    const delay = Math.min(1000 * Math.pow(1.6, retry++), MAX_BACKOFF_MS)
    onStatus('down')
    reconnectTimer = setTimeout(open, delay)
  }

  function startHeartbeat() {
    lastFrameAt = Date.now()
    heartbeat = setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      if (Date.now() - lastFrameAt > SILENCE_LIMIT_MS) {
        // 长时间没有任何帧，判定为半开连接，强制走重连
        try {
          ws.close()
        } catch {
          /* ignore */
        }
        return
      }
      send('ping', {})
    }, HEARTBEAT_MS)
  }

  function open() {
    clearTimers()
    onStatus(retry === 0 ? 'connecting' : 'down')
    try {
      ws = new WebSocket(url())
    } catch {
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      retry = 0
      onStatus('live')
      startHeartbeat()
      onOpen?.()
    }

    ws.onmessage = (ev) => {
      lastFrameAt = Date.now()
      const frame = parseJson(ev.data)
      if (frame && frame.type) onFrame?.(frame)
    }

    ws.onclose = (ev) => {
      clearTimers()
      if (closedByUser) return
      if (ev.code === 4401) {
        onStatus('unauthorized')
        onAuthFail?.()
        return
      }
      scheduleReconnect()
    }

    ws.onerror = () => {
      // onclose 会紧随其后，这里不重复处理
    }
  }

  function send(type, data) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false
    try {
      ws.send(JSON.stringify({ type, data: data || {} }))
      return true
    } catch {
      return false
    }
  }

  function close() {
    closedByUser = true
    clearTimers()
    if (ws) {
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      ws = null
    }
  }

  open()

  return { send, close, isOpen: () => Boolean(ws) && ws.readyState === WebSocket.OPEN }
}
