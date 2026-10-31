package com.liuzhidu.andyouchat.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Interceptor
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import okhttp3.Authenticator
import kotlinx.coroutines.runBlocking

/** 业务错误：message 已是可直接展示的中文文案（来自后端 detail） */
class ApiError(val status: Int, message: String) : Exception(message)

object ErrorParser {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    /** 后端约定 detail 永远是字符串；兜底解析，失败时给通用文案 */
    fun fromBody(status: Int, raw: String?): String {
        val body = raw?.trim().orEmpty()
        if (body.isNotEmpty()) {
            try {
                val obj = json.parseToJsonElement(body)
                if (obj is JsonObject) {
                    val d = obj["detail"]
                    if (d != null) {
                        val s = runCatching { d.jsonPrimitive.content }.getOrNull()
                        if (!s.isNullOrBlank()) return s
                    }
                }
            } catch (_: Exception) {
                // 非 JSON，走通用文案
            }
        }
        return when (status) {
            0 -> "连不上服务器，请确认网络、服务器地址是否正确"
            401 -> "登录已过期，请重新登录"
            else -> "请求失败（HTTP $status）"
        }
    }
}

/** 给请求附加 Bearer token；带 No-Auth 标记的请求（登录/注册/刷新）跳过 */
class AuthInterceptor(private val session: Session) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val builder = chain.request().newBuilder()
        if (chain.request().header(HEADER_NO_AUTH) == null) {
            session.access?.let { builder.header("Authorization", "Bearer $it") }
        }
        return chain.proceed(builder.build())
    }

    companion object {
        const val HEADER_NO_AUTH = "X-No-Auth"
    }
}

/**
 * 401 自动续期：用 refresh_token 换新 token 后重放原请求（对齐网页版 api.js）。
 * 刷新用独立的裸客户端，避免递归套认证器。并发 401 只会刷新一次。
 */
class TokenAuthenticator(
    private val session: Session,
    private val refreshCall: suspend () -> Boolean,
) : Authenticator {

    override fun authenticate(route: Route?, response: Response): Request? {
        // 刷新接口自己 401 说明 refresh 也失效了，直接清会话
        if (response.request.header(HEADER_NO_AUTH) != null) return null
        if (responseCount(response) >= 2) return null

        val ok = runBlocking { refreshCall() }
        if (!ok) return null

        return response.request.newBuilder()
            .header("Authorization", "Bearer ${session.access}")
            .build()
    }

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}
