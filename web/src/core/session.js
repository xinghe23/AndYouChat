/**
 * 会话层：base 地址 + 双 token 的保存与恢复。
 * 用 sessionStorage 而不是 localStorage，这样同一浏览器的两个标签页可以登录两个账号做联调。
 */
const STORAGE_KEY = 'ayc_vue_session'

/**
 * 构建时注入的接口前缀（只到子目录，例如 /chat）。
 * 部署在 Nginx 子目录时必须设置：请求路径本身是 /api/v1/xxx，
 * 前缀负责把它挪到 /chat/api/v1/xxx —— 因为同一域名根路径的 /api/ 往往
 * 已被别的后端占用，聊天接口只能挂在自己的子前缀上。
 * 留空表示接口与页面同源（根路径部署）。
 */
const DEFAULT_BASE = String(import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')

export const session = {
  base: DEFAULT_BASE,
  access: '',
  refresh: '',

  load() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY)
      if (!raw) return false
      const data = JSON.parse(raw)
      this.base = data.base || DEFAULT_BASE
      this.access = data.access || ''
      this.refresh = data.refresh || ''
      return Boolean(this.access)
    } catch {
      return false
    }
  },

  save() {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ base: this.base, access: this.access, refresh: this.refresh }),
    )
  },

  setBase(base) {
    this.base = String(base || '').replace(/\/+$/, '')
    this.save()
  },

  setTokens(payload) {
    this.access = payload.access_token || ''
    this.refresh = payload.refresh_token || ''
    this.save()
  },

  clear() {
    this.access = ''
    this.refresh = ''
    sessionStorage.removeItem(STORAGE_KEY)
  },
}
