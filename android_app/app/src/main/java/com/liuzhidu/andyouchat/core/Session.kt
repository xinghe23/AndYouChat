package com.liuzhidu.andyouchat.core

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

private val Context.sessionStore by preferencesDataStore(name = "ayc_session")

/**
 * 会话状态：token + 当前用户。
 * 与网页版 sessionStorage 行为一致：持久化到 DataStore，冷启动自动恢复登录。
 */
class Session(private val context: Context, private val scope: CoroutineScope) {

    var host: String = Config.DEFAULT_HOST
        private set
    var access: String? = null
        private set
    var refresh: String? = null
        private set
    var me: UserOut? = null
        private set

    private val _loggedIn = MutableStateFlow(false)
    val loggedIn: StateFlow<Boolean> = _loggedIn

    private val _hostFlow = MutableStateFlow(Config.DEFAULT_HOST)
    val hostFlow: StateFlow<String> = _hostFlow

    private val kHost = stringPreferencesKey("host")
    private val kAccess = stringPreferencesKey("access")
    private val kRefresh = stringPreferencesKey("refresh")
    private val kUserId = longKey("user_id")
    private val kUsername = stringPreferencesKey("username")
    private val kNickname = stringPreferencesKey("nickname")
    private val kAvatar = stringPreferencesKey("avatar_url")
    private val kSign = stringPreferencesKey("sign")

    init {
        scope.launch { restore() }
    }

    private suspend fun restore() {
        val p = context.sessionStore.data.first()
        host = p[kHost] ?: Config.DEFAULT_HOST
        access = p[kAccess]
        refresh = p[kRefresh]
        val uid = p[kUserId]
        me = if (uid != null) UserOut(
            id = uid,
            username = p[kUsername] ?: "",
            nickname = p[kNickname] ?: p[kUsername] ?: "",
            avatarUrl = p[kAvatar],
            sign = p[kSign],
        ) else null
        _hostFlow.value = host
        _loggedIn.value = access != null
    }

    suspend fun setTokens(t: TokenOut) {
        access = t.accessToken
        refresh = t.refreshToken
        t.user?.let { me = it }
        _loggedIn.value = access != null
        context.sessionStore.edit { p ->
            p[kHost] = host
            p[kAccess] = t.accessToken
            p[kRefresh] = t.refreshToken
            t.user?.let { u ->
                p[kUserId] = u.id
                p[kUsername] = u.username
                p[kNickname] = u.nickname
                u.avatarUrl?.let { p[kAvatar] = it }
                u.sign?.let { p[kSign] = it }
            }
        }
    }

    suspend fun setMe(u: UserOut) {
        me = u
        context.sessionStore.edit { p ->
            p[kUserId] = u.id
            p[kUsername] = u.username
            p[kNickname] = u.nickname
            u.avatarUrl?.let { p[kAvatar] = it } ?: p.remove(kAvatar)
            u.sign?.let { p[kSign] = it } ?: p.remove(kSign)
        }
    }

    suspend fun setHost(h: String) {
        host = h.trim().removePrefix("http://").removePrefix("https://").removeSuffix("/")
        if (host.isEmpty()) host = Config.DEFAULT_HOST
        _hostFlow.value = host
        context.sessionStore.edit { it[kHost] = host }
    }

    /** 清空会话（登出 / 登录失效）。登出前先 WsClient.close()。 */
    suspend fun clear() {
        access = null
        refresh = null
        me = null
        _loggedIn.value = false
        context.sessionStore.edit { p ->
            listOf(kAccess, kRefresh, kUserId, kUsername, kNickname, kAvatar, kSign).forEach { p.remove(it) }
        }
    }
}
