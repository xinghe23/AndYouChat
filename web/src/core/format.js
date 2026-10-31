/** 通用格式化：时间、错误文案、雪花 ID 安全解析 */

const FIELD_LABELS = {
  username: '用户名',
  password: '密码',
  nickname: '昵称',
  sign: '签名',
  to_user_id: '对方用户',
  peer_id: '对方用户',
  conversation_id: '会话',
  client_msg_id: '消息标识',
  content: '消息内容',
  seq: '已读位置',
  q: '搜索关键字',
  accept: '是否同意',
  limit: '每页数量',
  refresh_token: '刷新令牌',
  access_token: '访问令牌',
  message: '申请附言',
}

function translateValidation(msg) {
  const text = String(msg || '').replace(/^Value error,\s*/, '')
  let m = text.match(/at least (\d+) character/)
  if (m) return `至少需要 ${m[1]} 个字符`
  m = text.match(/at most (\d+) character/)
  if (m) return `最多 ${m[1]} 个字符`
  if (text.includes('Field required')) return '不能为空'
  if (text.includes('String should match pattern')) return '只能用字母、数字或下划线'
  if (text.includes('valid integer')) return '必须是整数'
  if (text.includes('Input should be')) return '取值不合法'
  return text
}

/** 后端 detail 约定为字符串；这里保留数组兜底，避免历史版本裸露 JSON */
export function formatError(detail, status) {
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      const loc = (item.loc || []).filter((p) => p !== 'body' && p !== 'query')
      const field = FIELD_LABELS[loc[0]] || loc[0] || '参数'
      return field + translateValidation(item.msg)
    })
    return parts.filter(Boolean).join('；') || '输入格式不正确'
  }
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail)
  return `请求失败（HTTP ${status}）`
}

/**
 * 雪花 ID 是 19 位整数，超出 JS 安全整数范围（2^53），直接 JSON.parse 会被截断，
 * 极端情况下不同用户可能落到同一个浮点数上。这里把 16 位以上的整数先转成字符串再解析。
 * 后端 Pydantic 与 WS 处理都做了 int() 强转，字符串回传是安全的。
 */
const BIG_INT_RE = /(:\s*)(-?\d{16,})(?=\s*[,}\]])/g

export function parseJson(text) {
  if (!text) return null
  try {
    return JSON.parse(text.replace(BIG_INT_RE, '$1"$2"'))
  } catch {
    return text
  }
}

export function sameId(a, b) {
  if (a === undefined || a === null || b === undefined || b === null) return false
  return String(a) === String(b)
}

export function uid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replace(/-/g, '')
  }
  return String(Date.now()) + Math.random().toString(16).slice(2, 10)
}

export function fmtTime(ms) {
  if (!ms) return ''
  const d = new Date(Number(ms))
  const now = new Date()
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (d.toDateString() === now.toDateString()) return hm
  const yesterday = new Date(now.getTime() - 86400000)
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${hm}`
  return `${d.getMonth() + 1}/${d.getDate()} ${hm}`
}

export function fmtDay(ms) {
  const d = new Date(Number(ms))
  const now = new Date()
  const md = `${d.getMonth() + 1}月${d.getDate()}日`
  return d.getFullYear() === now.getFullYear() ? md : `${d.getFullYear()}年${md}`
}

export function dayKey(ms) {
  const d = new Date(Number(ms))
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
}

export function initial(name) {
  const text = String(name || '?').trim()
  return (text ? text.slice(0, 1) : '?').toUpperCase()
}

export function previewOf(message) {
  if (!message) return ''
  if (message.revoked) return '[消息已撤回]'
  if (message.msg_type === 'image') return '[图片]'
  return message.content || ''
}
