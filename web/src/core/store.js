import { reactive } from 'vue'
import { session } from './session'
import { api, request, ApiError } from './api'
import { createSocket } from './ws'
import { uid, sameId } from './format'

const ACK_TIMEOUT_MS = 8000
const TYPING_THROTTLE_MS = 2000
const TYPING_CLEAR_MS = 3000
export const RECALL_WINDOW_MS = 120000

export const store = reactive({
  ready: false,
  me: null,
  conn: 'idle', // idle | connecting | live | down | unauthorized

  conversations: [],
  friends: [],
  requests: [],
  pane: 'conversations',

  activeId: null,
  // 手机端（≤768px）单栏切换：'list' 显示会话/好友列表，'chat' 显示聊天窗口。
  // 桌面/平板双栏常驻，此状态不影响布局。
  mobileView: 'list',
  messages: [],
  hasMore: false,
  loadingConv: false,
  loadingMore: false,
  peerReadSeq: {},
  lastReadSent: {},
  typingConv: null,

  searchQuery: '',
  searchResults: [],
  searching: false,

  toast: null,
  profileOpen: false,
  unreadTotal: 0,
})

let socket = null
let toastTimer = null
let typingTimer = null
let lastTypingSentAt = 0
let pollTimer = null

/* ---------------- 内部工具 ---------------- */

export function toast(text, kind = 'info') {
  store.toast = { text, kind, at: Date.now() }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    store.toast = null
  }, 2600)
}

function findConv(id) {
  return store.conversations.find((c) => sameId(c.id, id)) || null
}

function sortConversations() {
  store.conversations.sort((a, b) => {
    if (Boolean(a.pinned) !== Boolean(b.pinned)) return a.pinned ? -1 : 1
    const ta = Number(a.last_message?.created_at || a.updated_at || 0)
    const tb = Number(b.last_message?.created_at || b.updated_at || 0)
    return tb - ta
  })
}

function updateBadge() {
  store.unreadTotal = store.conversations.reduce((sum, c) => sum + (Number(c.unread) || 0), 0)
  document.title = store.unreadTotal > 0 ? `(${store.unreadTotal}) AndYouChat` : 'AndYouChat'
}

function sortMessages() {
  store.messages.sort((a, b) => {
    const sa = a._pending ? Number.MAX_SAFE_INTEGER : Number(a.seq || 0)
    const sb = b._pending ? Number.MAX_SAFE_INTEGER : Number(b.seq || 0)
    return sa - sb
  })
}

function upsertMessage(message) {
  if (!sameId(message.conversation_id, store.activeId)) return false
  let idx = store.messages.findIndex((m) => sameId(m.id, message.id))
  if (idx < 0 && message.client_msg_id) {
    idx = store.messages.findIndex((m) => m.client_msg_id === message.client_msg_id)
  }
  if (idx >= 0) store.messages[idx] = { ...message }
  else store.messages.push({ ...message })
  sortMessages()
  return true
}

function bumpConversation(message) {
  const conv = findConv(message.conversation_id)
  if (!conv) return false
  conv.last_message = message
  conv.updated_at = message.created_at
  const mine = sameId(message.sender_id, store.me?.id)
  if (!mine && !sameId(conv.id, store.activeId)) {
    conv.unread = (Number(conv.unread) || 0) + 1
  }
  sortConversations()
  updateBadge()
  return true
}

function markFailed(clientMsgId, failed = true) {
  const msg = store.messages.find((m) => m.client_msg_id === clientMsgId)
  if (!msg) return
  msg._pending = false
  msg._failed = failed
}

async function sendViaHttp(payload) {
  try {
    const resp = await api.post('/api/v1/messages', payload)
    applyAck(resp.message)
  } catch (e) {
    markFailed(payload.client_msg_id)
    toast(e.message, 'error')
  }
}

function applyAck(message) {
  if (!message) return
  const idx = store.messages.findIndex(
    (m) => m.client_msg_id && m.client_msg_id === message.client_msg_id,
  )
  if (idx >= 0) store.messages[idx] = { ...message }
  else upsertMessage(message)
  sortMessages()
  if (!bumpConversation(message)) refreshConversations().catch(() => {})
}

/* ---------------- WebSocket ---------------- */

