import { session } from './session'
import { formatError, parseJson } from './format'

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

let refreshingPromise = null

/** 用 refresh_token 续期，返回是否成功。并发请求只会触发一次刷新。 */
async function refreshTokens() {
  if (!session.refresh) return false
  if (!refreshingPromise) {
    refreshingPromise = (async () => {
      try {
        const resp = await fetch(`${session.base}/api/v1/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: session.refresh }),
        })
        if (!resp.ok) return false
        const data = parseJson(await resp.text())
        if (!data || !data.access_token) return false
        session.setTokens(data)
        return true
      } catch {
        return false
      } finally {
        refreshingPromise = null
      }
    })()
  }
  return refreshingPromise
}

export async function request(path, options = {}) {
  const { method = 'GET', body, auth = true, retry = true } = options
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth && session.access) headers.Authorization = `Bearer ${session.access}`

  let resp
  try {
    resp = await fetch(`${session.base}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('连不上服务器，请确认服务已启动、地址填写正确', 0)
  }

  const data = parseJson(await resp.text())

  if (resp.status === 401 && auth && retry) {
    if (await refreshTokens()) return request(path, { ...options, retry: false })
    session.clear()
    throw new ApiError('登录已过期，请重新登录', 401)
  }

  if (!resp.ok) {
    const detail = data && data.detail !== undefined ? data.detail : data
    throw new ApiError(formatError(detail, resp.status), resp.status)
  }
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: body ?? {} }),
  patch: (path, body) => request(path, { method: 'PATCH', body: body ?? {} }),
}
