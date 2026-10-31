package com.liuzhidu.andyouchat.core

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.net.URLEncoder
import java.util.concurrent.TimeUnit
import kotlin.math.min
import kotlin.math.pow

enum class Conn { CONNECTING, LIVE, DOWN, UNAUTHORIZED }

/** WS 帧统一格式：{"type": "...", "data": {...}} */
@Serializable
data class WsFrame(val type: String, val data: JsonObject = JsonObject(emptyMap()))

/**
 * WebSocket 客户端：25s 心跳 + 60s 静默判定 + 指数退避重连 + 4401 鉴权失效回调。
 * 与网页版 ws.js 行为逐项对齐，业务层只订阅 frames。
 */
class WsClient(
    private val json: Json,
    private val tokenProvider: () -> String?,
    private val hostProvider: () -> String,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS) // WS 长连接禁用读超时
        .build()

    private var webSocket: WebSocket? = null
    private var scope: CoroutineScope? = null
    private var heartbeatJob: Job? = null
    private var retry = 0
    private var closedByUser = false
    @Volatile private var lastFrameAt = 0L

    private val _conn = MutableStateFlow(Conn.DOWN)
    val conn: StateFlow<Conn> = _conn

    private val _frames = MutableSharedFlow<WsFrame>(extraBufferCapacity = 128)
    val frames: SharedFlow<WsFrame> = _frames

    private val _authFailed = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val authFailed: SharedFlow<Unit> = _authFailed

    fun start() {
        stop()
        closedByUser = false
        scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        open()
    }

    fun stop() {
        closedByUser = true
        heartbeatJob?.cancel()
        heartbeatJob = null
        webSocket?.close(1000, "bye")
        webSocket = null
        scope?.cancel()
        scope = null
        _conn.value = Conn.DOWN
    }

    /** 发一帧；连接不可用时返回 false，调用方走 HTTP 兜底 */
    fun send(type: String, data: JsonObject = JsonObject(emptyMap())): Boolean {
        val ws = webSocket ?: return false
        return try {
            ws.send(json.encodeToString(WsFrame.serializer(), WsFrame(type, data)))
        } catch (_: Exception) {
            false
        }
    }

    private fun open() {
        val token = tokenProvider() ?: return
        val url = "${Config.wsBase(hostProvider())}?token=${URLEncoder.encode(token, "UTF-8")}"
        _conn.value = if (retry == 0) Conn.CONNECTING else Conn.DOWN
        val request = Request.Builder().url(url).build()
        webSocket = client.newWebSocket(request, listener)
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            retry = 0
            lastFrameAt = System.currentTimeMillis()
            _conn.value = Conn.LIVE
            startHeartbeat()
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            lastFrameAt = System.currentTimeMillis()
            val frame = runCatching { json.decodeFromString(WsFrame.serializer(), text) }.getOrNull()
            if (frame != null) _frames.tryEmit(frame)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            if (closedByUser) return
            if (code == 4401) {
                _conn.value = Conn.UNAUTHORIZED
                _authFailed.tryEmit(Unit)
                return
            }
            scheduleReconnect()
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (closedByUser) return
            scheduleReconnect()
        }
    }

    private fun startHeartbeat() {
        heartbeatJob?.cancel()
        heartbeatJob = scope?.launch {
            while (isActive) {
                delay(HEARTBEAT_MS)
                if (System.currentTimeMillis() - lastFrameAt > SILENCE_LIMIT_MS) {
                    // 半开连接：长期无任何帧，主动断开触发重连
                    runCatching { webSocket?.close(4000, "silent") }
                    break
                }
                send("ping")
            }
        }
    }

    private fun scheduleReconnect() {
        val s = scope ?: return
        _conn.value = Conn.DOWN
        heartbeatJob?.cancel()
        heartbeatJob = null
        s.launch {
            val delayMs = min(1000.0 * 1.6.pow(retry++), MAX_BACKOFF_MS.toDouble()).toLong()
            delay(delayMs)
            if (!closedByUser) open()
        }
    }

    companion object {
        const val HEARTBEAT_MS = 25_000L
        const val SILENCE_LIMIT_MS = 60_000L
        const val MAX_BACKOFF_MS = 15_000L
    }
}