function wsUrl() {
  const base = session.base || window.location.origin
  const url = new URL(base, window.location.origin)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  // base 可能带路径前缀（子目录部署时是 /chat/api），WS 必须挂在同一前缀下，
  // 否则会把请求打到站点根路径的 /ws 上（那通常是别的服务）。
  const prefix = url.pathname.replace(/\/+$/, '')
  url.pathname = `${prefix}/ws`
  url.search = `?token=${encodeURIComponent(session.access)}`
  return url.toString()
}

function disconnectSocket() {
  if (socket) {
    socket.close()
    socket = null
  }
}

export function connect() {
  disconnectSocket()
  store.conn = 'connecting'
  socket = createSocket({
    url: wsUrl,
    onOpen: () => {
      resync().catch(() => {})
    },
    onFrame: handleFrame,
    onStatus: (status) => {
      store.conn = status
    },
    onAuthFail: () => {
      signOut(true)
    },
  })
}

function handleFrame(frame) {
  const data = frame.data || {}
  switch (frame.type) {
    case 'pong':
      store.conn = 'live'
      break
    case 'msg.ack':
      applyAck(data.message)
      markRead()
      break
    case 'msg.new':
      onIncoming(data.message)
      break
    case 'msg.read':
      onReadReceipt(data)
      break
    case 'msg.recalled':
      onRecalled(data.message)
      break
    case 'typing':
      onTyping(data)
      break
    case 'presence':
      onPresence(data)
      break
    case 'error':
      toast(data.message || '操作失败', 'error')
      break
    default:
      break
  }
}

function onIncoming(message) {
  if (!message) return
  if (sameId(message.conversation_id, store.activeId)) {
    upsertMessage(message)
    markRead()
  }
  if (!bumpConversation(message)) refreshConversations().catch(() => {})
}

function onReadReceipt({ conversation_id, user_id, seq }) {
  if (sameId(user_id, store.me?.id)) return
  const key = String(conversation_id)
  const current = Number(store.peerReadSeq[key] || 0)
  if (Number(seq) > current) store.peerReadSeq[key] = Number(seq)
}

function onRecalled(message) {
  if (!message) return
  if (sameId(message.conversation_id, store.activeId)) {
    const idx = store.messages.findIndex((m) => sameId(m.id, message.id))
    if (idx >= 0) store.messages[idx] = { ...store.messages[idx], ...message }
  }
  const conv = findConv(message.conversation_id)
  if (conv && conv.last_message && sameId(conv.last_message.id, message.id)) {
    conv.last_message = { ...conv.last_message, ...message }
  }
}

function onTyping({ conversation_id }) {
  if (!sameId(conversation_id, store.activeId)) return
  store.typingConv = String(conversation_id)
  if (typingTimer) clearTimeout(typingTimer)
  typingTimer = setTimeout(() => {
    store.typingConv = null
  }, TYPING_CLEAR_MS)
}

function onPresence({ user_id, online }) {
  store.friends.forEach((f) => {
    if (sameId(f.id, user_id)) f.online = Boolean(online)
  })
  store.conversations.forEach((c) => {
    if (c.peer && sameId(c.peer.id, user_id)) {
      c.peer.online = Boolean(online)
      c.peer_online = Boolean(online)
    }
  })
  store.searchResults.forEach((u) => {
    if (sameId(u.id, user_id)) u.online = Boolean(online)
  })
}

/** 重连后：补拉当前会话增量 + 刷新列表 */
async function resync() {
  try {
    if (store.activeId) {
      const synced = store.messages.filter((m) => Number(m.seq) > 0)
      const lastSeq = synced.length ? Number(synced[synced.length - 1].seq) : 0
      const page = await api.get(
        `/api/v1/conversations/${store.activeId}/messages?after_seq=${lastSeq}`,
      )
      page.items.forEach((m) => upsertMessage(m))
      if (page.items.length) {
        store.lastReadSent[String(store.activeId)] = 0
        markRead()
      }
    }
    await refreshAll()
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return
  }
}

/* ---------------- 启动 / 认证 ---------------- */

