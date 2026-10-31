package com.liuzhidu.andyouchat.data

import android.content.Context
import com.liuzhidu.andyouchat.core.Api
import com.liuzhidu.andyouchat.core.Config
import com.liuzhidu.andyouchat.core.Session
import com.liuzhidu.andyouchat.core.TokenAuthenticator
import com.liuzhidu.andyouchat.core.TokenOut
import com.liuzhidu.andyouchat.core.RefreshIn
import com.liuzhidu.andyouchat.core.WsClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

/**
 * 手动依赖容器：json / session / api / ws + 共享状态。
 * host 变化时自动重建 Retrofit。
 */
class AppContainer(context: Context, private val appScope: CoroutineScope) {

    val json: Json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
        explicitNulls = false
    }

    val session = Session(context, appScope)

    /** 好友在线状态缓存：userId -> online（presence 事件驱动） */
    val presence = MutableStateFlow<Map<Long, Boolean>>(emptyMap())

    /** 当前正在全屏查看的会话（Home 用于把未读清零；Chat 离开时置 null） */
    val readingConvId = MutableStateFlow<Long?>(null)

    private val authlessClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private val authenticator = TokenAuthenticator(session) { refreshTokens() }

    private val authedClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .addInterceptor(com.liuzhidu.andyouchat.core.AuthInterceptor(session))
        .authenticator(authenticator)
        .build()

    @Volatile
    var api: Api = buildApi(Config.DEFAULT_HOST)
        private set

    val ws = WsClient(json, { session.access }, { session.host })

    init {
        appScope.launch {
            session.hostFlow.collect { host -> if (apiHost != host) { apiHost = host; api = buildApi(host) } }
        }
    }

    @Volatile
    private var apiHost: String = Config.DEFAULT_HOST

    private fun buildApi(host: String): Api =
        Retrofit.Builder()
            .baseUrl(Config.restBase(host))
            .client(authedClient)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(Api::class.java)

    /**
     * 用 refresh_token 续期（401 时由 Authenticator 调用，裸客户端避免递归）。
     * 返回是否成功；失败时不清会话，由上层决定（网页版逻辑：重放一次，再失败抛 401）。
     */
    private suspend fun refreshTokens(): Boolean {
        val refreshToken = session.refresh ?: return false
        return try {
            val body = json.encodeToString(RefreshIn.serializer(), RefreshIn(refreshToken))
                .toRequestBody("application/json".toMediaType())
            val request = Request.Builder()
                .url(Config.restBase(session.host) + "v1/auth/refresh")
                .header("X-No-Auth", "1")
                .post(body)
                .build()
            authlessClient.newCall(request).execute().use { resp ->
                val text = resp.body?.string()
                if (!resp.isSuccessful || text.isNullOrBlank()) return@use false
                val token = json.decodeFromString(TokenOut.serializer(), text)
                session.setTokens(token)
                true
            }
        } catch (_: Exception) {
            false
        }
    }
}