export async function bootstrap() {
  if (!session.load()) {
    store.ready = true
    return
  }
  try {
    store.me = await api.get('/api/v1/auth/me')
    store.ready = true
    connect()
    startPolling()
    await refreshAll()
  } catch {
    session.clear()
    store.ready = true
  }
}

export async function login({ username, password, base, register }) {
  session.setBase(base || '')
  const data = await request(register ? '/api/v1/auth/register' : '/api/v1/auth/login', {
    method: 'POST',
    auth: false,
    body: register
      ? { username, password, nickname: username }
      : { username, password },
  })
  session.setTokens(data)
  store.me = data.user
  store.ready = true
  connect()
  startPolling()
  await refreshAll()
}

export function signOut(expired = false) {
  disconnectSocket()
  stopPolling()
  session.clear()
  store.me = null
  store.conversations = []
  store.friends = []
  store.requests = []
  store.messages = []
  store.activeId = null
  store.mobileView = 'list'
  store.hasMore = false
  store.peerReadSeq = {}
  store.lastReadSent = {}
  store.searchResults = []
  store.searchQuery = ''
  store.pane = 'conversations'
  store.conn = 'idle'
  store.profileOpen = false
  store.unreadTotal = 0
  document.title = 'AndYouChat'
  if (expired) toast('登录已失效，请重新登录', 'error')
}

/* ---------------- 列表数据 ---------------- */

export async function refreshConversations() {
  store.conversations = await api.get('/api/v1/conversations')
  sortConversations()
  updateBadge()
}

export async function refreshFriends() {
  store.friends = await api.get('/api/v1/friends')
}

export async function refreshRequests() {
  store.requests = await api.get('/api/v1/friends/requests')
}

export async function refreshAll() {
  await Promise.allSettled([refreshConversations(), refreshFriends(), refreshRequests()])
}

/* ---------------- 会话与消息 ---------------- */

export async function openConversation(id) {
  store.pane = 'conversations'
  store.mobileView = 'chat' // 手机上点开即进入全屏聊天，桌面端该值不影响布局
  if (sameId(store.activeId, id)) return
  store.activeId = String(id)
  store.messages = []
  store.hasMore = false
  store.typingConv = null
  store.loadingConv = true
  try {
    const page = await api.get(`/api/v1/conversations/${id}/messages?limit=30`)
    if (!sameId(store.activeId, id)) return
    store.messages = page.items || []
    store.hasMore = Boolean(page.has_more)
    const conv = findConv(id)
    if (conv) conv.unread = 0
    updateBadge()
    markRead(true)
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    store.loadingConv = false
  }
}

export async function loadMore() {
  if (store.loadingMore || !store.hasMore || !store.activeId) return
  const first = store.messages.find((m) => Number(m.seq) > 0)
  if (!first) return
  store.loadingMore = true
  try {
    const page = await api.get(
      `/api/v1/conversations/${store.activeId}/messages?before_seq=${first.seq}&limit=30`,
    )
    const known = new Set(store.messages.map((m) => String(m.id)))
    const older = (page.items || []).filter((m) => !known.has(String(m.id)))
    store.messages = [...older, ...store.messages]
    store.hasMore = Boolean(page.has_more)
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    store.loadingMore = false
  }
}

export function markRead(force = false) {
  if (!store.activeId) return
  const synced = store.messages.filter((m) => Number(m.seq) > 0)
  if (!synced.length) return
  const key = String(store.activeId)
  const seq = Number(synced[synced.length - 1].seq)
  if (!force && Number(store.lastReadSent[key] || 0) >= seq) return
  store.lastReadSent[key] = seq
  const sent = socket && socket.send('msg.read', { conversation_id: key, seq })
  if (!sent) {
    api.post(`/api/v1/conversations/${key}/read`, { conversation_id: key, seq }).catch(() => {})
  }
}

export function sendText(content) {
  const text = String(content || '').trim()
  if (!text || !store.activeId || !store.me) return false
  const convId = String(store.activeId)
  const clientMsgId = uid()
  const optimistic = {
    id: `tmp-${clientMsgId}`,
    conversation_id: convId,
    seq: 0,
    sender_id: store.me.id,
    msg_type: 'text',
    content: text,
    extra: null,
    client_msg_id: clientMsgId,
    revoked: false,
    created_at: Date.now(),
    _pending: true,
    _failed: false,
  }
  store.messages.push(optimistic)
  sortMessages()

  const payload = {
    conversation_id: convId,
    client_msg_id: clientMsgId,
    msg_type: 'text',
    content: text,
  }
  const sent = socket && socket.send('msg.send', payload)
  if (!sent) sendViaHttp(payload)

  setTimeout(() => {
    const msg = store.messages.find((m) => m.client_msg_id === clientMsgId)
    if (msg && msg._pending) markFailed(clientMsgId)
  }, ACK_TIMEOUT_MS)
  return true
}

export function retryMessage(message) {
  if (!message) return
  message._pending = true
  message._failed = false
  const payload = {
    conversation_id: message.conversation_id,
    client_msg_id: message.client_msg_id,
    msg_type: message.msg_type || 'text',
    content: message.content,
  }
  const sent = socket && socket.send('msg.send', payload)
  if (!sent) sendViaHttp(payload)
}

export function canRecall(message) {
  if (!message || message.revoked || message._pending || message._failed) return false
  if (!sameId(message.sender_id, store.me?.id)) return false
  return Date.now() - Number(message.created_at || 0) < RECALL_WINDOW_MS
}

export async function recallMessage(message) {
  if (!message) return
  try {
    const updated = await api.post(`/api/v1/messages/${message.id}/recall`)
    const idx = store.messages.findIndex((m) => sameId(m.id, updated.id))
    if (idx >= 0) store.messages[idx] = { ...store.messages[idx], ...updated }
    const conv = findConv(updated.conversation_id)
    if (conv && conv.last_message && sameId(conv.last_message.id, updated.id)) {
      conv.last_message = { ...conv.last_message, ...updated }
    }
    toast('已撤回')
  } catch (e) {
    toast(e.message, 'error')
  }
}

export function notifyTyping() {
  if (!store.activeId || !socket) return
  const now = Date.now()
  if (now - lastTypingSentAt < TYPING_THROTTLE_MS) return
  lastTypingSentAt = now
  socket.send('typing', { conversation_id: String(store.activeId) })
}

/* ---------------- 好友 ---------------- */

/**
 * 好友申请没有实时推送通道（协议里只覆盖消息类事件），
 * 这里用 20s 轮询兜底，切到「申请」面板时也会立即刷新一次。
 */
function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    if (document.hidden || !store.me) return
    refreshRequests().catch(() => {})
  }, 20000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

export async function openWith(peerId) {
  try {
    const conv = await api.post('/api/v1/conversations/single', { peer_id: peerId })
    if (!findConv(conv.id)) await refreshConversations()
    await openConversation(conv.id)
  } catch (e) {
    toast(e.message, 'error')
  }
}

export async function searchUsers(query) {
  store.searchQuery = query
  const q = String(query || '').trim()
  if (!q) {
    store.searchResults = []
    return
  }
  store.searching = true
  try {
    store.searchResults = await api.get(`/api/v1/users/search?q=${encodeURIComponent(q)}`)
  } catch (e) {
    store.searchResults = []
    toast(e.message, 'error')
  } finally {
    store.searching = false
  }
}

export async function addFriend(userId) {
  try {
    const res = await api.post('/api/v1/friends/requests', {
      to_user_id: userId,
      message: '你好',
    })
    const item = store.searchResults.find((u) => sameId(u.id, userId))
    if (res && res.status === 'accepted') {
      if (item) item.is_friend = true
      await refreshFriends()
      toast('对方也在等你，已成为好友')
    } else {
      if (item) item.request_pending = true
      toast('好友申请已发送')
    }
  } catch (e) {
    toast(e.message, 'error')
  }
}

export async function respondRequest(requestId, accept) {
  try {
    await api.post(`/api/v1/friends/requests/${requestId}/respond`, { accept })
    await Promise.all([refreshRequests(), refreshFriends()])
    toast(accept ? '已添加为好友' : '已拒绝该申请')
  } catch (e) {
    toast(e.message, 'error')
  }
}

export async function saveProfile({ nickname, sign }) {
  try {
    store.me = await api.patch('/api/v1/users/me', { nickname, sign })
    store.profileOpen = false
    toast('资料已保存')
  } catch (e) {
    toast(e.message, 'error')
  }
}
